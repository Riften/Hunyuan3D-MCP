"""Smoke-test the distributable plugin in a new location without Tencent API calls."""

import argparse
import asyncio
import json
import os
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def check(source: Path, *, offline: bool = False) -> None:
    uv = shutil.which("uv")
    if uv is None:
        raise SystemExit("Install uv and make it available on PATH before running this check.")
    with TemporaryDirectory(prefix="hunyuan3d deployment ") as directory:
        workspace = Path(directory)
        plugin = workspace / "plugin with spaces"
        data = workspace / "plugin data"
        await asyncio.to_thread(
            shutil.copytree,
            source,
            plugin,
            ignore=shutil.ignore_patterns(".venv", "__pycache__", "dist", "build", ".git"),
        )
        config = json.loads((plugin / ".mcp.json").read_text())["mcpServers"]["hunyuan3d"]

        def expand(value: str) -> str:
            return value.replace("${PLUGIN_ROOT}", str(plugin)).replace("${PLUGIN_DATA}", str(data))

        env = {key: os.environ[key] for key in config["env_vars"] if key in os.environ}
        env.update({key: expand(value) for key, value in config["env"].items()})
        env["HY3D_API_KEY"] = ""
        if "UV_CACHE_DIR" in os.environ:
            env["UV_CACHE_DIR"] = os.environ["UV_CACHE_DIR"]
        if offline:
            env["UV_OFFLINE"] = "1"
        params = StdioServerParameters(
            command=uv,
            args=[expand(arg) for arg in config["args"]],
            env=env,
            cwd=str(workspace),
        )
        async with asyncio.timeout(config["startup_timeout_sec"] + 30):
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    initialized = await session.initialize()
                    assert initialized.serverInfo.name == "hunyuan3d"
                    tools = await session.list_tools()
                    assert len(tools.tools) == 4
                    result = await session.call_tool("hy3d_check_config", {})
                    assert not result.isError
                    assert result.structuredContent["api_key_configured"] is False
                    assert result.structuredContent["network_checked"] is False
                    missing_key = await session.call_tool("hy3d_query_job", {"job_id": "0"})
                    assert missing_key.isError
                    assert "HY3D_API_KEY" in missing_key.content[0].text
        assert (data / "venv" / "pyvenv.cfg").is_file()
        assert not (plugin / ".venv").exists()
    print("Plugin relocation, dependency environment, and MCP STDIO checks passed; API calls: 0.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--plugin-root",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "plugins" / "hunyuan3d",
    )
    parser.add_argument("--offline", action="store_true", help="Require pre-cached dependencies")
    args = parser.parse_args()
    asyncio.run(check(args.plugin_root.resolve(), offline=args.offline))


if __name__ == "__main__":
    main()
