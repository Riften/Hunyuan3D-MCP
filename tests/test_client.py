import asyncio
import json
from unittest.mock import AsyncMock

import httpx
import pytest

from hunyuan3d_mcp.__main__ import probe
from hunyuan3d_mcp.client import HunyuanClient, HunyuanError, Settings
from hunyuan3d_mcp.models import GenerationInput

KEY = "sk-test-only-not-a-real-key"


def make_client(handler):
    return HunyuanClient(Settings(api_key=KEY), transport=httpx.MockTransport(handler))


async def test_submit_wire_contract():
    calls = []

    def handler(request):
        calls.append(request)
        assert str(request.url) == "https://api.ai3d.cloud.tencent.com/v1/ai3d/submit"
        assert request.headers["Authorization"] == KEY
        assert request.headers["Content-Type"] == "application/json"
        assert json.loads(request.content)["Prompt"] == "chair"
        return httpx.Response(200, json={"Response": {"JobId": "123", "RequestId": "request-1"}})

    async with make_client(handler) as client:
        assert await client.submit(GenerationInput(prompt="chair")) == {
            "JobId": "123",
            "RequestId": "request-1",
        }
    assert len(calls) == 1


async def test_query_preserves_files_credits_and_failure():
    files = [{"Type": "GLB", "Url": "https://example.com/model.glb"}]
    response = {
        "Status": "DONE",
        "ResultFile3Ds": files,
        "ResultCreditConsumed": 20,
        "ResultCreditDetails": '{"GenerateType-Normal":20}',
    }

    def handler(request):
        assert request.url.path == "/v1/ai3d/query"
        assert json.loads(request.content) == {"JobId": "123"}
        return httpx.Response(200, json=response)

    async with make_client(handler) as client:
        assert await client.query("123") == {**response, "JobId": "123"}
        response = {"Status": "FAIL", "ErrorCode": "GenerationFailed", "ErrorMessage": "Failed"}
        assert (await client.query("123"))["ErrorCode"] == "GenerationFailed"


@pytest.mark.parametrize("kind", ["network", "timeout", "http", "redirect", "json", "missing_job"])
async def test_uncertain_submissions_never_retry(kind):
    calls = []

    def handler(request):
        calls.append(request)
        if kind == "network":
            raise httpx.ConnectError("secret=" + KEY)
        if kind == "timeout":
            raise httpx.ReadTimeout("secret=" + KEY)
        if kind == "http":
            return httpx.Response(503, text=KEY)
        if kind == "redirect":
            return httpx.Response(307, headers={"Location": "https://other.example.com"})
        if kind == "json":
            return httpx.Response(200, text=KEY)
        return httpx.Response(200, json={"Response": {}})

    async with make_client(handler) as client:
        with pytest.raises(HunyuanError, match="Do not automatically resubmit") as error:
            await client.submit(GenerationInput(prompt="chair"))
        assert KEY not in str(error.value)
    assert len(calls) == 1


async def test_business_error_redacts_key_and_keeps_request_id():
    async with make_client(
        lambda _: httpx.Response(
            200,
            json={
                "Response": {
                    "Error": {"Code": "FailedOperation.JobNotFound", "Message": KEY},
                    "RequestId": "r1",
                }
            },
        )
    ) as client:
        with pytest.raises(HunyuanError, match="FailedOperation.JobNotFound") as error:
            await client.query("0")
        assert KEY not in str(error.value)
        assert "RequestId: r1" in str(error.value)


@pytest.mark.parametrize(
    "response", [[], {"Response": None}, {"Status": "UNKNOWN"}, {"Status": []}, {}]
)
async def test_malformed_query_response(response):
    async with make_client(lambda _: httpx.Response(200, json=response)) as client:
        with pytest.raises(HunyuanError):
            await client.query("123")


async def test_missing_key_does_not_send():
    def handler(_):
        pytest.fail("No request should be sent without an API Key")

    async with HunyuanClient(Settings(), transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(HunyuanError, match="HY3D_API_KEY"):
            await client.query("123")


@pytest.mark.parametrize(
    "states,expected_polls,exhausted",
    [
        (["DONE"], 1, False),
        (["FAIL"], 1, False),
        (["WAIT", "RUN", "DONE"], 3, False),
        (["RUN", "RUN", "RUN"], 3, True),
    ],
)
async def test_bounded_polling(monkeypatch, states, expected_polls, exhausted):
    sleep = AsyncMock()
    monkeypatch.setattr("hunyuan3d_mcp.client.asyncio.sleep", sleep)
    values = iter(states)
    async with make_client(lambda _: httpx.Response(200, json={"Status": next(values)})) as client:
        result = await client.wait("123")
    assert result["polls_performed"] == expected_polls
    assert result["polling_exhausted"] is exhausted
    assert sleep.await_count == expected_polls - 1
    if expected_polls > 1:
        sleep.assert_awaited_with(10)


async def test_poll_errors_stop_without_retry():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(429)

    async with make_client(handler) as client:
        with pytest.raises(HunyuanError, match="429"):
            await client.wait("123")
    assert len(calls) == 1


async def test_cancellation_propagates(monkeypatch):
    monkeypatch.setattr(
        "hunyuan3d_mcp.client.asyncio.sleep", AsyncMock(side_effect=asyncio.CancelledError)
    )
    async with make_client(lambda _: httpx.Response(200, json={"Status": "RUN"})) as client:
        with pytest.raises(asyncio.CancelledError):
            await client.wait("123")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_polls": 0},
        {"max_polls": 11},
        {"max_polls": True},
        {"poll_interval_seconds": 4},
        {"poll_interval_seconds": float("nan")},
    ],
)
async def test_invalid_poll_options(kwargs):
    async with make_client(lambda _: pytest.fail("Unexpected network call")) as client:
        with pytest.raises(ValueError):
            await client.wait("123", **kwargs)


def test_settings_hide_credentials(monkeypatch):
    monkeypatch.setenv("HY3D_API_KEY", KEY)
    monkeypatch.setenv("HY3D_PROXY", "http://user:password@127.0.0.1:7897")
    settings = Settings.from_env()
    public = json.dumps(settings.public_info()) + repr(settings)
    assert KEY not in public and "password" not in public
    assert settings.public_info()["api_key_configured"] is True
    assert settings.public_info()["network_checked"] is False


@pytest.mark.parametrize("value", ["nan", "inf", "0", "121", "abc"])
def test_invalid_timeout(monkeypatch, value):
    monkeypatch.setenv("HY3D_TIMEOUT_SECONDS", value)
    with pytest.raises(HunyuanError):
        Settings.from_env()


async def test_probe_uses_one_query_only(monkeypatch):
    query = AsyncMock(side_effect=HunyuanError("query: FailedOperation.JobNotFound: missing"))
    monkeypatch.setattr(HunyuanClient, "query", query)
    result = await probe(Settings(api_key=KEY))
    query.assert_awaited_once_with("0")
    assert result["authenticated"] is True
    assert result["generation_jobs_created"] == 0
