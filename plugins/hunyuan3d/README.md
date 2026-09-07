# Hunyuan 3D MCP

A standalone Python MCP server and Codex plugin for Tencent Hunyuan 3D Pro.
Supports text-to-3D, image-to-3D, job queries, and bounded polling over STDIO.
This is a community integration, not an official Tencent plugin.

## Requirements

- Python 3.11 or newer.
- [uv](https://docs.astral.sh/uv/getting-started/installation/) on the agent's PATH for plugin mode.
- Your own Tencent Hunyuan 3D API Key in `HY3D_API_KEY` in the agent environment.
- Network access to the dependency registry on first launch and to Tencent for API calls.

## Codex Plugin

Install `hunyuan3d` from the repository's `hunyuan3d` marketplace, then start a new session.
The bundled `.mcp.json` starts this package from `${PLUGIN_ROOT}` using `uv.lock`.
The virtual environment is stored in `${PLUGIN_DATA}/venv`; no checkout-specific path is needed.
The plugin forwards `HY3D_API_KEY` without storing its value in configuration files.
The marketplace policy does not provision Tencent credentials or provide an OAuth flow.

Call `hy3d_check_config` after installation. Installation and tool discovery do not submit jobs.

## Standalone Package

From this package directory:

```bash
uv tool install .
hunyuan3d-mcp --check-config
```

Alternatively, install with `python -m pip install .` in a Python environment.
Configure any STDIO MCP client with command `hunyuan3d-mcp` and forward `HY3D_API_KEY`.
Ensure the command is on that client's PATH. `python -m hunyuan3d_mcp` is an equivalent entry point.
The server does not load `.env` automatically.

## Tools

| Tool | Behavior |
| --- | --- |
| `hy3d_check_config` | Inspect configuration without network access or exposing credentials |
| `hy3d_submit_job` | Submit one potentially billable job; never automatically retry |
| `hy3d_query_job` | Query an existing JobId once; return status, files, and credit usage |
| `hy3d_wait_job` | Poll an existing job, default at most 3 queries spaced 10 seconds apart |

For text generation call `hy3d_submit_job` with `{"request":{"prompt":"A modern office chair"}}`.
For images use one of `image_url`, `image_path` (absolute path), or `image_base64` instead of `prompt`.
Image inputs are uploaded to Tencent. Models `3.0` and `3.1` are supported; `LowPoly` and `Sketch`
require `3.0`. Save the returned JobId and reuse it for all queries. `DONE` and `FAIL` are terminal;
`WAIT` and `RUN` are pending. Result URLs should be downloaded promptly.

If submission times out, check the Tencent console before resubmitting to avoid duplicate charges.
Default request timeout is 30 seconds (`HY3D_TIMEOUT_SECONDS`, range 1-120).
Allow at least 180 seconds for tool calls using default bounded polling.

## API

The API Key endpoint is `https://api.ai3d.cloud.tencent.com` with `POST /v1/ai3d/submit`
and `POST /v1/ai3d/query`. Authentication is `Authorization: <HY3D_API_KEY>`, without `Bearer`.
This endpoint supports Pro only; TC3 authentication and Rapid are not implemented.

- [API Key compatibility endpoint](https://cloud.tencent.com/document/product/1804/126189)
- [API Key management](https://cloud.tencent.com/document/product/1804/126325)
- [Pro submission](https://cloud.tencent.com/document/api/1804/123447)
- [Pro query](https://cloud.tencent.com/document/api/1804/123448)
