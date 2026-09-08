# Hunyuan 3D MCP

通过 MCP 为 Codex、Claude Code、Cursor 提供腾讯混元生 3D Pro 服务。本项目是社区集成，使用你自己的 `HY3D_API_KEY`。

## 安装 Codex 插件

要求：Codex（支持 `codex plugin`）、Git、`uv`，以及 Python 3.11+。将密钥设置在启动 Codex 的环境中：

```bash
export HY3D_API_KEY='你的密钥'
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

把 `hunyuan3d-mcp` 配置为任意 STDIO MCP 客户端的 command，并转发 `HY3D_API_KEY`。服务支持文本或图片生成、任务查询和结果获取。

## MCP Inspector 调试

安装 [Node.js](https://nodejs.org/) 后，可以使用官方 MCP Inspector 调试独立运行的 STDIO 服务。先安装命令并设置 API 密钥：

```bash
uv tool install ./plugins/hunyuan3d
export HY3D_API_KEY='你的密钥'
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
