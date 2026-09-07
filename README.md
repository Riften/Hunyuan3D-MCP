# Hunyuan 3D MCP Server

通过 MCP STDIO 为 Codex、Claude Code、Cursor 等 code agent 提供腾讯混元生 3D **专业版**生成服务。支持作为 Python 包独立安装，或通过仓库内的 **Codex plugin marketplace** 安装。默认读取 `HY3D_API_KEY`，使用官方 Python MCP SDK。本项目为社区集成，并非腾讯官方插件。

## 接口与认证

腾讯提供两套入口，认证方式不能混用。本项目实现的是官方 **API Key / OpenAI 兼容入口**：

| 项目 | 本项目使用的值 |
| --- | --- |
| 服务地址 | `https://api.ai3d.cloud.tencent.com` |
| 提交任务 | `POST /v1/ai3d/submit` |
| 查询任务 | `POST /v1/ai3d/query` |
| 认证 | `Authorization: <HY3D_API_KEY>`，不加 `Bearer` |
| 版本 | 专业版，模型 `3.0`（默认）或 `3.1` |

[API 文档](https://cloud.tencent.com/document/api/1804/)还包含使用 SecretId/SecretKey 和 TC3 签名的 `ai3d.tencentcloudapi.com` 入口。API Key 不能直接用于该入口。本项目不实现 TC3、极速版或其他后处理接口。

认证与兼容格式依据[腾讯官方调用示例](https://cloud.tencent.com/document/product/1804/126189)，Key 的获取参见 [API Key 管理](https://cloud.tencent.com/document/product/1804/126325)。腾讯文档提示服务逐步迁移到 TokenHub，已有服务暂不受影响；本项目没有假设 TokenHub 与此入口可互换。

## 安装前提

支持 Python 3.11+ 的 Windows、macOS 和 Linux 环境。插件安装需要 [uv](https://docs.astral.sh/uv/getting-started/installation/) 和支持 `codex plugin` 命令的 Codex 版本；Git marketplace 还需要 Git。请确保这些命令在 agent 进程的 `PATH` 中。

在启动 agent 的环境中设置自己的 `HY3D_API_KEY`。首次启动会下载 Python 依赖，后续 API 调用需要能访问腾讯服务。插件不会创建或代管腾讯 API Key，也不提供 OAuth 登录流程。

## Codex Marketplace 安装

本仓库已经包含 marketplace 清单和完整插件。发布到 Git 托管平台后，将 `<repository-url>` 替换为实际仓库 URL：

```bash
codex plugin marketplace add <repository-url>
codex plugin add hunyuan3d@hunyuan3d
```

如果已经克隆仓库，也可直接在仓库根目录运行：

```bash
codex plugin marketplace add .
codex plugin add hunyuan3d@hunyuan3d
```

安装后新建 Codex 会话，通过 `/plugins` 查看插件，调用 `hy3d_check_config` 检查 Key 是否可用。插件已配置 MCP 启动命令、环境变量转发和超时，不需要再手动注册相同的 MCP Server。

插件通过 `${PLUGIN_ROOT}` 定位安装后的源码，并使用 `uv.lock` 安装依赖；虚拟环境存放在 `${PLUGIN_DATA}/venv`，不依赖源码检出位置或预先配置的虚拟环境。首次启动较慢时，可按[发布与部署说明](docs/distribution.md)预装依赖。

这是可由 Git 仓库分发的 Codex marketplace，不代表已上架 OpenAI 官方公共目录。仓库 URL 在发布时确定，不在清单中绑定特定账号。Codex IDE 扩展等不支持插件的客户端可以使用以下独立 MCP 安装方式。

## 独立 MCP 安装

在仓库根目录运行：

```bash
uv tool install ./plugins/hunyuan3d
hunyuan3d-mcp --check-config
```

`uv tool install` 将命令安装到独立环境；如 `PATH` 尚未配置，可运行 `uv tool update-shell`，然后重新打开终端。也可在自己管理的 Python 环境中运行 `python -m pip install ./plugins/hunyuan3d`。源码包位于 `plugins/hunyuan3d`，无需先发布到 PyPI。

`--check-config` 不联网、不输出密钥；Key 缺失时退出码为 1。默认无参数启动 STDIO 服务，`python -m hunyuan3d_mcp` 是等价入口。

## 环境配置

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `HY3D_API_KEY` | 无 | 腾讯混元生 3D API Key；调用接口时必需 |
| `HY3D_PROXY` | 无 | 可选 HTTP 代理，优先于标准代理环境变量 |
| `HY3D_TIMEOUT_SECONDS` | `30` | 每次 API 请求的总超时，允许 1–120 秒 |
| `HTTPS_PROXY` / `HTTP_PROXY` / `ALL_PROXY` / `NO_PROXY` | 系统环境 | HTTPX 标准代理配置；支持小写形式 |

`.env.example` 仅作说明，程序**不会自动加载 `.env`**。请由启动 agent 的终端或环境管理器注入 Key。图形界面启动的 agent 可能看不到 shell 中的变量，需要从已配置环境的终端启动或通过其环境配置注入。不要把真实 Key 写进项目、版本库或命令行参数。

## 注册到 Codex

独立安装后，可在 Codex 的 `config.toml` 中添加以下配置，或参考 [examples/codex.toml](examples/codex.toml)：

```toml
[mcp_servers.hunyuan3d]
command = "hunyuan3d-mcp"
env_vars = ["HY3D_API_KEY", "HY3D_PROXY", "HY3D_TIMEOUT_SECONDS", "HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY", "NO_PROXY"]
startup_timeout_sec = 20
tool_timeout_sec = 180
```

`env_vars` 显式转发父进程环境变量，不把 Key 值存入 TOML。也可以先运行 CLI 注册，再在生成的配置项里加入上述 `env_vars` 和超时配置：

```bash
codex mcp add hunyuan3d -- hunyuan3d-mcp
codex mcp list
codex mcp get hunyuan3d
```

重启 Codex 会话后使用 `/mcp` 检查连接，并调用 `hy3d_check_config`。`--check-config` 不能写进 MCP 启动参数，否则进程只会输出普通 JSON 后退出。配置文件位置和作用域参见 [Codex 官方 MCP 文档](https://developers.openai.com/codex/mcp)。

## 注册到其他 Agent

### Claude Code

从已包含 `HY3D_API_KEY`（及可选代理）的终端运行：

```bash
claude mcp add --transport stdio --scope user hunyuan3d -- hunyuan3d-mcp
claude mcp list
```

重启会话并使用 `/mcp` 验证。如客户端会过滤父进程环境变量，需在客户端的环境配置中转发 `HY3D_API_KEY`。遇到长轮询超时，使用 `hy3d_query_job` 单次查询或减少 `max_polls`。其他支持 `mcpServers` 的客户端可参考 [examples/claude-code.json](examples/claude-code.json)。

### Cursor

将 [examples/cursor.json](examples/cursor.json) 的内容加入 Cursor 的 MCP 配置。示例通过 `${env:HY3D_API_KEY}` 读取环境变量：

```json
{
  "mcpServers": {
    "hunyuan3d": {
      "command": "hunyuan3d-mcp",
      "env": { "HY3D_API_KEY": "${env:HY3D_API_KEY}" }
    }
  }
}
```

在 Cursor 的 MCP 设置中启用并检查工具列表。其他 MCP 客户端使用同一 STDIO 命令即可；环境变量插值语法由客户端决定，`${env:...}` 不应直接复制给不支持该语法的客户端。

本项目提供注册说明与示例，不会自动修改用户现有的 agent 配置。

## 工具与工作流

| 工具 | 用途 | 网络与额度 |
| --- | --- | --- |
| `hy3d_check_config` | 检查本地配置，隐藏 Key | 不联网 |
| `hy3d_submit_job` | 提交一个专业版生成任务 | 1 次提交，可能计费；不自动重试 |
| `hy3d_query_job` | 查询现有任务，返回状态、模型链接、积分明细 | 1 次查询，不创建生成任务 |
| `hy3d_wait_job` | 有上限地轮询现有任务 | 默认最多 3 次查询，间隔 10 秒 |

建议先检查配置，然后提交一次并保存返回的 `JobId`，之后始终查询同一任务。`WAIT` / `RUN` 表示未完成，`DONE` / `FAIL` 为终态。`FAIL` 时保留 `ErrorCode` 和 `ErrorMessage`；成功时保留 `ResultFile3Ds`、`ResultCreditConsumed`、`ResultCreditDetails` 及 `RequestId`。

文生 3D 的 MCP 工具参数：

```json
{
  "request": {
    "prompt": "一把现代办公椅，灰色坐垫，金属底座",
    "model": "3.0",
    "generate_type": "Normal"
  }
}
```

使用图片 URL（替换为腾讯可访问的实际图片链接）：

```json
{
  "request": {
    "image_url": "https://example.com/chair.png",
    "model": "3.1",
    "enable_pbr": true
  }
}
```

也支持 `image_path`（MCP 进程所在机器上的绝对文件路径）或 `image_base64`（原始 base64 / `data:image/...;base64,...`）。本地文件在服务端编码后上传至腾讯，不需要 agent 把大量 base64 写入上下文。兼容入口使用 `ImageUrl.Url`，本地图片统一转换为 data URI。

输入校验在提交前执行：图片为 JPEG/PNG/WebP，各边 128–5000 像素，原始数据最多 6 MiB，完整 JSON 最多 8 MiB。远程 URL 图片由腾讯读取，本地不会预下载；远程图片的实际尺寸和大小由腾讯验证。文字最多 1024 字符；文字和图片仅可在 `Sketch` 下组合；3.1 在兼容入口不支持 `LowPoly` / `Sketch`。当前工具支持单图，不封装多视角输入。

高级可选项包括 `face_count`（3000–1500000）、`polygon_type`（仅 LowPoly）、`result_format`（STL / USDZ / FBX）。不设置 `result_format` 时由腾讯返回默认 OBJ/GLB，Geometry 默认 GLB。PBR、面数和生成模式可能影响实际积分消耗，以腾讯的计费规则和返回明细为准。

查询参数：

```json
{ "job_id": "返回的数字字符串 JobId" }
```

有限轮询参数：

```json
{ "job_id": "返回的数字字符串 JobId", "max_polls": 3, "poll_interval_seconds": 10 }
```

`polling_exhausted: true` 表示达到查询上限，任务仍在云端继续执行。JobId 按文档有效期为 24 小时。结果链接应及时下载保存；本服务返回链接，不自动下载文件。OBJ 的链接可能是包含贴图的 ZIP 文件，不应仅根据 `Type` 假设下载文件后缀。

单次等待的最坏耗时为 `max_polls * HY3D_TIMEOUT_SECONDS + (max_polls - 1) * poll_interval_seconds`，默认不超过约 110 秒，加上少量通信开销。调大轮询次数时同步调大客户端工具超时；默认的 Codex 示例已配置 180 秒。

## 额度与错误处理

- 启动、工具发现、配置检查和全部自动化测试都不会调用真实生成接口。
- 提交不会自动重试，包括超时、网络错误、HTTP 错误或异常响应。提交结果不确定时先到腾讯控制台核实，避免重复计费。
- 查询遇到 API 错误会直接返回 MCP 工具错误，不无限轮询。业务失败 `FAIL` 则作为任务结果返回。
- 服务不记录请求体、认证头或图片内容。标准输出只用于 MCP 协议；错误日志走标准错误。
- API Key 缺失时仍可发现工具和检查配置；调用远程接口会明确报错。

可选的真实认证检查只查询不存在的 JobId `0`，不会创建生成任务，但仍会占用一次查询请求：

```bash
hunyuan3d-mcp --probe-auth
```

## 开发与验证

```bash
uv sync --project plugins/hunyuan3d --locked
uv run --project plugins/hunyuan3d --locked python -m pytest
uv run --project plugins/hunyuan3d --locked ruff check .
uv run --project plugins/hunyuan3d --locked ruff format --check .
```

测试覆盖请求地址和认证头、参数互斥和图片校验、返回结构、费用字段、API/HTTP/网络异常、提交不重试、轮询上限与取消，以及真实 STDIO 进程的初始化、工具发现和调用。测试使用虚拟 Key 与模拟响应，不依赖真实环境中的 Key 或网络。

目录：`plugins/hunyuan3d` 是可独立部署的插件和 Python 包，`.agents/plugins/marketplace.json` 是 marketplace 入口，`tests` 为离线测试，`examples` 为其他 MCP 客户端配置。构建 wheel、发布 Git marketplace 和更新插件的步骤参见[发布与部署说明](docs/distribution.md)。

## 文档依据

- [API Key 兼容接口与认证](https://cloud.tencent.com/document/product/1804/126189)
- [API Key 管理](https://cloud.tencent.com/document/product/1804/126325)
- [专业版提交参数](https://cloud.tencent.com/document/api/1804/123447)
- [专业版查询与结果](https://cloud.tencent.com/document/api/1804/123448)
- [腾讯官方 Python SDK 参数定义](https://github.com/TencentCloud/tencentcloud-sdk-python/blob/master/tencentcloud/ai3d/v20250513/models.py)
- [Codex MCP 注册文档](https://developers.openai.com/codex/mcp)
- [Codex 插件与 marketplace 打包文档](https://developers.openai.com/plugins/build/plugins)

接口信息核对日期：2026-09-08。兼容入口的模型限制和图片结构优先遵循该入口的专门文档。
