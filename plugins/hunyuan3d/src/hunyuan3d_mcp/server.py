"""STDIO tools shared by standalone MCP clients and the Codex plugin."""

from contextlib import asynccontextmanager
from typing import Annotated, Any

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from .client import HunyuanClient, HunyuanError, Settings
from .service_tools import register_service_tools
from .services import Backend, Service


def create_server(settings: Settings | None = None) -> FastMCP:
    config = settings if settings is not None else Settings.from_env()

    @asynccontextmanager
    async def lifespan(server: FastMCP):
        async with HunyuanClient(config) as client:
            yield client

    server = FastMCP(
        "hunyuan3d",
        instructions=(
            "Use service-specific tools to generate models from text/images/sketches, low-poly "
            "or untextured geometry, rapid models, textures, components, UVs, simplified meshes, "
            "rigs, motion, portrait characters, and format conversion. hy3d_list_capabilities "
            "provides examples and workflow guidance; hy3d_check_config is local and free. "
            "All services require TENCENTCLOUD_SECRET_ID + TENCENTCLOUD_SECRET_KEY "
            "(optional TENCENTCLOUD_TOKEN). "
            "Submission tools create potentially billable jobs: save JobId/service/backend "
            "and copy returned query.arguments or wait.arguments to query/wait. Never "
            "automatically resubmit after an uncertain error. WAIT/RUN are pending, DONE/FAIL "
            "terminal. Polling exhaustion does not cancel a job. Return files and any credit "
            "usage. Download results within 24 hours. Conversion returns a URL directly. "
            "Use absolute local image paths; existing model inputs require public HTTP(S) URLs. "
            "Chain ResultFile3Ds[].Url and Type into the next tool's file.url/type after DONE. "
            "All service tools use Tencent Cloud TC3 credentials."
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
        """Inspect credentials and service availability locally, without exposing secrets."""
        return config.public_info()

    @server.tool(name="hy3d_query_job", annotations=read)
    async def query_job(
        job_id: Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[0-9]+$")],
        ctx: Context,
        service: Annotated[
            Service,
            Field(description="Service returned by submission; defaults to pro."),
        ] = "pro",
        backend: Annotated[
            Backend,
            Field(description="Reuse submission backend: tc3; auto is accepted for compatibility."),
        ] = "auto",
    ) -> dict[str, Any]:
        """Query an existing JobId ONCE. Return WAIT/RUN/DONE/FAIL, files and credit usage.

        Copy query.arguments from submission: job_id, service and backend.
        Reuse the submitted JobId (valid for 24 hours). DONE/FAIL are terminal.
        ResultFile3Ds includes Type, Url and PreviewImageUrl. Download results promptly.
        """
        try:
            return await ctx.request_context.lifespan_context.query(
                job_id, service=service, backend=backend
            )
        except (HunyuanError, ValueError) as exc:
            raise ToolError(str(exc)) from None

    @server.tool(name="hy3d_wait_job", annotations=read)
    async def wait_job(
        job_id: Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[0-9]+$")],
        ctx: Context,
        max_polls: Annotated[int, Field(ge=1, le=10)] = 3,
        poll_interval_seconds: Annotated[float, Field(ge=5, le=60)] = 10,
        service: Annotated[
            Service,
            Field(description="Service returned by submission; defaults to pro."),
        ] = "pro",
        backend: Annotated[
            Backend,
            Field(description="Reuse submission backend: tc3; auto is accepted for compatibility."),
        ] = "auto",
    ) -> dict[str, Any]:
        """Poll an EXISTING job, default at most 3 queries spaced 10 seconds apart.

        Copy wait.arguments from submission, including service and backend.
        Stop on DONE or FAIL, propagate API errors without retries. If polling_exhausted
        is true the job is still pending, NOT cancelled. Query the same JobId later.
        For worst-case duration allow max_polls * request timeout + (max_polls - 1) *
        poll interval in the agent's tool timeout; defaults require up to 110 seconds.
        """
        try:
            return await ctx.request_context.lifespan_context.wait(
                job_id,
                max_polls=max_polls,
                poll_interval_seconds=poll_interval_seconds,
                service=service,
                backend=backend,
            )
        except (HunyuanError, ValueError) as exc:
            raise ToolError(str(exc)) from None

    register_service_tools(server, config)
    return server
