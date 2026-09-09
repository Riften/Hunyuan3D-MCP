"""Task-oriented MCP tools with explicit typed inputs and a local capability guide."""

import json
from typing import Any, get_args

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.fastmcp.tools import Tool
from mcp.server.fastmcp.utilities.func_metadata import ArgModelBase, FuncMetadata
from mcp.types import ToolAnnotations
from pydantic import BaseModel, create_model

from .client import HunyuanError, Settings
from .service_models import (
    MOTION_PRESETS,
    ConvertInput,
    GeometryInput,
    ImageTo3DInput,
    LowPolyInput,
    MotionInput,
    MultiViewTo3DInput,
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

TOOL_GUIDE = [
    {
        "tool": "hy3d_generate_model_from_text",
        "service": "pro",
        "description": (
            "Generate a textured 3D model from a text description (文生3D). Pro 3.0/3.1. Choose "
            "this for a new object described in words."
        ),
        "example": {"prompt": "一把现代办公椅"},
    },
    {
        "tool": "hy3d_generate_model_from_image",
        "service": "pro",
        "description": (
            "Generate a textured 3D model from ONE reference image (单图生3D). For multiple views "
            "of the same object use hy3d_generate_model_from_multiview."
        ),
        "example": {"image": {"url": "https://example.com/chair.png"}},
    },
    {
        "tool": "hy3d_generate_model_from_multiview",
        "service": "pro",
        "description": (
            "Generate a textured 3D model from multiple views of the SAME object (多视角生3D). "
            "Supply a main/front image and 1–7 additional views. Each angle once; model 3.0 "
            "supports left/right/back only, model 3.1 (default) supports all listed angles."
        ),
        "example": {
            "image": {"url": "https://example.com/front.png"},
            "multi_view_images": [
                {"view": "back", "image": {"url": "https://example.com/back.png"}}
            ],
        },
    },
    {
        "tool": "hy3d_generate_model_from_sketch",
        "service": "pro",
        "description": (
            "Generate a 3D model from a sketch or line drawing (草图生3D), optionally guided by "
            "text. Uses Pro 3.0 Sketch mode; both image and prompt are allowed here."
        ),
        "example": {"image": {"path": "/absolute/path/sketch.png"}, "prompt": "木制椅子"},
    },
    {
        "tool": "hy3d_generate_low_poly_model",
        "service": "pro",
        "description": (
            "Generate a new model with low-polygon topology (低多边形生成) from text OR image "
            "using Pro 3.0. Quad mode mixes quads and triangles; face count cannot be set. To "
            "simplify an EXISTING model use hy3d_reduce_faces."
        ),
        "example": {"prompt": "低多边形宝箱", "polygon_type": "triangle"},
    },
    {
        "tool": "hy3d_generate_geometry",
        "service": "pro",
        "description": (
            "Generate an untextured mesh/white model (白模生成) from text OR image. Pro Geometry "
            "mode; default output GLB. Use hy3d_generate_texture afterwards to add materials."
        ),
        "example": {"prompt": "一只陶瓷花瓶"},
    },
    {
        "tool": "hy3d_generate_rapid_model",
        "service": "rapid",
        "description": (
            "Generate a 3D model using the Rapid edition (极速版). Text OR image input; text at "
            "most 200 characters. Default output OBJ, or GLB for geometry-only mode. Requires "
            "Tencent Cloud credentials."
        ),
        "example": {"prompt": "一把椅子", "result_format": "GLB"},
    },
    {
        "tool": "hy3d_generate_texture",
        "service": "texture",
        "description": (
            "Generate or replace textures on an EXISTING OBJ/GLB mesh (纹理生成/重绘). Supply the "
            "model URL plus an appearance prompt OR reference image. Supports PBR, keeping UVs, "
            "texture resolution and model 3.1 multi-view texturing. Requires Tencent Cloud "
            "credentials."
        ),
        "example": {
            "file": {"url": "https://example.com/model.glb", "type": "GLB"},
            "prompt": "磨损的棕色皮革",
            "enable_pbr": True,
        },
    },
    {
        "tool": "hy3d_generate_parts",
        "service": "parts",
        "description": (
            "Decompose an EXISTING FBX mesh into semantic 3D components (组件生成/拆分). Convert "
            "OBJ/GLB to FBX with hy3d_convert_format first. staged=true returns editable "
            "segmentation: download PartSegmentationInfoUrl, edit it, then submit the returned "
            "model plus segmentation_info. postprocess adds 20 credits. Requires Tencent Cloud "
            "credentials."
        ),
        "example": {"file": {"url": "https://example.com/model.fbx"}},
    },
    {
        "tool": "hy3d_unwrap_uv",
        "service": "uv",
        "description": (
            "Unwrap UVs for an EXISTING FBX/OBJ/GLB mesh (UV展开). Query the returned task, then "
            "pass its output URL to hy3d_generate_texture with keep_uv=true if desired. "
            "Requires Tencent Cloud credentials."
        ),
        "example": {"file": {"url": "https://example.com/model.glb", "type": "GLB"}},
    },
    {
        "tool": "hy3d_reduce_faces",
        "service": "reduce_faces",
        "description": (
            "Simplify an EXISTING OBJ/GLB mesh (智能减面/拓扑). Select high/medium/low face tier "
            "and triangle/quadrilateral topology. This API has no exact target face count. "
            "Requires Tencent Cloud credentials."
        ),
        "example": {
            "file": {"url": "https://example.com/model.glb", "type": "GLB"},
            "face_level": "low",
        },
    },
    {
        "tool": "hy3d_rig_model",
        "service": "rig",
        "description": (
            "Auto-rig and skin an EXISTING character (自动绑骨/蒙皮), optionally adding a humanoid "
            "motion preset. FBX/GLB ≤60 MB. Humanoids need A/T pose without "
            "weapons/mounts/wings; animals need a simple pose and no motion preset. Preset map: "
            "hy3d_list_capabilities. Requires Tencent Cloud credentials."
        ),
        "example": {"file": {"url": "https://example.com/character.glb", "type": "GLB"}},
    },
    {
        "tool": "hy3d_generate_motion",
        "service": "motion",
        "description": (
            "Generate character animation from text (动作生成) with HY-Motion-1.0, 1–12 seconds. "
            "Optionally retarget onto a model from Hunyuan rigging/animation templates; "
            "arbitrary character rigs are unsupported. Requires Tencent Cloud credentials."
        ),
        "example": {"prompt": "人物向前走几步然后挥手", "duration": 5},
    },
    {
        "tool": "hy3d_generate_profile_model",
        "service": "profile",
        "description": (
            "Generate a stylized 3D person from a portrait and a character template (头像生3D). "
            "JPEG/PNG, each dimension 501–4095 px, encoded <10 MiB. Template enum is in the "
            "schema; labels are in hy3d_list_capabilities. Requires Tencent Cloud credentials."
        ),
        "example": {"image": {"url": "https://example.com/portrait.jpg"}, "template": "basketball"},
    },
    {
        "tool": "hy3d_convert_format",
        "service": "convert",
        "description": (
            "Convert an EXISTING FBX/OBJ/GLB model ≤60 MB to STL/USDZ/FBX, or render MP4/GIF "
            "previews (格式转换). Returns ResultFile3D URL directly, without JobId or polling. Use "
            "FBX output before component generation. Requires Tencent Cloud credentials."
        ),
        "example": {
            "file": {"url": "https://example.com/model.glb", "type": "GLB"},
            "format": "FBX",
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


# One source of truth for field types, descriptions, defaults and cross-field validation.
TOOL_INPUTS: dict[str, type[BaseModel]] = {
    "hy3d_generate_model_from_text": TextTo3DInput,
    "hy3d_generate_model_from_image": ImageTo3DInput,
    "hy3d_generate_model_from_multiview": MultiViewTo3DInput,
    "hy3d_generate_model_from_sketch": SketchTo3DInput,
    "hy3d_generate_low_poly_model": LowPolyInput,
    "hy3d_generate_geometry": GeometryInput,
    "hy3d_generate_rapid_model": RapidInput,
    "hy3d_generate_texture": TextureInput,
    "hy3d_generate_parts": PartsInput,
    "hy3d_unwrap_uv": UVInput,
    "hy3d_reduce_faces": ReduceFacesInput,
    "hy3d_rig_model": RigInput,
    "hy3d_generate_motion": MotionInput,
    "hy3d_generate_profile_model": ProfileInput,
    "hy3d_convert_format": ConvertInput,
}


class ServiceMetadata(FuncMetadata):
    def pre_parse_json(self, data: dict[str, Any]) -> dict[str, Any]:
        parsed = super().pre_parse_json(data)
        # FastMCP only protects bare str by default. Preserve optional text as well,
        # including segmentation JSON and literal "null"/"true" appearance prompts.
        for name, field in self.arg_model.model_fields.items():
            if isinstance(data.get(name), str) and (
                field.annotation is str or str in get_args(field.annotation)
            ):
                parsed[name] = data[name]
        return parsed


def _service_tool(entry: dict[str, Any]) -> Tool:
    """Expose model fields as named MCP arguments without duplicating their schema.

    The MCP argument model inherits the business model, including cross-field validators
    and extra="forbid". ArgModelBase provides the SDK's one-level argument serialization.
    """
    input_model = TOOL_INPUTS[entry["tool"]]

    async def run(ctx: Context, **arguments) -> dict[str, Any]:
        try:
            request = input_model.model_validate(arguments)
            client = ctx.request_context.lifespan_context
            if entry["service"] == "convert":
                return await client.convert(request)
            return await client.submit_service(entry["service"], request, backend="tc3")
        except (HunyuanError, ValueError, OSError) as exc:
            raise ToolError(str(exc)) from None

    run.__name__ = entry["tool"]
    run.__doc__ = entry["description"]
    if entry["service"] != "convert":
        run.__doc__ += (
            " Submits one potentially billable job; never retries. Copy returned "
            "query.arguments or wait.arguments into hy3d_query_job/hy3d_wait_job."
        )
    run.__doc__ += " Example arguments: " + json.dumps(entry["example"], ensure_ascii=False)
    tool = Tool.from_function(run, name=entry["tool"], annotations=WRITE)
    argument_model = create_model(entry["tool"] + "Arguments", __base__=(input_model, ArgModelBase))
    tool.fn_metadata = ServiceMetadata(
        **{**tool.fn_metadata.model_dump(), "arg_model": argument_model}
    )
    tool.parameters = argument_model.model_json_schema()
    return tool


def create_service_tools() -> list[Tool]:
    return [_service_tool(entry) for entry in TOOL_GUIDE]


def register_capability_tool(server: FastMCP, config: Settings) -> None:
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
                    "credentials": "TENCENTCLOUD_SECRET_ID + TENCENTCLOUD_SECRET_KEY",
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
