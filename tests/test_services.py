import base64
import io
import json
from unittest.mock import AsyncMock

import httpx
import pytest
from mcp.shared.memory import create_connected_server_and_client_session
from PIL import Image
from pydantic import ValidationError

from hunyuan3d_mcp.client import HunyuanClient, HunyuanError, Settings
from hunyuan3d_mcp.server import create_server
from hunyuan3d_mcp.service_models import (
    ImageSource,
    ImageTo3DInput,
    MotionInput,
    PartsInput,
    ProfileInput,
    RapidInput,
    RigInput,
    TextureInput,
)

SETTINGS = Settings(secret_id="test-id", secret_key="test-secret", token="test-token")
FILE = {"url": "https://example.com/model.glb", "type": "GLB"}
IMAGE = {"url": "https://example.com/image.png"}

# Contract fixtures from Tencent's ai3d/v20250513 request/response models.
CASES = [
    (
        "generate_model_from_text",
        {"prompt": "椅子"},
        "pro",
        "SubmitHunyuanTo3DProJob",
        "QueryHunyuanTo3DProJob",
        {"Prompt": "椅子", "GenerateType": "Normal", "Model": "3.0"},
    ),
    (
        "generate_model_from_image",
        {"image": IMAGE},
        "pro",
        "SubmitHunyuanTo3DProJob",
        "QueryHunyuanTo3DProJob",
        {"ImageUrl": IMAGE["url"], "GenerateType": "Normal"},
    ),
    (
        "generate_model_from_sketch",
        {"image": IMAGE, "prompt": "木椅"},
        "pro",
        "SubmitHunyuanTo3DProJob",
        "QueryHunyuanTo3DProJob",
        {"ImageUrl": IMAGE["url"], "Prompt": "木椅", "GenerateType": "Sketch", "Model": "3.0"},
    ),
    (
        "generate_low_poly_model",
        {"prompt": "椅子"},
        "pro",
        "SubmitHunyuanTo3DProJob",
        "QueryHunyuanTo3DProJob",
        {"GenerateType": "LowPoly", "PolygonType": "triangle"},
    ),
    (
        "generate_geometry",
        {"prompt": "椅子"},
        "pro",
        "SubmitHunyuanTo3DProJob",
        "QueryHunyuanTo3DProJob",
        {"GenerateType": "Geometry", "EnablePBR": False},
    ),
    (
        "generate_rapid_model",
        {"image": IMAGE},
        "rapid",
        "SubmitHunyuanTo3DRapidJob",
        "QueryHunyuanTo3DRapidJob",
        {"ImageUrl": IMAGE["url"], "EnableGeometry": False},
    ),
    (
        "generate_texture",
        {"file": FILE, "prompt": "皮革", "keep_uv": True},
        "texture",
        "SubmitTextureTo3DJob",
        "DescribeTextureTo3DJob",
        {
            "File3D": {"Url": FILE["url"], "Type": "GLB"},
            "Prompt": "皮革",
            "EnableKeepUV": True,
            "TextureSize": 4096,
        },
    ),
    (
        "generate_parts",
        {
            "file": {"url": "https://example.com/model.fbx"},
            "staged": True,
            "segmentation_info": '{"parts":[]}',
        },
        "parts",
        "SubmitHunyuan3DPartJob",
        "QueryHunyuan3DPartJob",
        {
            "File": {"Url": "https://example.com/model.fbx", "Type": "FBX"},
            "Model": "1.5",
            "EnableStagedGeneration": True,
            "PartSegmentationInfo": '{"parts":[]}',
        },
    ),
    (
        "unwrap_uv",
        {"file": FILE},
        "uv",
        "SubmitHunyuanTo3DUVJob",
        "DescribeHunyuanTo3DUVJob",
        {"File": {"Url": FILE["url"], "Type": "GLB"}},
    ),
    (
        "reduce_faces",
        {"file": FILE, "face_level": "low"},
        "reduce_faces",
        "SubmitReduceFaceJob",
        "DescribeReduceFaceJob",
        {"FaceLevel": "low", "PolygonType": "triangle"},
    ),
    (
        "rig_model",
        {"file": FILE, "motion_type": 23},
        "rig",
        "SubmitAutoRiggingJob",
        "DescribeAutoRiggingJob",
        {"File3D": {"Url": FILE["url"], "Type": "GLB"}, "MotionType": 23},
    ),
    (
        "generate_motion",
        {"prompt": "人物挥手", "retarget_file": FILE},
        "motion",
        "SubmitHunyuanTo3DMotionJob",
        "DescribeHunyuanTo3DMotionJob",
        {
            "Prompt": "人物挥手",
            "Model": "HY-Motion-1.0",
            "Duration": 5,
            "RetargetFile": {"Url": FILE["url"], "Type": "GLB"},
        },
    ),
    (
        "generate_profile_model",
        {"image": IMAGE, "template": "basketball"},
        "profile",
        "SubmitProfileTo3DJob",
        "DescribeProfileTo3DJob",
        {"Profile": {"Url": IMAGE["url"]}, "Template": "basketball"},
    ),
]


@pytest.mark.parametrize("tool,request_args,service,submit_action,query_action,payload", CASES)
async def test_each_service_through_mcp(
    monkeypatch,
    tool,
    request_args,
    service,
    submit_action,
    query_action,
    payload,
):
    calls = []

    def handler(req):
        calls.append(req)
        assert str(req.url) == "https://ai3d.tencentcloudapi.com/"
        assert req.headers["X-TC-Version"] == "2025-05-13"
        assert req.headers["X-TC-Token"] == "test-token"
        assert req.headers["Authorization"].startswith("TC3-HMAC-SHA256 Credential=test-id/")
        body = json.loads(req.content)
        if len(calls) == 1:
            assert req.headers["X-TC-Action"] == submit_action
            assert all(body[key] == value for key, value in payload.items())
            return httpx.Response(200, json={"Response": {"JobId": "123", "RequestId": "r1"}})
        assert req.headers["X-TC-Action"] == query_action
        assert body == {"JobId": "123"}
        return httpx.Response(
            200,
            json={
                "Response": {
                    "Status": "DONE",
                    "ResultCreditConsumed": 20,
                    "ResultFile3Ds": [{"Type": "GLB", "Url": FILE["url"]}],
                    "PartSegmentationInfoUrl": "https://example.com/segmentation.json",
                }
            },
        )

    monkeypatch.setattr(
        "hunyuan3d_mcp.server.HunyuanClient",
        lambda config: HunyuanClient(config, transport=httpx.MockTransport(handler)),
    )
    async with create_connected_server_and_client_session(create_server(SETTINGS)) as session:
        result = await session.call_tool("hy3d_" + tool, {"request": request_args})
        assert not result.isError, result
        job = result.structuredContent
        assert job["service"] == service and job["backend"] == "tc3"
        query = await session.call_tool(job["query"]["tool"], job["query"]["arguments"])
        assert not query.isError, query
        assert query.structuredContent["ResultCreditConsumed"] == 20
        assert query.structuredContent["PartSegmentationInfoUrl"].endswith("segmentation.json")
        waited = await session.call_tool(job["wait"]["tool"], job["wait"]["arguments"])
        assert not waited.isError, waited
        assert waited.structuredContent["polling_exhausted"] is False
    assert len(calls) == 3


async def test_conversion_returns_url_without_job(monkeypatch):
    calls = []

    def handler(req):
        calls.append(req)
        assert req.headers["X-TC-Action"] == "Convert3DFormat"
        assert json.loads(req.content) == {"File3D": FILE["url"], "Format": "FBX"}
        return httpx.Response(200, json={"Response": {"ResultFile3D": "https://example.com/a.fbx"}})

    monkeypatch.setattr(
        "hunyuan3d_mcp.server.HunyuanClient",
        lambda config: HunyuanClient(
            config,
            transport=httpx.MockTransport(handler),
        ),
    )
    async with create_connected_server_and_client_session(create_server(SETTINGS)) as session:
        result = await session.call_tool(
            "hy3d_convert_format", {"request": {"file": FILE, "format": "FBX"}}
        )
        assert not result.isError
        assert result.structuredContent == {"ResultFile3D": "https://example.com/a.fbx"}
    assert len(calls) == 1


async def test_discovery_and_missing_cloud_credentials_are_local(monkeypatch):
    monkeypatch.setattr(
        "hunyuan3d_mcp.server.HunyuanClient",
        lambda config: HunyuanClient(
            config,
            transport=httpx.MockTransport(lambda _: pytest.fail("Unexpected network request")),
        ),
    )
    async with create_connected_server_and_client_session(
        create_server(Settings(api_key="test-api-key")),
    ) as session:
        tools = {tool.name: tool for tool in (await session.list_tools()).tools}
        assert len(tools) == 19
        for name, tool in tools.items():
            assert tool.description
            assert "ctx" not in tool.inputSchema["properties"]
            if name in {
                "hy3d_check_config",
                "hy3d_list_capabilities",
                "hy3d_query_job",
                "hy3d_wait_job",
            }:
                assert tool.annotations.readOnlyHint
            else:
                assert tool.annotations.idempotentHint is False
        capabilities = await session.call_tool("hy3d_list_capabilities", {})
        for item in capabilities.structuredContent["services"]:
            assert item["credentials_configured"] == (item["service"] == "pro")
            assert item["tool"] in tools
        missing = await session.call_tool(
            "hy3d_generate_texture", {"request": {"file": FILE, "prompt": "red"}}
        )
        assert missing.isError
        assert "TENCENTCLOUD_SECRET_ID" in missing.content[0].text
        invalid = await session.call_tool("hy3d_generate_parts", {"request": {"file": FILE}})
        assert invalid.isError
        wrong_query = await session.call_tool(
            "hy3d_query_job", {"job_id": "123", "service": "texture", "backend": "api_key"}
        )
        assert wrong_query.isError


def encoded_image(size=(128, 128), fmt="PNG"):
    stream = io.BytesIO()
    Image.new("RGB", size).save(stream, format=fmt)
    return base64.b64encode(stream.getvalue()).decode()


@pytest.mark.parametrize("backend", ["api_key", "tc3"])
async def test_pro_local_image_wire_shape(tmp_path, backend):
    image = tmp_path / "chair.png"
    image.write_bytes(base64.b64decode(encoded_image()))

    def handler(req):
        body = json.loads(req.content)
        if backend == "api_key":
            assert req.url.path == "/v1/ai3d/submit"
            assert body["ImageUrl"] == {"Url": "data:image/png;base64," + encoded_image()}
            assert req.headers["Authorization"] == "api-key"
        else:
            assert req.headers["X-TC-Action"] == "SubmitHunyuanTo3DProJob"
            assert body["ImageBase64"] == encoded_image()
            assert "ImageUrl" not in body
        return httpx.Response(200, json={"JobId": "123"})

    config = Settings(api_key="api-key", secret_id="test-id", secret_key="test-secret")
    async with HunyuanClient(config, transport=httpx.MockTransport(handler)) as client:
        await client.submit_service(
            "pro", ImageTo3DInput(image=ImageSource(path=str(image))), backend=backend
        )


async def test_multi_view_payload_and_api_key_rejection():
    request = ImageTo3DInput.model_validate(
        {
            "image": IMAGE,
            "model": "3.1",
            "multi_view_images": [
                {"view": "top", "image": {"base64": encoded_image((129, 129))}},
            ],
        }
    )
    calls = []

    def handler(req):
        calls.append(req)
        body = json.loads(req.content)
        assert body["MultiViewImages"] == [
            {"ViewType": "top", "ViewImageBase64": encoded_image((129, 129))}
        ]
        return httpx.Response(200, json={"JobId": "123"})

    async with HunyuanClient(SETTINGS, transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError, match="Multi-view"):
            await client.submit_service("pro", request, backend="api_key")
        await client.submit_service("pro", request, backend="tc3")
    assert len(calls) == 1


@pytest.mark.parametrize(
    "model,values",
    [
        (TextureInput, {"file": FILE}),
        (TextureInput, {"file": FILE, "prompt": "red", "image": IMAGE}),
        (TextureInput, {"file": FILE, "prompt": "red", "texture_size": 4097}),
        (
            TextureInput,
            {"file": FILE, "image": IMAGE, "multi_view_images": [{"view": "left", "image": IMAGE}]},
        ),
        (PartsInput, {"file": FILE}),
        (RapidInput, {"prompt": "x" * 201}),
        (RapidInput, {"prompt": "chair", "enable_geometry": True, "result_format": "OBJ"}),
        (RigInput, {"file": FILE, "motion_type": True}),
        (MotionInput, {"prompt": "walk", "duration": 13}),
        (ProfileInput, {"image": IMAGE, "template": "unknown"}),
        (ImageSource, {"url": "https://user:password@example.com/a.png"}),
        (ImageSource, {"url": "file:///tmp/a.png"}),
        (ImageSource, {"url": IMAGE["url"], "path": "/tmp/a.png"}),
        (ImageTo3DInput, {"image": IMAGE, "multi_view_images": [{"view": "top", "image": IMAGE}]}),
        (
            ImageTo3DInput,
            {"image": IMAGE, "multi_view_images": [{"view": "left", "image": IMAGE}] * 2},
        ),
    ],
)
def test_service_validation(model, values):
    with pytest.raises(ValidationError):
        model.model_validate(values)


@pytest.mark.parametrize(
    "kind,size,fmt",
    [
        ("texture", (128, 128), "PNG"),
        ("texture", (4096, 129), "PNG"),
        ("texture", (129, 129), "WEBP"),
        ("profile", (500, 501), "PNG"),
        ("view", (128, 129), "PNG"),
        ("view", (129, 129), "WEBP"),
    ],
)
def test_per_service_image_constraints(kind, size, fmt):
    with pytest.raises(ValueError):
        ImageSource(base64=encoded_image(size, fmt)).payload(kind=kind)


async def test_texture_image_and_extended_options():
    request = TextureInput.model_validate(
        {
            "file": FILE,
            "image": {"base64": encoded_image((129, 129))},
            "model": "3.1",
            "multi_view_images": [{"view": "back", "image": IMAGE}],
            "enable_pbr": True,
        }
    )
    body = request.to_payload()
    assert body["Image"] == {"Base64": encoded_image((129, 129))}
    assert body["MultiViewImages"] == [{"ViewType": "back", "ViewImageUrl": IMAGE["url"]}]
    assert body["EnablePBR"] is True


@pytest.mark.parametrize("kind", ["timeout", "http", "json", "missing_job", "business"])
async def test_tc3_errors_redact_secrets_and_never_resubmit(kind):
    calls = []

    def handler(req):
        calls.append(req)
        if kind == "timeout":
            raise httpx.ReadTimeout("test-secret")
        if kind == "http":
            return httpx.Response(503, text="test-secret")
        if kind == "json":
            return httpx.Response(200, text="test-token")
        if kind == "business":
            return httpx.Response(
                200,
                json={
                    "Response": {
                        "Error": {
                            "Code": "AuthFailure",
                            "Message": "test-id test-secret test-token",
                        }
                    }
                },
            )
        return httpx.Response(200, json={"Response": {}})

    async with HunyuanClient(SETTINGS, transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(HunyuanError) as error:
            await client.submit_service(
                "parts", PartsInput(file={"url": "https://example.com/a.fbx"})
            )
        assert all(
            secret not in str(error.value) for secret in ("test-secret", "test-token", "test-id")
        )
        if kind != "business":
            assert "Do not automatically resubmit" in str(error.value)
    assert len(calls) == 1


async def test_pending_cloud_job_keeps_route_across_polling(monkeypatch):
    sleep = AsyncMock()
    monkeypatch.setattr("hunyuan3d_mcp.client.asyncio.sleep", sleep)
    calls = []

    def handler(req):
        calls.append(req)
        assert req.headers["X-TC-Action"] == "QueryHunyuan3DPartJob"
        return httpx.Response(200, json={"Status": "RUN"})

    async with HunyuanClient(SETTINGS, transport=httpx.MockTransport(handler)) as client:
        result = await client.wait("123", service="parts", backend="tc3", max_polls=2)
    assert result["polling_exhausted"] is True and len(calls) == 2
    assert result["wait"]["arguments"] == {"job_id": "123", "service": "parts", "backend": "tc3"}
    sleep.assert_awaited_once_with(10)


def test_cloud_config_secrets_remain_private(monkeypatch):
    monkeypatch.setenv("TENCENTCLOUD_SECRET_ID", "test-id")
    monkeypatch.setenv("TENCENTCLOUD_SECRET_KEY", "test-secret")
    monkeypatch.setenv("TENCENTCLOUD_TOKEN", "test-token")
    config = Settings.from_env()
    rendered = json.dumps(config.public_info()) + repr(config)
    assert all(secret not in rendered for secret in ("test-id", "test-secret", "test-token"))
    assert config.public_info()["tc3_configured"] is True
    assert "texture" in config.public_info()["available_services"]
    assert not Settings(secret_id="test-id").tc3_configured


def test_tc3_signature_matches_official_sdk_vector():
    # Golden signature computed with Tencent SDK AbstractClient._get_tc3_signature
    # and Sign.sign_tc3, using exactly these UTF-8 body bytes (2024-07-03 UTC).
    from hunyuan3d_mcp.auth import tc3_headers

    headers = tc3_headers(
        '{"Prompt":"椅子"}'.encode(),
        "SubmitHunyuanTo3DProJob",
        "test-id",
        "test-secret",
        1720000000,
        token="test-token",
        region="ap-guangzhou",
    )
    assert headers["Authorization"] == (
        "TC3-HMAC-SHA256 Credential=test-id/2024-07-03/ai3d/tc3_request, "
        "SignedHeaders=content-type;host, "
        "Signature=c9acbfca7186f249240ac3b42e9cd9c320c97befca9d8b38d8656483c9275faa"
    )
    assert headers["X-TC-Token"] == "test-token"
    assert headers["X-TC-Region"] == "ap-guangzhou"


def test_cli_check_config_accepts_cloud_credentials_without_api_key(monkeypatch, capsys):
    from hunyuan3d_mcp.__main__ import main

    monkeypatch.setenv("TENCENTCLOUD_SECRET_ID", "test-id")
    monkeypatch.setenv("TENCENTCLOUD_SECRET_KEY", "test-secret")
    monkeypatch.setattr("sys.argv", ["hunyuan3d-mcp", "--check-config"])
    main()
    result = json.loads(capsys.readouterr().out)
    assert result["tc3_configured"] is True
    assert result["api_key_configured"] is False
