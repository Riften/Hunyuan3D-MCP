# 发布与部署

## 仓库布局

```text
.agents/plugins/marketplace.json
plugins/hunyuan3d/
  .codex-plugin/plugin.json
  .mcp.json
  pyproject.toml
  uv.lock
  README.md
  src/hunyuan3d_mcp/
examples/
tests/
```

marketplace 的 `source.path` 相对仓库根目录解析。Codex 将 `plugins/hunyuan3d` 复制到插件缓存，因此运行所需的源码、包元数据、README 和锁文件都放在该目录内。根目录 `pyproject.toml` 只管理测试和代码风格，Python 包的元数据位于插件目录。

MCP 配置使用 `cwd: "."`，由 Codex 将相对工作目录解析到安装后的插件根目录。`uv` 在该安装副本中创建 `.venv` 并按 `uv.lock` 启动服务。配置不依赖仅对插件 hooks 明确定义的 `${PLUGIN_ROOT}`、`${PLUGIN_DATA}` 变量，也不经过 shell 拼接或包含预设用户目录。

## 发布 Git Marketplace

1. 将本仓库发布到可访问的 Git 地址。当前清单通过相对目录定位插件，发布时不必修改它。
2. 给使用者提供仓库 URL，并要求安装 Git、uv 和支持插件的 Codex 版本，配置自己的 `TENCENTCLOUD_SECRET_ID`（Pro），以及 `TENCENTCLOUD_SECRET_ID` / `TENCENTCLOUD_SECRET_KEY`（其他服务）。
3. 使用者运行以下命令，将 `<repository-url>` 替换为实际地址：

```bash
codex plugin marketplace add <repository-url>
codex plugin add hunyuan3d@hunyuan3d
```

可以用 `--ref <tag-or-commit>` 固定发布版本，例如 `codex plugin marketplace add <repository-url> --ref v0.1.0`。仅在仓库确实有对应标签后使用该标签。

仓库分发不需要预先上传 Python 包到 PyPI。本项目也没有配置虚构的发布账号或包仓库地址。marketplace 分发与 OpenAI 官方公共目录上架是不同流程；公共目录发布需要另行提交审核，参见[官方发布说明](https://developers.openai.com/plugins/deploy/submission)。

## 安装验证

在克隆后的仓库根目录验证 marketplace：

```bash
codex plugin marketplace add .
codex plugin add hunyuan3d@hunyuan3d
codex plugin list
```

新建会话后调用 `hy3d_check_config`，应能列出 19 个工具并检查环境；`hy3d_list_capabilities` 提供服务说明和示例。安装和该检查不调用腾讯 API。`ON_INSTALL` 为 marketplace 策略，不会自动生成腾讯 Key，也不会弹出本项目实现的登录界面；Key 始终由部署环境提供。

首次启动由 `uv` 按锁文件下载依赖，并在 Codex 的安装缓存副本中创建自己的 `.venv`；启动超时配置为 180 秒。执行本地 marketplace 安装前，插件源码目录不应包含开发用 `.venv`，因为本地安装会复制源码目录中的未跟踪文件。离线部署需要通过独立构建流程事先准备对应操作系统和 Python 版本的 uv 缓存；仅复制锁文件并不能离线安装依赖。腾讯 API 调用始终需要网络。

## 更新版本

发布正式新版时，移除 `.codex-plugin/plugin.json` 中仅供本地迭代使用的 `+codex.*` cachebuster，并同步更新 `plugins/hunyuan3d/pyproject.toml`、插件 manifest 和 `src/hunyuan3d_mcp/__init__.py` 的基础版本。随后重新生成锁文件并执行检查：

```bash
uv lock --project plugins/hunyuan3d
uv run --project plugins/hunyuan3d --locked python -m pytest
uv run --project plugins/hunyuan3d --locked ruff check .
```

发布新的 Git 提交或标签后，使用者更新 marketplace 并重新安装插件：

```bash
codex plugin marketplace upgrade hunyuan3d
codex plugin remove hunyuan3d@hunyuan3d
codex plugin add hunyuan3d@hunyuan3d
```

随后新建会话。固定到标签或提交的 marketplace 不会自动跟随主分支；需要通过 `marketplace add` 选择新的 `--ref`。安装成功后，直接修改源仓库中的文件不会自动更新已缓存的插件。

## Python 包分发

从仓库根目录构建 wheel 和源码包：

```bash
uv build ./plugins/hunyuan3d --out-dir dist
```

构建产物可交由自己的 Python 包索引或发布流程分发。安装 wheel 后，所有 STDIO MCP 客户端均可使用 `hunyuan3d-mcp` 命令；程序也支持 `python -m hunyuan3d_mcp`。首次发布前应确定项目的开源许可和实际发布者信息，本项目未替维护者选择授权许可。

## 验证范围

自动化测试使用模拟 HTTP 和虚拟 Key，覆盖 MCP 协议、计费相关重试约束，以及独立插件目录的配置和打包边界。发布前可以运行可选部署检查，将插件复制到新的目录，再按真实 `.mcp.json` 启动：

```bash
uv run --project plugins/hunyuan3d --locked python scripts/check_plugin.py
```

该检查使用临时目录和空 Key，只执行 MCP 初始化、工具发现及配置检查，不提交生成任务。它会安装插件依赖，因此首次运行需要访问 Python 包源。

参考：[官方插件打包文档](https://developers.openai.com/plugins/build/plugins)、[Codex MCP 配置](https://developers.openai.com/codex/mcp)。
