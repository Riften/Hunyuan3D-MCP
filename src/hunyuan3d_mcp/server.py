"""STDIO tools for code agents."""

from contextlib import asynccontextmanager
from typing import Annotated, Any

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from .client import HunyuanClient, HunyuanError, Settings
from .models import GenerationInput


def create_server(settings: Settings | None = None) -> FastMCP:
    config = settings if settings is not None else Settings.from_env()

    @asynccontextmanager
    async def lifespan(server: FastMCP):
        async with HunyuanClient(config) as client:
            yield client

    server = FastMCP(
        "hunyuan3d",
        instructions=(
            "Generate 3D assets with Tencent Hunyuan Pro. submit creates a potentially billable "
            "job: call only when generation is requested, save JobId, and never automatically "
            "resubmit after a timeout. Query that same JobId or wait with bounded polling. "
            "WAIT/RUN are pending, DONE succeeds, FAIL is terminal. Return result URLs and "
            "credit usage. Job IDs are valid for 24 hours. check_config is local and free. "
            "Use absolute local image paths; credentials come only from HY3D_API_KEY."
        ),
        lifespan=lifespan,
        log_level="WARNING",
    )
    read = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True)

    @server.tool(
        name="hy3d_check_config",
        annotations=ToolAnnotations(
            readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
        ),
    )
    def check_config() -> dict[str, Any]:
        """Inspect local configuration without network requests or exposing the API Key."""
        return config.public_info()

    @server.tool(
        name="hy3d_submit_job",
        annotations=ToolAnnotations(
            readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True
        ),
    )
    async def submit_job(request: GenerationInput, ctx: Context) -> dict[str, Any]:
        """Submit ONE potentially billable Pro 3D generation job; returns JobId immediately.

        Use prompt OR image_url/image_path/image_base64 (Sketch permits prompt plus image).
        image_path must be absolute. Inputs are uploaded to Tencent. Models: 3.0 or 3.1;
        LowPoly and Sketch require 3.0. Omit result_format for default OBJ/GLB outputs;
        explicit formats: STL, USDZ, FBX. Never retry automatically if submission fails.
        """
        try:
            return await ctx.request_context.lifespan_context.submit(request)
        except (HunyuanError, ValueError, OSError) as exc:
            raise ToolError(str(exc)) from None

    @server.tool(name="hy3d_query_job", annotations=read)
    async def query_job(
        job_id: Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[0-9]+$")],
        ctx: Context,
    ) -> dict[str, Any]:
        """Query an existing JobId ONCE. Return WAIT/RUN/DONE/FAIL, files and credit usage.

        Reuse the submitted JobId (valid for 24 hours). DONE/FAIL are terminal.
        ResultFile3Ds includes Type, Url and PreviewImageUrl. Download results promptly.
        """
        try:
            return await ctx.request_context.lifespan_context.query(job_id)
        except HunyuanError as exc:
            raise ToolError(str(exc)) from None

    @server.tool(name="hy3d_wait_job", annotations=read)
    async def wait_job(
        job_id: Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[0-9]+$")],
        ctx: Context,
        max_polls: Annotated[int, Field(ge=1, le=10)] = 3,
        poll_interval_seconds: Annotated[float, Field(ge=5, le=60)] = 10,
    ) -> dict[str, Any]:
        """Poll an EXISTING job, default at most 3 queries spaced 10 seconds apart.

        Stop on DONE or FAIL, propagate API errors without retries. If polling_exhausted
        is true the job is still pending, NOT cancelled. Query the same JobId later.
        For worst-case duration allow max_polls * request timeout + (max_polls - 1) *
        poll interval in the agent's tool timeout; defaults require up to 110 seconds.
        """
        try:
            return await ctx.request_context.lifespan_context.wait(
                job_id, max_polls=max_polls, poll_interval_seconds=poll_interval_seconds
            )
        except (HunyuanError, ValueError) as exc:
            raise ToolError(str(exc)) from None

    return server
