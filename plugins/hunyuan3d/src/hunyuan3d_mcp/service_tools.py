"""Task-oriented MCP tools with explicit typed inputs and a local capability guide."""

from typing import Annotated, Any

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from .client import HunyuanError, Settings
from .service_models import (
    MOTION_PRESETS,
    ConvertInput,
    GeometryInput,
    ImageTo3DInput,
    LowPolyInput,
    MotionInput,
    PartsInput,
    ProfileInput,
    RapidInput,
    ReduceFacesInput,
    RigInput,
    SketchTo3DInput,
    TextTo3DInput,
    TextureInput,
    UVInput,
)
from .services import Backend

WRITE = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=False,
    openWorldHint=True,
)
LOCAL = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)
BackendOption = Annotated[
    Backend,
    Field(
        description="All services use Tencent Cloud TC3. Returned backend "
        "must be reused when querying.",
    ),
]

TOOL_GUIDE = [
    {
        "tool": "hy3d_generate_model_from_text",
        "service": "pro",
        "description": "Generate a textured 3D model from a text description (文生3D). Pro "
        "3.0/3.1. Choose this for a new object described in words.",
        "example": {"request": {"prompt": "一把现代办公椅"}},
    },
    {
        "tool": "hy3d_generate_model_from_image",
        "service": "pro",
        "description": "Reconstruct a textured 3D model from an image (图生3D). Supply a "
        "main/front image, optionally additional views of the same object."
        " Additional views require backend=tc3; extra angles beyond "
        "left/right/back require model 3.1.",
        "example": {"request": {"image": {"url": "https://example.com/chair.png"}}},
    },
    {
        "tool": "hy3d_generate_model_from_sketch",
        "service": "pro",
        "description": "Generate a 3D model from a sketch or line drawing (草图生3D), "
        "optionally guided by text. Uses Pro 3.0 Sketch mode; both image "
        "and prompt are allowed here.",
        "example": {
            "request": {"image": {"path": "/absolute/path/sketch.png"}, "prompt": "木制椅子"}
        },
    },
    {
        "tool": "hy3d_generate_low_poly_model",
        "service": "pro",
        "description": "Generate a new model with low-polygon topology (低多边形生成) from text"
        " OR image using Pro 3.0. Quad mode mixes quads and triangles; "
        "face count cannot be set. To simplify an EXISTING model use "
        "hy3d_reduce_faces.",
        "example": {"request": {"prompt": "低多边形宝箱", "polygon_type": "triangle"}},
    },
    {
        "tool": "hy3d_generate_geometry",
        "service": "pro",
        "description": "Generate an untextured mesh/white model (白模生成) from text OR "
        "image. Pro Geometry mode; default output GLB. Use "
        "hy3d_generate_texture afterwards to add materials.",
        "example": {"request": {"prompt": "一只陶瓷花瓶"}},
    },
    {
        "tool": "hy3d_generate_rapid_model",
        "service": "rapid",
        "description": "Generate a 3D model using the Rapid edition (极速版). Text OR image "
        "input; text at most 200 characters. Default output OBJ, or GLB "
        "for geometry-only mode. Requires Tencent Cloud credentials.",
        "example": {"request": {"prompt": "一把椅子", "result_format": "GLB"}},
    },
    {
        "tool": "hy3d_generate_texture",
        "service": "texture",
        "description": "Generate or replace textures on an EXISTING OBJ/GLB mesh "
        "(纹理生成/重绘). Supply the model URL plus an appearance prompt OR "
        "reference image. Supports PBR, keeping UVs, texture resolution "
        "and model 3.1 multi-view texturing. Requires Tencent Cloud "
        "credentials.",
        "example": {
            "request": {
                "file": {"url": "https://example.com/model.glb", "type": "GLB"},
                "prompt": "磨损的棕色皮革",
                "enable_pbr": True,
            }
        },
    },
    {
        "tool": "hy3d_generate_parts",
        "service": "parts",
        "description": "Decompose an EXISTING FBX mesh into semantic 3D components "
        "(组件生成/拆分). Convert OBJ/GLB to FBX with hy3d_convert_format first."
        " staged=true returns editable segmentation: download "
        "PartSegmentationInfoUrl, edit it, then submit the returned model "
        "plus segmentation_info. postprocess adds 20 credits. Requires "
        "Tencent Cloud credentials.",
        "example": {"request": {"file": {"url": "https://example.com/model.fbx"}}},
    },
    {
        "tool": "hy3d_unwrap_uv",
        "service": "uv",
        "description": "Unwrap UVs for an EXISTING FBX/OBJ/GLB mesh (UV展开). Query the "
        "returned task, then pass its output URL to hy3d_generate_texture "
        "with keep_uv=true if desired. Requires Tencent Cloud credentials.",
        "example": {"request": {"file": {"url": "https://example.com/model.glb", "type": "GLB"}}},
    },
    {
        "tool": "hy3d_reduce_faces",
        "service": "reduce_faces",
        "description": "Simplify an EXISTING OBJ/GLB mesh (智能减面/拓扑). Select "
        "high/medium/low face tier and triangle/quadrilateral topology. "
        "This API has no exact target face count. Requires Tencent Cloud "
        "credentials.",
        "example": {
            "request": {
                "file": {"url": "https://example.com/model.glb", "type": "GLB"},
                "face_level": "low",
            }
        },
    },
    {
        "tool": "hy3d_rig_model",
        "service": "rig",
        "description": "Auto-rig and skin an EXISTING character (自动绑骨/蒙皮), optionally "
        "adding a humanoid motion preset. FBX/GLB ≤60 MB. Humanoids need "
        "A/T pose without weapons/mounts/wings; animals need a simple pose"
        " and no motion preset. Preset map: hy3d_list_capabilities. "
        "Requires Tencent Cloud credentials.",
        "example": {
            "request": {"file": {"url": "https://example.com/character.glb", "type": "GLB"}}
        },
    },
    {
        "tool": "hy3d_generate_motion",
        "service": "motion",
        "description": "Generate character animation from text (动作生成) with HY-Motion-1.0,"
        " 1–12 seconds. Optionally retarget onto a model from Hunyuan "
        "rigging/animation templates; arbitrary character rigs are "
        "unsupported. Requires Tencent Cloud credentials.",
        "example": {"request": {"prompt": "人物向前走几步然后挥手", "duration": 5}},
    },
    {
        "tool": "hy3d_generate_profile_model",
        "service": "profile",
        "description": "Generate a stylized 3D person from a portrait and a character "
        "template (头像生3D). JPEG/PNG, each dimension 501–4095 px, encoded "
        "<10 MiB. Template enum is in the schema; labels are in "
        "hy3d_list_capabilities. Requires Tencent Cloud credentials.",
        "example": {
            "request": {
                "image": {"url": "https://example.com/portrait.jpg"},
                "template": "basketball",
            }
        },
    },
    {
        "tool": "hy3d_convert_format",
        "service": "convert",
        "description": "Convert an EXISTING FBX/OBJ/GLB model ≤60 MB to STL/USDZ/FBX, or "
        "render MP4/GIF previews (格式转换). Returns ResultFile3D URL "
        "directly, without JobId or polling. Use FBX output before "
        "component generation. Requires Tencent Cloud credentials.",
        "example": {
            "request": {
                "file": {"url": "https://example.com/model.glb", "type": "GLB"},
                "format": "FBX",
            }
        },
    },
]

PROFILE_TEMPLATES = dict(
    zip(
        [
            "basketball",
            "badminton",
            "pingpong",
            "gymnastics",
            "pilidance",
            "tennis",
            "athletics",
            "footballboykicking1",
            "footballboykicking2",
            "guitar",
            "footballboy",
            "skateboard",
            "futuresoilder",
            "explorer",
            "beardollgirl",
            "bibpantsboy",
            "womansitpose",
            "womanstandpose2",
            "mysteriousprincess",
            "manstandpose2",
        ],
        [
            "动感球手",
            "羽扬中华",
            "国球荣耀",
            "勇攀巅峰",
            "舞动青春",
            "网球甜心",
            "东方疾风",
            "激情逐风",
            "绿茵之星",
            "甜酷弦音",
            "足球小将",
            "滑跃青春",
            "未来战士",
            "逐梦旷野",
            "可爱女孩",
            "都市白领",
            "职业丽影",
            "悠闲时光",
            "海洋公主",
            "演讲之星",
        ],
        strict=True,
    )
)


async def _submit(ctx: Context, service: str, request, backend: Backend = "tc3") -> dict:
    try:
        return await ctx.request_context.lifespan_context.submit_service(
            service,
            request,
            backend=backend,
        )
    except (HunyuanError, ValueError, OSError) as exc:
        raise ToolError(str(exc)) from None


def register_service_tools(server: FastMCP, config: Settings) -> None:
    @server.tool(name="hy3d_list_capabilities", annotations=LOCAL)
    def list_capabilities() -> dict[str, Any]:
        """Discover services, tool examples, required credentials, motion presets and portrait
        templates.

        Local and free; use when choosing a workflow. Each listed tool has a typed input
        schema.
        Credential availability does not verify account permissions, service entitlement
        or quota.
        """
        available = config.public_info()["available_services"]
        return {
            "services": [
                {
                    **entry,
                    "credentials_configured": entry["service"] in available,
                    "credentials": (
                        "TENCENTCLOUD_SECRET_ID + TENCENTCLOUD_SECRET_KEY"
                    )
                    if entry["service"] == "pro"
                    else "TENCENTCLOUD_SECRET_ID + TENCENTCLOUD_SECRET_KEY",
                }
                for entry in TOOL_GUIDE
            ],
            "motion_presets": MOTION_PRESETS,
            "profile_templates": PROFILE_TEMPLATES,
            "workflow": [
                "Call the service tool; save JobId, service and backend.",
                "Copy returned query.arguments or wait.arguments into "
                "hy3d_query_job/hy3d_wait_job.",
                "WAIT/RUN are pending; DONE/FAIL are terminal. polling_exhausted "
                "is not cancellation.",
                "After DONE, select ResultFile3Ds by Type and pass Url to the next"
                " tool's file.url.",
                "Conversion returns ResultFile3D directly. Download result URLs within 24 hours.",
                "Submission can be billable. Never automatically resubmit after an"
                " ambiguous error.",
            ],
            "model_file_inputs": "Public HTTP(S) URLs only; upload local meshes to accessible "
            "storage first. This server does not upload mesh files.",
            "image_inputs": "Exactly one url/path/base64. Local images are uploaded to "
            "Tencent; URL image limits must be checked by the caller/provider.",
            "documentation": [
                "https://cloud.tencent.com/document/product/1804/126189",
                "https://cloud.tencent.com/document/api/1804/123447",
                "https://github.com/TencentCloud/tencentcloud-sdk-python/tree/master/tencentcloud/ai3d/v20250513",
            ],
        }

    @server.tool(name="hy3d_generate_model_from_text", annotations=WRITE)
    async def generate_model_from_text(
        request: TextTo3DInput,
        ctx: Context,
        backend: BackendOption = "tc3",
    ) -> dict[str, Any]:
        """Generate a textured 3D model from a text description (文生3D). Pro 3.0/3.1. Choose this
        for a new object described in words.

        Submits one potentially billable job; never retries. Returns JobId, service and backend.
        Copy returned query.arguments or wait.arguments to query/wait until DONE/FAIL.
        Download result URLs promptly.
        Example arguments: {"request": {"prompt": "一把现代办公椅"}}
        """
        return await _submit(ctx, "pro", request, backend)

    @server.tool(name="hy3d_generate_model_from_image", annotations=WRITE)
    async def generate_model_from_image(
        request: ImageTo3DInput,
        ctx: Context,
        backend: BackendOption = "tc3",
    ) -> dict[str, Any]:
        """Reconstruct a textured 3D model from an image (图生3D). Supply a main/front image,
        optionally additional views of the same object. Additional views require
        backend=tc3; extra angles beyond left/right/back require model 3.1.

        Submits one potentially billable job; never retries. Returns JobId, service and backend.
        Copy returned query.arguments or wait.arguments to query/wait until DONE/FAIL.
        Download result URLs promptly.
        Example arguments: {"request": {"image": {"url":
        "https://example.com/chair.png"}}}
        """
        return await _submit(ctx, "pro", request, backend)

    @server.tool(name="hy3d_generate_model_from_sketch", annotations=WRITE)
    async def generate_model_from_sketch(
        request: SketchTo3DInput,
        ctx: Context,
        backend: BackendOption = "tc3",
    ) -> dict[str, Any]:
        """Generate a 3D model from a sketch or line drawing (草图生3D), optionally guided by text.
        Uses Pro 3.0 Sketch mode; both image and prompt are allowed here.

        Submits one potentially billable job; never retries. Returns JobId, service and backend.
        Copy returned query.arguments or wait.arguments to query/wait until DONE/FAIL.
        Download result URLs promptly.
        Example arguments: {"request": {"image": {"path": "/absolute/path/sketch.png"},
        "prompt": "木制椅子"}}
        """
        return await _submit(ctx, "pro", request, backend)

    @server.tool(name="hy3d_generate_low_poly_model", annotations=WRITE)
    async def generate_low_poly_model(
        request: LowPolyInput,
        ctx: Context,
        backend: BackendOption = "tc3",
    ) -> dict[str, Any]:
        """Generate a new model with low-polygon topology (低多边形生成)
        from text OR image using Pro
        3.0. Quad mode mixes quads and triangles; face count cannot be set. To simplify
        an EXISTING model use hy3d_reduce_faces.

        Submits one potentially billable job; never retries. Returns JobId, service and backend.
        Copy returned query.arguments or wait.arguments to query/wait until DONE/FAIL.
        Download result URLs promptly.
        Example arguments: {"request": {"prompt": "低多边形宝箱", "polygon_type": "triangle"}}
        """
        return await _submit(ctx, "pro", request, backend)

    @server.tool(name="hy3d_generate_geometry", annotations=WRITE)
    async def generate_geometry(
        request: GeometryInput,
        ctx: Context,
        backend: BackendOption = "tc3",
    ) -> dict[str, Any]:
        """Generate an untextured mesh/white model (白模生成) from text OR image. Pro Geometry mode;
        default output GLB. Use hy3d_generate_texture afterwards to add materials.

        Submits one potentially billable job; never retries. Returns JobId, service and backend.
        Copy returned query.arguments or wait.arguments to query/wait until DONE/FAIL.
        Download result URLs promptly.
        Example arguments: {"request": {"prompt": "一只陶瓷花瓶"}}
        """
        return await _submit(ctx, "pro", request, backend)

    @server.tool(name="hy3d_generate_rapid_model", annotations=WRITE)
    async def generate_rapid_model(
        request: RapidInput,
        ctx: Context,
    ) -> dict[str, Any]:
        """Generate a 3D model using the Rapid edition (极速版). Text OR image input; text at most
        200 characters. Default output OBJ, or GLB for geometry-only mode. Requires
        Tencent Cloud credentials.

        Submits one potentially billable job; never retries. Returns JobId, service and backend.
        Copy returned query.arguments or wait.arguments to query/wait until DONE/FAIL.
        Download result URLs promptly.
        Example arguments: {"request": {"prompt": "一把椅子", "result_format": "GLB"}}
        """
        return await _submit(ctx, "rapid", request, "tc3")

    @server.tool(name="hy3d_generate_texture", annotations=WRITE)
    async def generate_texture(
        request: TextureInput,
        ctx: Context,
    ) -> dict[str, Any]:
        """Generate or replace textures on an EXISTING OBJ/GLB mesh (纹理生成/重绘).
        Supply the model
        URL plus an appearance prompt OR reference image. Supports PBR, keeping UVs,
        texture resolution and model 3.1 multi-view texturing. Requires Tencent Cloud
        credentials.

        Submits one potentially billable job; never retries. Returns JobId, service and backend.
        Copy returned query.arguments or wait.arguments to query/wait until DONE/FAIL.
        Download result URLs promptly.
        Example arguments: {"request": {"file": {"url": "https://example.com/model.glb",
        "type": "GLB"}, "prompt": "磨损的棕色皮革", "enable_pbr": true}}
        """
        return await _submit(ctx, "texture", request, "tc3")

    @server.tool(name="hy3d_generate_parts", annotations=WRITE)
    async def generate_parts(
        request: PartsInput,
        ctx: Context,
    ) -> dict[str, Any]:
        """Decompose an EXISTING FBX mesh into semantic 3D components (组件生成/拆分).
        Convert OBJ/GLB
        to FBX with hy3d_convert_format first. staged=true returns editable
        segmentation: download PartSegmentationInfoUrl, edit it, then submit the
        returned model plus segmentation_info. postprocess adds 20 credits. Requires
        Tencent Cloud credentials.

        Submits one potentially billable job; never retries. Returns JobId, service and backend.
        Copy returned query.arguments or wait.arguments to query/wait until DONE/FAIL.
        Download result URLs promptly.
        Example arguments: {"request": {"file": {"url":
        "https://example.com/model.fbx"}}}
        """
        return await _submit(ctx, "parts", request, "tc3")

    @server.tool(name="hy3d_unwrap_uv", annotations=WRITE)
    async def unwrap_uv(
        request: UVInput,
        ctx: Context,
    ) -> dict[str, Any]:
        """Unwrap UVs for an EXISTING FBX/OBJ/GLB mesh (UV展开). Query the returned task, then
        pass its output URL to hy3d_generate_texture with keep_uv=true if desired.
        Requires Tencent Cloud credentials.

        Submits one potentially billable job; never retries. Returns JobId, service and backend.
        Copy returned query.arguments or wait.arguments to query/wait until DONE/FAIL.
        Download result URLs promptly.
        Example arguments: {"request": {"file": {"url": "https://example.com/model.glb",
        "type": "GLB"}}}
        """
        return await _submit(ctx, "uv", request, "tc3")

    @server.tool(name="hy3d_reduce_faces", annotations=WRITE)
    async def reduce_faces(
        request: ReduceFacesInput,
        ctx: Context,
    ) -> dict[str, Any]:
        """Simplify an EXISTING OBJ/GLB mesh (智能减面/拓扑). Select high/medium/low face tier and
        triangle/quadrilateral topology. This API has no exact target face count.
        Requires Tencent Cloud credentials.

        Submits one potentially billable job; never retries. Returns JobId, service and backend.
        Copy returned query.arguments or wait.arguments to query/wait until DONE/FAIL.
        Download result URLs promptly.
        Example arguments: {"request": {"file": {"url": "https://example.com/model.glb",
        "type": "GLB"}, "face_level": "low"}}
        """
        return await _submit(ctx, "reduce_faces", request, "tc3")

    @server.tool(name="hy3d_rig_model", annotations=WRITE)
    async def rig_model(
        request: RigInput,
        ctx: Context,
    ) -> dict[str, Any]:
        """Auto-rig and skin an EXISTING character (自动绑骨/蒙皮), optionally adding a humanoid
        motion preset. FBX/GLB ≤60 MB. Humanoids need A/T pose without
        weapons/mounts/wings; animals need a simple pose and no motion preset. Preset
        map: hy3d_list_capabilities. Requires Tencent Cloud credentials.

        Submits one potentially billable job; never retries. Returns JobId, service and backend.
        Copy returned query.arguments or wait.arguments to query/wait until DONE/FAIL.
        Download result URLs promptly.
        Example arguments: {"request": {"file": {"url":
        "https://example.com/character.glb", "type": "GLB"}}}
        """
        return await _submit(ctx, "rig", request, "tc3")

    @server.tool(name="hy3d_generate_motion", annotations=WRITE)
    async def generate_motion(
        request: MotionInput,
        ctx: Context,
    ) -> dict[str, Any]:
        """Generate character animation from text (动作生成) with HY-Motion-1.0, 1–12 seconds.
        Optionally retarget onto a model from Hunyuan rigging/animation templates;
        arbitrary character rigs are unsupported. Requires Tencent Cloud credentials.

        Submits one potentially billable job; never retries. Returns JobId, service and backend.
        Copy returned query.arguments or wait.arguments to query/wait until DONE/FAIL.
        Download result URLs promptly.
        Example arguments: {"request": {"prompt": "人物向前走几步然后挥手", "duration": 5}}
        """
        return await _submit(ctx, "motion", request, "tc3")

    @server.tool(name="hy3d_generate_profile_model", annotations=WRITE)
    async def generate_profile_model(
        request: ProfileInput,
        ctx: Context,
    ) -> dict[str, Any]:
        """Generate a stylized 3D person from a portrait and a character template (头像生3D).
        JPEG/PNG, each dimension 501–4095 px, encoded <10 MiB. Template enum is in the
        schema; labels are in hy3d_list_capabilities. Requires Tencent Cloud
        credentials.

        Submits one potentially billable job; never retries. Returns JobId, service and backend.
        Copy returned query.arguments or wait.arguments to query/wait until DONE/FAIL.
        Download result URLs promptly.
        Example arguments: {"request": {"image": {"url":
        "https://example.com/portrait.jpg"}, "template": "basketball"}}
        """
        return await _submit(ctx, "profile", request, "tc3")

    @server.tool(name="hy3d_convert_format", annotations=WRITE)
    async def convert_format(
        request: ConvertInput,
        ctx: Context,
    ) -> dict[str, Any]:
        """Convert an EXISTING FBX/OBJ/GLB model ≤60 MB to STL/USDZ/FBX, or render MP4/GIF
        previews (格式转换). Returns ResultFile3D URL directly, without JobId or polling.
        Use FBX output before component generation. Requires Tencent Cloud credentials.

        Example arguments: {"request": {"file": {"url": "https://example.com/model.glb",
        "type": "GLB"}, "format": "FBX"}}
        """
        try:
            return await ctx.request_context.lifespan_context.convert(request)
        except (HunyuanError, ValueError, OSError) as exc:
            raise ToolError(str(exc)) from None
