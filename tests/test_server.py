import json

import httpx
from mcp.shared.memory import create_connected_server_and_client_session

from hunyuan3d_mcp.client import HunyuanClient, Settings
from hunyuan3d_mcp.server import create_server


async def test_mcp_generation_workflow_with_mock_http(monkeypatch):
    calls = []

    def handler(request):
        calls.append(request)
        if request.headers["X-TC-Action"] == "SubmitHunyuanTo3DProJob":
            assert json.loads(request.content)["ImageUrl"] == "https://example.com/chair.png"
            return httpx.Response(200, json={"Response": {"JobId": "123"}})
        assert json.loads(request.content) == {"JobId": "123"}
        return httpx.Response(
            200,
            json={
                "Response": {
                    "Status": "DONE",
                    "ResultCreditConsumed": 20,
                    "ResultFile3Ds": [{"Type": "GLB", "Url": "https://example.com/chair.glb"}],
                }
            },
        )

    monkeypatch.setattr(
        "hunyuan3d_mcp.server.HunyuanClient",
        lambda config: HunyuanClient(config, transport=httpx.MockTransport(handler)),
    )
    server = create_server(Settings(secret_id="test-id", secret_key="test-secret"))
    async with create_connected_server_and_client_session(server) as session:
        submitted = await session.call_tool(
            "hy3d_generate_model_from_image",
            {"image": {"url": "https://example.com/chair.png"}},
        )
        assert not submitted.isError
        job_id = submitted.structuredContent["JobId"]
        queried = await session.call_tool("hy3d_query_job", {"job_id": job_id})
        assert not queried.isError
        assert queried.structuredContent["ResultCreditConsumed"] == 20
        waited = await session.call_tool("hy3d_wait_job", {"job_id": job_id, "max_polls": 1})
        assert not waited.isError
        assert waited.structuredContent["Status"] == "DONE"
        assert waited.structuredContent["polls_performed"] == 1
    assert len(calls) == 3


async def test_mcp_business_error(monkeypatch):
    monkeypatch.setattr(
        "hunyuan3d_mcp.server.HunyuanClient",
        lambda config: HunyuanClient(
            config,
            transport=httpx.MockTransport(
                lambda _: httpx.Response(
                    200,
                    json={
                        "Response": {
                            "Error": {"Code": "FailedOperation.JobNotFound", "Message": "missing"},
                            "RequestId": "test-request",
                        }
                    },
                )
            ),
        ),
    )
    async with create_connected_server_and_client_session(
        create_server(Settings(secret_id="test-id", secret_key="test-secret"))
    ) as session:
        result = await session.call_tool("hy3d_query_job", {"job_id": "0"})
        assert result.isError
        assert "FailedOperation.JobNotFound" in result.content[0].text
        assert "test-request" in result.content[0].text
