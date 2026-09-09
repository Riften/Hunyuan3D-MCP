import json
import tomllib
from pathlib import Path

from hunyuan3d_mcp import __version__

ROOT = Path(__file__).resolve().parents[1]


def test_marketplace_points_to_self_contained_package():
    marketplace = json.loads((ROOT / ".agents/plugins/marketplace.json").read_text())
    (entry,) = marketplace["plugins"]
    plugin = ROOT / entry["source"]["path"]
    assert plugin.resolve().is_relative_to(ROOT)
    assert marketplace["name"] == "hunyuan3d"
    assert entry["name"] == plugin.name == "hunyuan3d"
    manifest = json.loads((plugin / ".codex-plugin/plugin.json").read_text())
    package = tomllib.loads((plugin / "pyproject.toml").read_text())
    assert manifest["version"].split("+", 1)[0] == package["project"]["version"] == __version__
    assert (plugin / package["project"]["readme"]).is_file()
    assert (plugin / "src/hunyuan3d_mcp/__main__.py").is_file()
    lock = tomllib.loads((plugin / "uv.lock").read_text())
    distribution = next(p for p in lock["package"] if p["name"] == "hunyuan3d-mcp")
    assert distribution["source"] == {"editable": "."}


def test_plugin_launch_uses_plugin_relative_cwd_and_forwards_key():
    plugin = ROOT / "plugins/hunyuan3d"
    manifest = json.loads((plugin / ".codex-plugin/plugin.json").read_text())
    config = json.loads((plugin / manifest["mcpServers"]).read_text())["mcpServers"]["hunyuan3d"]
    assert config["command"] == "uv"
    assert config["args"] == [
        "run",
        "--locked",
        "--no-dev",
        "--python",
        "3.11",
        "hunyuan3d-mcp",
    ]
    assert config["cwd"] == "."
    assert {
        "TENCENTCLOUD_SECRET_ID",
        "TENCENTCLOUD_SECRET_KEY",
        "TENCENTCLOUD_TOKEN",
    } <= set(config["env_vars"])
    assert "env" not in config
    assert "${PLUGIN_ROOT}" not in json.dumps(config)
    assert "${PLUGIN_DATA}" not in json.dumps(config)


def test_standalone_examples_use_installed_entry_point():
    codex = tomllib.loads((ROOT / "examples/codex.toml").read_text())["mcp_servers"]["hunyuan3d"]
    assert codex["command"] == "hunyuan3d-mcp"
    for name in ("claude-code", "cursor"):
        config = json.loads((ROOT / f"examples/{name}.json").read_text())
        assert config["mcpServers"]["hunyuan3d"]["command"] == "hunyuan3d-mcp"
