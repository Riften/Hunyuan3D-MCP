"""Async API Key client. Submissions are intentionally never retried."""

import asyncio
import json
import math
import os
from dataclasses import dataclass, field
from typing import Any

import httpx

from .models import MAX_REQUEST_BYTES, GenerationInput, JobInput

BASE_URL = "https://api.ai3d.cloud.tencent.com"
TERMINAL_STATES = {"DONE", "FAIL"}


class HunyuanError(Exception):
    """A safe-to-display API/configuration error."""


@dataclass(frozen=True)
class Settings:
    api_key: str = field(default="", repr=False)
    proxy: str | None = field(default=None, repr=False)
    timeout_seconds: float = 30

    def __post_init__(self) -> None:
        if not math.isfinite(self.timeout_seconds) or not 1 <= self.timeout_seconds <= 120:
            raise HunyuanError("HY3D_TIMEOUT_SECONDS must be between 1 and 120.")
        if self.api_key and (
            not self.api_key.isascii()
            or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in self.api_key)
        ):
            raise HunyuanError("HY3D_API_KEY must contain an API Key without whitespace.")

    @classmethod
    def from_env(cls) -> "Settings":
        try:
            timeout = float(os.getenv("HY3D_TIMEOUT_SECONDS", "30"))
        except ValueError as exc:
            raise HunyuanError("HY3D_TIMEOUT_SECONDS must be a number.") from exc
        return cls(
            api_key=os.getenv("HY3D_API_KEY", "").strip(),
            proxy=os.getenv("HY3D_PROXY") or None,
            timeout_seconds=timeout,
        )

    def public_info(self) -> dict:
        return {
            "api_key_configured": bool(self.api_key),
            "base_url": BASE_URL,
            "authentication": "Authorization: <HY3D_API_KEY> (no Bearer prefix)",
            "edition": "pro",
            "models": ["3.0", "3.1"],
            "timeout_seconds": self.timeout_seconds,
            "proxy_configured": bool(
                self.proxy
                or any(
                    os.getenv(k)
                    for k in (
                        "HTTPS_PROXY",
                        "https_proxy",
                        "HTTP_PROXY",
                        "http_proxy",
                        "ALL_PROXY",
                        "all_proxy",
                    )
                )
            ),
            "network_checked": False,
            "automatic_submission_retries": 0,
        }


class HunyuanClient:
    def __init__(self, settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None):
        self.settings = settings
        self._http = httpx.AsyncClient(
            base_url=BASE_URL,
            proxy=settings.proxy,
            timeout=settings.timeout_seconds,
            follow_redirects=False,
            transport=transport,
        )

    async def __aenter__(self) -> "HunyuanClient":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self._http.aclose()

    def _safe(self, value: Any) -> str:
        text = str(value)
        if self.settings.api_key:
            text = text.replace(self.settings.api_key, "[REDACTED]")
        return text[:1000]

    async def _request(self, operation: str, payload: dict) -> dict:
        if not self.settings.api_key:
            raise HunyuanError("Set HY3D_API_KEY in the MCP server process environment.")
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(body) > MAX_REQUEST_BYTES:
            raise HunyuanError("Encoded JSON request exceeds 8 MiB; use a smaller image.")
        uncertainty = (
            " Submission may have been accepted and billed. Do not automatically resubmit; "
            "check the Tencent console first."
            if operation == "submit"
            else ""
        )
        try:
            async with asyncio.timeout(self.settings.timeout_seconds):
                response = await self._http.post(
                    f"/v1/ai3d/{operation}",
                    headers={
                        "Authorization": self.settings.api_key,
                        "Content-Type": "application/json",
                    },
                    content=body,
                )
        except (httpx.HTTPError, TimeoutError) as exc:
            raise HunyuanError(
                f"{operation}: network request failed ({type(exc).__name__})." + uncertainty
            ) from None
        if not 200 <= response.status_code < 300:
            # Do not include arbitrary response bodies, which can echo secrets or image data.
            raise HunyuanError(f"{operation}: HTTP {response.status_code}." + uncertainty)
        try:
            data = response.json()
        except ValueError:
            raise HunyuanError(f"{operation}: invalid JSON response." + uncertainty) from None
        if not isinstance(data, dict):
            raise HunyuanError(f"{operation}: expected a JSON object." + uncertainty)
        result = data.get("Response", data)
        if not isinstance(result, dict):
            raise HunyuanError(f"{operation}: invalid Response envelope." + uncertainty)
        error = result.get("Error") or result.get("error")
        if error:
            if isinstance(error, dict):
                code = error.get("Code", error.get("code", "APIError"))
                message = error.get("Message", error.get("message", "Request failed"))
            else:
                code, message = "APIError", "Request failed"
            request_id = self._safe(result.get("RequestId", "unknown"))
            raise HunyuanError(
                f"{operation}: {self._safe(code)}: {self._safe(message)} (RequestId: {request_id})"
            )
        if operation == "submit":
            if not isinstance(result.get("JobId"), str) or not result["JobId"]:
                raise HunyuanError("submit: response is missing JobId." + uncertainty)
        elif not isinstance(result.get("Status"), str) or result["Status"] not in {
            "WAIT",
            "RUN",
            "DONE",
            "FAIL",
        }:
            raise HunyuanError("query: response contains a missing or unknown Status.")
        # Preserve official result URLs, credit accounting, and future response fields.
        return result

    async def submit(self, request: GenerationInput) -> dict:
        payload = await asyncio.to_thread(request.to_payload)
        return await self._request("submit", payload)

    async def query(self, job_id: str) -> dict:
        job = JobInput(job_id=job_id)
        result = await self._request("query", {"JobId": job.job_id})
        return {**result, "JobId": job.job_id}

    async def wait(
        self, job_id: str, *, max_polls: int = 3, poll_interval_seconds: float = 10
    ) -> dict:
        JobInput(job_id=job_id)
        if (
            isinstance(max_polls, bool)
            or not isinstance(max_polls, int)
            or not 1 <= max_polls <= 10
        ):
            raise ValueError("max_polls must be an integer between 1 and 10.")
        if not math.isfinite(poll_interval_seconds) or not 5 <= poll_interval_seconds <= 60:
            raise ValueError("poll_interval_seconds must be between 5 and 60.")
        for poll in range(1, max_polls + 1):
            result = await self.query(job_id)
            complete = result["Status"] in TERMINAL_STATES
            if complete or poll == max_polls:
                return {**result, "polls_performed": poll, "polling_exhausted": not complete}
            await asyncio.sleep(poll_interval_seconds)
        raise AssertionError("Unreachable")
