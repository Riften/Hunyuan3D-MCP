"""Async Tencent Cloud TC3 client with environment credentials and no submission retries."""

import asyncio
import json
import math
import os
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from .auth import tc3_headers
from .models import MAX_REQUEST_BYTES, JobInput
from .services import SERVICES, TC3_HOST, Backend, Service

BASE_URL = "https://api.ai3d.cloud.tencent.com"
TERMINAL_STATES = {"DONE", "FAIL"}


class PayloadInput(Protocol):
    def to_payload(self) -> dict: ...


class HunyuanError(Exception):
    """A safe-to-display API/configuration error."""


@dataclass(frozen=True)
class Settings:
    proxy: str | None = field(default=None, repr=False)
    timeout_seconds: float = 30
    secret_id: str = field(default="", repr=False)
    secret_key: str = field(default="", repr=False)
    token: str = field(default="", repr=False)
    # AI3D currently supports Guangzhou (per the service region list).
    region: str = "ap-guangzhou"

    def __post_init__(self) -> None:
        if not math.isfinite(self.timeout_seconds) or not 1 <= self.timeout_seconds <= 120:
            raise HunyuanError("HY3D_TIMEOUT_SECONDS must be between 1 and 120.")
        for name, value in (
            ("TENCENTCLOUD_SECRET_ID", self.secret_id),
            ("TENCENTCLOUD_SECRET_KEY", self.secret_key),
            ("TENCENTCLOUD_TOKEN", self.token),
            ("TENCENTCLOUD_REGION", self.region),
        ):
            if value and (
                not value.isascii()
                or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in value)
            ):
                raise HunyuanError(f"{name} must be ASCII without whitespace/control characters.")

    @property
    def tc3_configured(self) -> bool:
        return bool(self.secret_id and self.secret_key)

    @classmethod
    def from_env(cls) -> "Settings":
        try:
            timeout = float(os.getenv("HY3D_TIMEOUT_SECONDS", "30"))
        except ValueError as exc:
            raise HunyuanError("HY3D_TIMEOUT_SECONDS must be a number.") from exc
        return cls(
            proxy=os.getenv("HY3D_PROXY") or None,
            timeout_seconds=timeout,
            secret_id=os.getenv("TENCENTCLOUD_SECRET_ID", "").strip(),
            secret_key=os.getenv("TENCENTCLOUD_SECRET_KEY", "").strip(),
            token=os.getenv("TENCENTCLOUD_TOKEN", "").strip(),
            region=os.getenv("TENCENTCLOUD_REGION", "ap-guangzhou").strip() or "ap-guangzhou",
        )

    def public_info(self) -> dict:
        return {
            "edition": "pro",
            "tc3_configured": self.tc3_configured,
            "tc3_credentials_incomplete": bool(self.secret_id) != bool(self.secret_key),
            "tc3_base_url": f"https://{TC3_HOST}",
            "tc3_region": self.region or None,
            "available_services": ([*SERVICES, "convert"] if self.tc3_configured else []),
            "availability_note": "Credential presence only; service access and quota are not "
            "checked.",
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
        for secret in (
            self.settings.secret_id,
            self.settings.secret_key,
            self.settings.token,
        ):
            if secret:
                text = text.replace(secret, "[REDACTED]")
        return text[:1000]

    async def _request(
        self,
        operation: str,
        payload: dict,
        *,
        action: str | None = None,
        result_kind: str | None = None,
    ) -> dict:
        result_kind = result_kind or operation
        if action and not self.settings.tc3_configured:
            raise HunyuanError(
                "This service requires Tencent Cloud TC3 credentials: set TENCENTCLOUD_SECRET_ID "
                "and TENCENTCLOUD_SECRET_KEY (optional TENCENTCLOUD_TOKEN) in the "
                "server environment. "
            )
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        limit = (
            12 * 1024 * 1024
            if action in {"SubmitTextureTo3DJob", "SubmitProfileTo3DJob"}
            else MAX_REQUEST_BYTES
        )
        if len(body) > limit:
            raise HunyuanError(f"Encoded JSON request exceeds {limit} bytes; use smaller images.")
        uncertainty = (
            " Submission may have been accepted and billed. Do not automatically resubmit; "
            "check the Tencent console first."
            if result_kind in {"submit", "convert"}
            else ""
        )
        headers = {"Content-Type": "application/json"}
        url = f"https://{TC3_HOST}/"
        if action:
            url = f"https://{TC3_HOST}/"
            headers = tc3_headers(
                body,
                action,
                self.settings.secret_id,
                self.settings.secret_key,
                int(time.time()),
                token=self.settings.token,
                region=self.settings.region,
            )
        try:
            async with asyncio.timeout(self.settings.timeout_seconds):
                response = await self._http.post(
                    url,
                    headers=headers,
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
        if result_kind == "submit":
            if not isinstance(result.get("JobId"), str) or not result["JobId"]:
                raise HunyuanError("submit: response is missing JobId." + uncertainty)
        elif result_kind == "convert":
            if not isinstance(result.get("ResultFile3D"), str) or not result["ResultFile3D"]:
                raise HunyuanError("convert: response is missing ResultFile3D." + uncertainty)
        elif not isinstance(result.get("Status"), str) or result["Status"] not in {
            "WAIT",
            "RUN",
            "DONE",
            "FAIL",
        }:
            raise HunyuanError("query: response contains a missing or unknown Status.")
        # Preserve official result URLs, credit accounting, and future response fields.
        return result

    def backend_for(self, service: str, backend: Backend) -> str:
        if service not in SERVICES and service != "convert":
            raise ValueError("Unknown Hunyuan service.")
        if backend not in {"auto", "tc3"}:
            raise ValueError("backend must be tc3 (or auto).")
        if not self.settings.tc3_configured:
            raise HunyuanError(
                "Set TENCENTCLOUD_SECRET_ID and TENCENTCLOUD_SECRET_KEY in the MCP environment."
            )
        return "tc3"

    async def submit_service(
        self,
        service: Service,
        request: PayloadInput,
        *,
        backend: Backend = "tc3",
    ) -> dict:
        backend = self.backend_for(service, backend)
        payload = await asyncio.to_thread(request.to_payload)
        if service == "pro":
            if "ImageUrl" in payload:
                image = payload.pop("ImageUrl")["Url"]
                if image.startswith("data:"):
                    payload["ImageBase64"] = image.split(",", 1)[1]
                else:
                    payload["ImageUrl"] = image
        # The multi-view API limits the combined encoded images to 8 MiB.
        if payload.get("MultiViewImages"):
            images = {
                k: v
                for k, v in payload.items()
                if k in {"Image", "ImageUrl", "ImageBase64", "MultiViewImages"}
            }
            if len(json.dumps(images).encode()) > MAX_REQUEST_BYTES:
                raise ValueError("Combined multi-view images exceed 8 MiB; use smaller images.")
        result = await self._request(
            "submit",
            payload,
            action=SERVICES[service].submit,
        )
        return self.with_job_context(result, result["JobId"], service, backend)

    @staticmethod
    def with_job_context(result: dict, job_id: str, service: str, backend: str) -> dict:
        args = {"job_id": job_id, "service": service, "backend": backend}
        return {
            **result,
            "JobId": job_id,
            "service": service,
            "backend": backend,
            "query": {"tool": "hy3d_query_job", "arguments": args},
            "wait": {"tool": "hy3d_wait_job", "arguments": args},
        }

    async def convert(self, request: PayloadInput) -> dict:
        payload = await asyncio.to_thread(request.to_payload)
        return await self._request("convert", payload, action="Convert3DFormat")

    async def query(
        self,
        job_id: str,
        *,
        service: Service = "pro",
        backend: Backend = "tc3",
    ) -> dict:
        job = JobInput(job_id=job_id)
        backend = self.backend_for(service, backend)
        result = await self._request(
            "query",
            {"JobId": job.job_id},
            action=SERVICES[service].query,
        )
        return self.with_job_context(result, job.job_id, service, backend)

    async def wait(
        self,
        job_id: str,
        *,
        max_polls: int = 3,
        poll_interval_seconds: float = 10,
        service: Service = "pro",
        backend: Backend = "tc3",
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
            result = await self.query(job_id, service=service, backend=backend)
            complete = result["Status"] in TERMINAL_STATES
            if complete or poll == max_polls:
                return {**result, "polls_performed": poll, "polling_exhausted": not complete}
            await asyncio.sleep(poll_interval_seconds)
        raise AssertionError("Unreachable")
