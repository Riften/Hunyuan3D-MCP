# Hunyuan 3D MCP

通过 MCP 为 Codex、Claude Code、Cursor 提供腾讯混元生 3D 的模型生成及后处理服务。本项目是社区集成，使用你自己的腾讯云凭据。

## 安装 Codex 插件

要求：Codex（支持 `codex plugin`）、Git、`uv`，以及 Python 3.11+。所有服务使用腾讯云 TC3，需要 SecretId/SecretKey。将凭据设置在启动 Codex 的环境中：

```bash
# 纹理、组件、极速版、UV、减面、绑骨、动作等服务需要：
export TENCENTCLOUD_SECRET_ID='你的 SecretId'
export TENCENTCLOUD_SECRET_KEY='你的 SecretKey'
codex plugin marketplace add <仓库地址>
codex plugin add hunyuan3d@hunyuan3d
```

本地开发版本：

```bash
codex plugin marketplace add .
codex plugin remove hunyuan3d@hunyuan3d
codex plugin add hunyuan3d@hunyuan3d
```

重启会话后调用 `hy3d_check_config` 检查配置。插件使用安装副本中的 `uv.lock` 和独立环境启动，与你启动 Codex 时激活的 Python 环境无关；首次启动会下载依赖。

## 独立 MCP

```bash
uv tool install ./plugins/hunyuan3d
hunyuan3d-mcp --check-config
```

把 `hunyuan3d-mcp` 配置为任意 STDIO MCP 客户端的 command，并转发腾讯云凭据环境变量。服务提供 14 个按用途划分的服务工具，另有能力发现、配置检查和任务查询工具。

## 服务工具与调用流程

Agent 可以直接通过 MCP 工具描述和参数 schema 选择服务，不需要猜测通用提交接口的参数。
`hy3d_list_capabilities` 会提供调用示例、凭据要求、动作预设和人物模板。

| 用途 | 工具 |
| --- | --- |
| 文本 / 图片 / 草图生成模型 | `hy3d_generate_model_from_text` / `hy3d_generate_model_from_image` / `hy3d_generate_model_from_sketch` |
| 低多边形 / 白模 / 极速版 | `hy3d_generate_low_poly_model` / `hy3d_generate_geometry` / `hy3d_generate_rapid_model` |
| 纹理生成 / 组件生成 | `hy3d_generate_texture` / `hy3d_generate_parts` |
| UV 展开 / 智能减面 | `hy3d_unwrap_uv` / `hy3d_reduce_faces` |
| 绑骨蒙皮 / 动作 / 头像人物 | `hy3d_rig_model` / `hy3d_generate_motion` / `hy3d_generate_profile_model` |
| 格式转换、预览视频 | `hy3d_convert_format` |

生成工具返回 `JobId`、`service`、`backend`，以及可直接复制给 `hy3d_query_job` 或
`hy3d_wait_job` 的参数。完成后可以把结果模型 URL 传给纹理、组件等后续工具。
格式转换直接返回 URL，不需要轮询。所有服务统一使用腾讯云 TC3。

**鉴权：**所有服务使用腾讯云 TC3，需要 `TENCENTCLOUD_SECRET_ID` 和 `TENCENTCLOUD_SECRET_KEY`；临时凭据还需 `TENCENTCLOUD_TOKEN`。
所有凭据仅从运行环境读取；`hy3d_check_config` 可检查哪些服务已具备凭据。

图片支持 URL、绝对路径或 Base64；已有模型需提供腾讯可访问的 URL。组件生成只接受 FBX，
可先调用格式转换工具。完整参数、限制和串联示例见 [插件使用说明](plugins/hunyuan3d/README.md)。

## MCP Inspector 调试

安装 [Node.js](https://nodejs.org/) 后，可以使用官方 MCP Inspector 调试独立运行的 STDIO 服务。先安装命令并设置腾讯云凭据：

```bash
uv tool install ./plugins/hunyuan3d
# 纹理、组件、极速版、UV、减面、绑骨、动作等服务需要：
export TENCENTCLOUD_SECRET_ID='你的 SecretId'
export TENCENTCLOUD_SECRET_KEY='你的 SecretKey'
```

从项目根目录启动 Inspector：

```bash
npx @modelcontextprotocol/inspector hunyuan3d-mcp
```

Inspector 会启动本地代理并打开 Web UI。在 UI 的 `Tools` 页面可以查看工具、填写参数并调用，也可以查看初始化、请求和响应日志。服务通过 STDIO 与 Inspector 通信，请勿向标准输出写入日志；结束调试时在终端按 `Ctrl-C`。如需只验证配置，可运行 `hunyuan3d-mcp --check-config`。

## 开发检查

```bash
uv run --project plugins/hunyuan3d --locked python -m pytest
uv run --project plugins/hunyuan3d --locked ruff check .
```

开发约定和发布流程见 [AGENTS.md](AGENTS.md)。
