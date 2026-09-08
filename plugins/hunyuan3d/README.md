# Hunyuan 3D MCP

A standalone Python MCP server and Codex plugin for Tencent Hunyuan 3D.
Provides 14 service tools, a capability guide, configuration checks and shared job polling over STDIO.
This is a community integration, not an official Tencent plugin.

## Requirements

- Python 3.11 or newer.
- [uv](https://docs.astral.sh/uv/getting-started/installation/) on the agent's PATH for plugin mode.
- Credentials in the agent environment: `TENCENTCLOUD_SECRET_ID` for Tencent Cloud services.
- Network access to the dependency registry on first launch and to Tencent for API calls.

## Codex Plugin

Install `hunyuan3d` from the repository's `hunyuan3d` marketplace, then start a new session.
The bundled `.mcp.json` starts from the installed plugin root using a relative working directory
and `uv.lock`. `uv` creates an isolated `.venv` in that installed plugin copy; no
checkout-specific path is embedded in the configuration.
The plugin forwards the credential environment variables without storing their values in configuration files.
The marketplace policy does not provision Tencent credentials or provide an OAuth flow.

Call `hy3d_check_config` after installation. Installation and tool discovery do not submit jobs.

## Standalone Package

From this package directory:

```bash
uv tool install .
hunyuan3d-mcp --check-config
```

Alternatively, install with `python -m pip install .` in a Python environment.
Configure any STDIO MCP client with command `hunyuan3d-mcp` and forward the credential environment variables below.
Ensure the command is on that client's PATH. `python -m hunyuan3d_mcp` is an equivalent entry point.
The server does not load `.env` automatically.

## Credentials and service availability

All services use Tencent Cloud API `ai3d`, version `2025-05-13`, with TC3-HMAC-SHA256 signing.
Configure the MCP process with:

```bash
export TENCENTCLOUD_SECRET_ID='your-secret-id'
export TENCENTCLOUD_SECRET_KEY='your-secret-key'
# Temporary credentials only:
# export TENCENTCLOUD_TOKEN='your-session-token'
# Optional region:
# export TENCENTCLOUD_REGION='ap-guangzhou'
```

`hy3d_check_config` reports credential presence without exposing secrets or making requests.
Presence does not verify account permission, service entitlement or quota.
`hy3d_list_capabilities` provides examples, workflow guidance, motion presets and portrait templates.
All service tools use Tencent Cloud TC3; `backend` defaults to `tc3`.

## Service tools

Every service tool has a typed `request` object in its MCP input schema, including parameter
explanations, enums, defaults and constraints. No separate documentation is required to discover
how to call a service. Unknown fields and invalid input combinations fail before submission.

| Tool | Input and purpose | Service / authentication |
| --- | --- | --- |
| `hy3d_generate_model_from_text` | Text → textured model; Pro 3.0/3.1, PBR optional | `pro`, TC3 |
| `hy3d_generate_model_from_image` | Main image → model, optional additional views | `pro`, TC3; multi-view requires TC3 |
| `hy3d_generate_model_from_sketch` | Sketch + optional prompt → model; Pro 3.0 | `pro`, TC3 |
| `hy3d_generate_low_poly_model` | Text OR image → new low-poly model; Pro 3.0 | `pro`, TC3 |
| `hy3d_generate_geometry` | Text OR image → untextured mesh | `pro`, TC3 |
| `hy3d_generate_rapid_model` | Text OR image → Rapid model | `rapid`, TC3 |
| `hy3d_generate_texture` | Existing OBJ/GLB + prompt OR image → textured model | `texture`, TC3 |
| `hy3d_generate_parts` | Existing FBX → semantic components; optional staged segmentation | `parts`, TC3 |
| `hy3d_unwrap_uv` | Existing FBX/OBJ/GLB → UV-unwrapped mesh | `uv`, TC3 |
| `hy3d_reduce_faces` | Existing OBJ/GLB → simplified topology | `reduce_faces`, TC3 |
| `hy3d_rig_model` | Character FBX/GLB → rigged/skinned character; optional preset motion | `rig`, TC3 |
| `hy3d_generate_motion` | Text → 1–12 second animation; optional Hunyuan character retargeting | `motion`, TC3 |
| `hy3d_generate_profile_model` | Portrait + template → stylized person | `profile`, TC3 |
| `hy3d_convert_format` | FBX/OBJ/GLB → STL/USDZ/FBX or MP4/GIF preview | Synchronous, TC3 |

Utility tools: `hy3d_check_config`, `hy3d_list_capabilities`, `hy3d_query_job`,
`hy3d_wait_job`, and the unified Tencent Cloud TC3 tools.

### Inputs

Images use exactly one of `{"url":"https://..."}`, `{"path":"/absolute/path/image.png"}`,
or `{"base64":"..."}`. Raw base64 and image data URIs are supported. Local images are validated,
encoded and uploaded to Tencent. Generation supports JPEG/PNG/WebP, 128–5000 pixels per side,
with local files at most 6 MiB. Texture references require JPEG/PNG, 129–4095 pixels;
portraits require JPEG/PNG, 501–4095 pixels; their base64 must be smaller than 10 MiB.
Additional views require JPEG/PNG, 129–4999 pixels and at most 8 MiB combined encoded images.
Public URL images are fetched by Tencent; the server cannot pre-validate their contents.

Existing models use `{"url":"https://.../model.glb","type":"GLB"}`. URLs must be reachable
by Tencent and free of embedded credentials. Upload local model files to accessible storage first;
this server does not provide model storage/upload. File formats are service-specific: components
require FBX; texturing and reduction accept OBJ/GLB. Rigging and conversion accept files up to 60 MB.
Signed storage URLs are allowed, and their validity must cover the remote processing period.

### Example: generate geometry, then texture it

Call `hy3d_generate_geometry`:

```json
{"request":{"prompt":"一把现代办公椅","model":"3.1"},"backend":"tc3"}
```

A successful submission includes the original API fields and reusable routing information:

```json
{
  "JobId":"123",
  "service":"pro",
  "backend":"tc3",
  "query":{"tool":"hy3d_query_job","arguments":{"job_id":"123","service":"pro","backend":"tc3"}},
  "wait":{"tool":"hy3d_wait_job","arguments":{"job_id":"123","service":"pro","backend":"tc3"}}
}
```

Copy `query.arguments` into `hy3d_query_job` or `wait.arguments` into `hy3d_wait_job`.
`WAIT`/`RUN` are pending; `DONE`/`FAIL` are terminal. `polling_exhausted: true` means the job is
still pending, not cancelled. After `DONE`, select a GLB from `ResultFile3Ds`, then call
`hy3d_generate_texture` with its actual URL:

```json
{"request":{"file":{"url":"https://example.com/generated-chair.glb","type":"GLB"},"prompt":"棕色皮革坐垫和拉丝金属椅脚","enable_pbr":true}}
```

The texture submission returns `service: "texture"`, `backend: "tc3"` and its own JobId.
Reuse **that submission's** query/wait arguments. JobIds alone do not identify a service;
querying the wrong service or authentication backend will not find the task. The routing
information is returned explicitly and works across server restarts, with no in-memory job registry.

### Example: component generation

Convert a GLB to FBX with `hy3d_convert_format`:

```json
{"request":{"file":{"url":"https://example.com/model.glb","type":"GLB"},"format":"FBX"}}
```

Conversion returns `ResultFile3D` directly, without JobId or polling. Pass that URL to
`hy3d_generate_parts`:

```json
{"request":{"file":{"url":"https://example.com/converted-model.fbx","type":"FBX"}}}
```

For editable segmentation, set `staged: true`, wait for completion and download
`PartSegmentationInfoUrl`. Submit the returned model plus the edited segmentation **contents**
in `segmentation_info` to generate the edited components. `postprocess: true` returns a single
processed model link and adds 20 credits according to the API documentation.

### Polling, results and errors

All generation operations create one potentially billable task and return immediately.
No generation or conversion request is automatically retried. After an uncertain submission
error or timeout, check the Tencent console before resubmitting to avoid duplicate charges.
Raw file URLs, previews, errors, credit accounting and segmentation result fields are preserved.
Download results promptly; job IDs and result URLs generally remain valid for 24 hours.

`hy3d_wait_job` defaults to at most 3 queries spaced 10 seconds apart. Request timeout defaults
to 30 seconds (`HY3D_TIMEOUT_SECONDS`, range 1–120). Allow at least 180 seconds for a tool call
with default polling. Longer polling settings may require increasing the client's tool timeout.
`HY3D_PROXY` or standard proxy environment variables configure HTTP access.

## API references and verification

- [Tencent Cloud AI3D API](https://cloud.tencent.com/document/product/1804/126189)
- [Pro submission](https://cloud.tencent.com/document/api/1804/123447)
- [Pro query](https://cloud.tencent.com/document/api/1804/123448)
- [Official Tencent AI3D SDK request/response models](https://github.com/TencentCloud/tencentcloud-sdk-python/blob/master/tencentcloud/ai3d/v20250513/models.py)
- [Official Tencent TC3 implementation](https://github.com/TencentCloud/tencentcloud-sdk-python/blob/master/tencentcloud/common/abstract_client.py)

API contracts were checked against the official documentation and SDK on 2026-09-08.
TC3 calls use
`https://ai3d.tencentcloudapi.com/`, version `2025-05-13`, with distinct submit/query Actions.
Tests use mock HTTP and an official-SDK signature vector; they do not submit paid live jobs.
