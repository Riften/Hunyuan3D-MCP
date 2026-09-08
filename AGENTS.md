# Hunyuan3D MCP 开发说明

插件位于 `plugins/hunyuan3d`，Python 包源码在 `src/hunyuan3d_mcp`，Codex 清单在 `.codex-plugin/plugin.json`，MCP 配置在 `.mcp.json`。根目录测试覆盖协议、客户端和分发边界。

使用 `uv` 管理插件依赖，锁文件为 `plugins/hunyuan3d/uv.lock`。不要提交或依赖任何 `.venv`；插件启动通过 `uv run --locked --no-dev --python 3.11`，应隔离于 Codex 启动时的 Python 环境。

常用检查：

```bash
uv run --project plugins/hunyuan3d --locked python -m pytest
uv run --project plugins/hunyuan3d --locked ruff check .
python scripts/check_plugin.py --offline
```

修改依赖后运行 `uv lock --project plugins/hunyuan3d`。发布时同步插件 manifest、包版本和 `src/hunyuan3d_mcp/__init__.py`，并更新 marketplace 条目。`HY3D_API_KEY` 只从运行环境读取，不写入配置。
