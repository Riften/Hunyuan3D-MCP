import asyncio
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def test_real_stdio_lifecycle_without_credentials():
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "hunyuan3d_mcp"],
        env={"HY3D_API_KEY": "", "HY3D_TIMEOUT_SECONDS": "1"},
    )
    async with asyncio.timeout(20):
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                initialized = await session.initialize()
                assert initialized.serverInfo.name == "hunyuan3d"
                tools = {tool.name: tool for tool in (await session.list_tools()).tools}
                assert set(tools) == {
                    "hy3d_check_config",
                    "hy3d_submit_job",
                    "hy3d_query_job",
                    "hy3d_wait_job",
                }
                assert tools["hy3d_submit_job"].annotations.idempotentHint is False
                assert tools["hy3d_query_job"].annotations.readOnlyHint is True
                assert "ctx" not in tools["hy3d_query_job"].inputSchema["properties"]
                config = await session.call_tool("hy3d_check_config", {})
                assert not config.isError
                assert config.structuredContent["api_key_configured"] is False
                missing_key = await session.call_tool("hy3d_query_job", {"job_id": "0"})
                assert missing_key.isError
                assert "HY3D_API_KEY" in missing_key.content[0].text
                invalid = await session.call_tool("hy3d_submit_job", {"request": {}})
                assert invalid.isError
                invalid_job = await session.call_tool("hy3d_query_job", {"job_id": "bad"})
                assert invalid_job.isError
