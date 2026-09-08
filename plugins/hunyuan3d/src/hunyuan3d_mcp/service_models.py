"""Service-specific, agent-discoverable inputs for the public Tencent AI3D API."""

import base64
import binascii
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .models import MAX_IMAGE_BYTES, GenerationInput, validate_image


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ImageSource(Input):
    """Exactly one image source. Local files are encoded and uploaded to Tencent."""

    url: str | None = Field(
        None,
        min_length=1,
        max_length=8192,
        description="Public HTTP(S) image URL fetchable by Tencent; no embedded credentials.",
    )
    path: str | None = Field(None, min_length=1, description="Absolute local image file path.")
    base64: str | None = Field(
        None,
        min_length=1,
        repr=False,
        description="Raw base64 or a base64 image data URI.",
    )

    @field_validator("url")
    @classmethod
    def valid_url(cls, value):
        return GenerationInput.public_url(value)

    @model_validator(mode="after")
    def one_source(self) -> Self:
        if sum(v is not None for v in (self.url, self.path, self.base64)) != 1:
            raise ValueError("Supply exactly one image source: url, path or base64.")
        return self

    def payload(self, *, kind: str = "generation") -> dict:
        if self.url:
            return {"Url": self.url}
        limits = {}
        max_bytes = MAX_IMAGE_BYTES
        if kind in {"texture", "profile"}:
            max_bytes = (10 * 1024 * 1024 - 1) // 4 * 3
            limits = dict(
                min_side=501 if kind == "profile" else 129,
                max_side=4095,
                formats=frozenset({"JPEG", "PNG"}),
            )
        elif kind == "view":
            limits = dict(min_side=129, max_side=4999, formats=frozenset({"JPEG", "PNG"}))
        if self.path:
            path = Path(self.path).expanduser()
            if not path.is_absolute() or not path.is_file():
                raise ValueError("Image path must be an absolute path to an existing regular file.")
            with path.open("rb") as stream:
                data = stream.read(max_bytes + 1)
        else:
            encoded = self.base64
            if encoded.startswith("data:"):
                header, separator, encoded = encoded.partition(",")
                if not separator or not header.endswith(";base64"):
                    raise ValueError("Expected a base64 image data URI.")
            if len(encoded) > 4 * ((max_bytes + 2) // 3):
                raise ValueError("Base64 image exceeds this service's size limit.")
            try:
                data = base64.b64decode(encoded, validate=True)
            except (binascii.Error, ValueError) as exc:
                raise ValueError("Invalid image base64 encoding.") from exc
        uri = validate_image(data, max_bytes=max_bytes, **limits)
        return {"Base64": uri.split(",", 1)[1]}


class ModelFile(Input):
    url: str = Field(
        min_length=1,
        max_length=8192,
        description="Public HTTP(S) model URL, e.g. ResultFile3Ds[].Url. Upload local "
        "models first.",
    )
    type: Literal["OBJ", "GLB", "FBX"] = Field(description="Actual input file format, uppercase.")

    @field_validator("url")
    @classmethod
    def valid_url(cls, value):
        return GenerationInput.public_url(value)

    def payload(self) -> dict:
        return {"Url": self.url, "Type": self.type}


class TextureFile(ModelFile):
    type: Literal["OBJ", "GLB"] = Field(description="Texture/reduction input: OBJ or GLB.")


class PartFile(ModelFile):
    type: Literal["FBX"] = Field(
        "FBX", description="Components require FBX; convert first if needed."
    )


class RigFile(ModelFile):
    type: Literal["FBX", "GLB"] = Field(description="Rigging input: FBX or GLB, at most 60 MB.")


class ViewImage(Input):
    view: Literal["left", "right", "back", "top", "bottom", "left_front", "right_front"] = Field(
        description="View of the same object; each view once. Extra angles require model 3.1."
    )
    image: ImageSource = Field(
        description="JPEG/PNG; each dimension 129–4999; total encoded ≤8 MiB."
    )

    def payload(self) -> dict:
        data = self.image.payload(kind="view")
        return {"ViewType": self.view, **{"ViewImage" + key: value for key, value in data.items()}}


def check_views(views: list[ViewImage], model: str, *, texture: bool = False) -> None:
    if len({view.view for view in views}) != len(views):
        raise ValueError("Each view may appear only once.")
    if model == "3.0" and any(
        texture or view.view not in {"left", "right", "back"} for view in views
    ):
        raise ValueError("These multi-view inputs require model 3.1.")


FaceCount = Annotated[int, Field(ge=3000, le=1500000, strict=True)]
ResultFormat = Literal["STL", "USDZ", "FBX"]


class ProOptions(Input):
    model: Literal["3.0", "3.1"] = Field("3.0", description="Hunyuan Pro model version.")
    face_count: FaceCount | None = Field(None, description="Target faces; API default 500000.")
    result_format: ResultFormat | None = Field(
        None,
        description="Omit for OBJ/GLB (geometry: GLB); set to return only STL, USDZ or FBX.",
    )

    def generation(self, mode: str = "Normal") -> GenerationInput:
        values = self.model_dump(exclude={"image", "multi_view_images"})
        if isinstance(self, ImageTo3DInput):
            image = self.image.model_dump(exclude_none=True)
            values.update({"image_" + key: value for key, value in image.items()})
        return GenerationInput(**values, generate_type=mode)

    def to_payload(self) -> dict:
        # Compatibility endpoint shape; the client adapts ImageUrl for TC3.
        payload = self.generation().to_payload()
        if isinstance(self, ImageTo3DInput) and self.multi_view_images:
            payload["MultiViewImages"] = [view.payload() for view in self.multi_view_images]
        return payload


class TextTo3DInput(ProOptions):
    prompt: str = Field(
        min_length=1, max_length=1024, description="Describe the 3D object; Chinese supported."
    )
    enable_pbr: bool = Field(False, description="Generate physically based rendering materials.")


class ImageTo3DInput(ProOptions):
    image: ImageSource = Field(
        description="Front/main image; JPEG/PNG/WebP, 128–5000 px, local ≤6 MiB."
    )
    multi_view_images: list[ViewImage] = Field(
        default_factory=list,
        max_length=7,
        description="Optional additional views; requires TC3.",
    )
    enable_pbr: bool = Field(False, description="Generate physically based rendering materials.")

    @model_validator(mode="after")
    def views_valid(self) -> Self:
        check_views(self.multi_view_images, self.model)
        return self


class SketchTo3DInput(Input):
    image: ImageSource = Field(
        description="Sketch/line drawing; JPEG/PNG/WebP, 128–5000 px, ≤6 MiB."
    )
    prompt: str | None = Field(
        None, min_length=1, max_length=1024, description="Optional description guiding the sketch."
    )
    enable_pbr: bool = Field(False, description="Generate PBR materials.")
    face_count: FaceCount | None = Field(None, description="Target faces; API default 500000.")
    result_format: ResultFormat | None = Field(None, description="Omit for OBJ/GLB outputs.")

    def to_payload(self) -> dict:
        values = self.model_dump(exclude={"image"})
        values.update(
            {"image_" + k: v for k, v in self.image.model_dump(exclude_none=True).items()}
        )
        return GenerationInput(**values, model="3.0", generate_type="Sketch").to_payload()


class PromptOrImage(Input):
    prompt: str | None = Field(
        None,
        min_length=1,
        max_length=1024,
        description="Text describing the object; omit with image.",
    )
    image: ImageSource | None = Field(None, description="Reference image; omit with prompt.")

    @model_validator(mode="after")
    def exclusive(self) -> Self:
        if (self.prompt is None) == (self.image is None):
            raise ValueError("Supply exactly one of prompt or image.")
        return self

    def source_payload(self, *, kind: str = "generation", nested: bool = False) -> dict:
        if self.prompt is not None:
            return {"Prompt": self.prompt}
        data = self.image.payload(kind=kind)
        return {"Image": data} if nested else {"Image" + k: v for k, v in data.items()}

    def pro_payload(self, mode: str, **options) -> dict:
        values = {"prompt": self.prompt}
        if self.image:
            values.update(
                {"image_" + k: v for k, v in self.image.model_dump(exclude_none=True).items()}
            )
        return GenerationInput(**values, generate_type=mode, **options).to_payload()


class LowPolyInput(PromptOrImage):
    polygon_type: Literal["triangle", "quadrilateral"] = Field(
        "triangle",
        description="quadrilateral creates a mix of quads and triangles; no face count control.",
    )
    enable_pbr: bool = Field(False, description="Generate PBR materials.")
    result_format: ResultFormat | None = Field(None, description="Omit for OBJ/GLB outputs.")

    def to_payload(self) -> dict:
        return self.pro_payload(
            "LowPoly",
            model="3.0",
            polygon_type=self.polygon_type,
            enable_pbr=self.enable_pbr,
            result_format=self.result_format,
        )


class GeometryInput(PromptOrImage, ProOptions):
    def to_payload(self) -> dict:
        return self.pro_payload(
            "Geometry",
            model=self.model,
            face_count=self.face_count,
            result_format=self.result_format,
        )


class RapidInput(PromptOrImage):
    prompt: str | None = Field(
        None,
        min_length=1,
        max_length=200,
        description="Object description, at most 200 characters; omit with image.",
    )
    result_format: Literal["OBJ", "GLB", "STL", "USDZ", "FBX", "MP4"] | None = Field(
        None,
        description="Omit for OBJ; geometry defaults to GLB and cannot return OBJ.",
    )
    enable_pbr: bool = Field(False, description="Generate PBR materials.")
    enable_geometry: bool = Field(False, description="Generate untextured geometry only.")

    @model_validator(mode="after")
    def geometry_options(self) -> Self:
        if self.enable_geometry and (self.result_format == "OBJ" or self.enable_pbr):
            raise ValueError("Geometry mode does not support OBJ or PBR.")
        return self

    def to_payload(self) -> dict:
        payload = self.source_payload() | {
            "EnablePBR": self.enable_pbr,
            "EnableGeometry": self.enable_geometry,
        }
        if self.result_format:
            payload["ResultFormat"] = self.result_format
        return payload


class TextureInput(PromptOrImage):
    file: TextureFile = Field(description="Existing mesh to texture/retexture; OBJ or GLB.")
    prompt: str | None = Field(
        None,
        min_length=1,
        max_length=200,
        description="Describe surface appearance, at most 200 characters; omit with image.",
    )
    image: ImageSource | None = Field(
        None,
        description="Texture reference instead of prompt; JPEG/PNG, 129–4095 px, encoded <10 MiB.",
    )
    model: Literal["3.0", "3.1"] = Field(
        "3.0", description="Texture model; multi-view requires 3.1."
    )
    multi_view_images: list[ViewImage] = Field(
        default_factory=list,
        max_length=7,
        description="Additional texture views, with a main image, model 3.1 only.",
    )
    enable_pbr: bool = Field(False, description="Generate PBR material maps.")
    keep_uv: bool = Field(False, description="Keep the source model's UV layout.")
    texture_size: int = Field(
        4096, ge=720, le=4096, strict=True, description="Square texture resolution in pixels."
    )

    @model_validator(mode="after")
    def views_valid(self) -> Self:
        check_views(self.multi_view_images, self.model, texture=True)
        if self.multi_view_images and self.image is None:
            raise ValueError("Multi-view texturing requires a main image, not a prompt.")
        return self

    def to_payload(self) -> dict:
        payload = self.source_payload(kind="texture", nested=True) | {
            "File3D": self.file.payload(),
            "Model": self.model,
            "EnablePBR": self.enable_pbr,
            "EnableKeepUV": self.keep_uv,
            "TextureSize": self.texture_size,
        }
        if self.multi_view_images:
            payload["MultiViewImages"] = [view.payload() for view in self.multi_view_images]
        return payload


class PartsInput(Input):
    file: PartFile = Field(description="Existing FBX mesh to decompose into semantic components.")
    model: Literal["1.5"] = Field("1.5", description="Component generation model version.")
    staged: bool = Field(
        False,
        description="Generate editable segmentation first; use returned model and "
        "segmentation in a subsequent submission.",
    )
    segmentation_info: str | None = Field(
        None,
        min_length=1,
        description="Edited segmentation JSON string, not a URL; download "
        "PartSegmentationInfoUrl first.",
    )
    postprocess: bool = Field(
        False,
        description="Return a single processed model link; adds 20 credits per "
        "official API documentation.",
    )

    def to_payload(self) -> dict:
        payload = {
            "File": self.file.payload(),
            "Model": self.model,
            "EnableStagedGeneration": self.staged,
            "EnablePostProcess": self.postprocess,
        }
        if self.segmentation_info is not None:
            payload["PartSegmentationInfo"] = self.segmentation_info
        return payload


class UVInput(Input):
    file: ModelFile = Field(description="Existing FBX/OBJ/GLB mesh to UV unwrap.")

    def to_payload(self) -> dict:
        return {"File": self.file.payload()}


class ReduceFacesInput(Input):
    file: TextureFile = Field(description="Existing OBJ/GLB mesh to simplify.")
    polygon_type: Literal["triangle", "quadrilateral"] = Field(
        "triangle", description="Output polygon topology."
    )
    face_level: Literal["high", "medium", "low"] = Field(
        "medium", description="Relative target face-count tier; API does not expose an exact count."
    )

    def to_payload(self) -> dict:
        return {
            "File3D": self.file.payload(),
            "PolygonType": self.polygon_type,
            "FaceLevel": self.face_level,
        }


MOTION_PRESETS = dict(
    enumerate(
        [
            "回旋踢",
            "左勾拳",
            "蓄力攻击",
            "蓄力出拳",
            "二连击打",
            "二连击打-2",
            "后撤",
            "受击",
            "受击-2",
            "受击-3",
            "受击倒地-1",
            "受击倒地-2",
            "落地",
            "沮丧",
            "割喉",
            "刺拳",
            "连续击打",
            "踢腿",
            "侧踢",
            "打太极",
            "后空翻",
            "蹲姿转体",
            "走路-1",
            "走路-2",
            "走路-3",
            "待机-1",
            "待机-2",
            "街舞",
            "扭扭舞",
            "左转弯",
            "右转弯",
            "慢跑",
            "慢跑-2",
            "奔跑",
            "冲刺跑-1",
            "冲刺跑-2",
            "冲刺跑-3",
            "原地跳-1",
            "滑铲",
            "向前大跳",
            "向前大跳-2",
            "跨越",
            "恐吓",
            "向前跌倒",
            "右转",
            "原地跳-2",
            "转身",
            "发送冲击波",
        ],
        start=1,
    )
)


class RigInput(Input):
    file: RigFile = Field(
        description="Single character, ≤60 MB. Humanoid: A/T pose, no "
        "weapons/mounts/wings. Animals: simple pose, no motion preset."
    )
    motion_type: int | None = Field(
        None,
        ge=1,
        le=48,
        strict=True,
        description="Optional humanoid preset ID; omit for rig only. 23=walk, 26=idle,"
        " 34=run. Full mapping: hy3d_list_capabilities.",
    )

    def to_payload(self) -> dict:
        payload = {"File3D": self.file.payload()}
        if self.motion_type is not None:
            payload["MotionType"] = self.motion_type
        return payload


class MotionInput(Input):
    prompt: str = Field(
        min_length=1,
        max_length=128,
        description="Describe the desired character motion, up to 128 characters.",
    )
    model: Literal["HY-Motion-1.0"] = Field("HY-Motion-1.0", description="Motion generation model.")
    retarget_file: RigFile | None = Field(
        None,
        description="Optional character returned by Hunyuan auto-rigging/animation "
        "templates; arbitrary rigs unsupported.",
    )
    duration: int = Field(5, ge=1, le=12, strict=True, description="Animation duration in seconds.")
    enable_mesh: bool = Field(True, description="Include skinned mesh in returned FBX.")
    rewrite_prompt: bool = Field(False, description="Let the service expand the motion prompt.")
    estimate_duration: bool = Field(
        False, description="Let the service estimate duration from the prompt."
    )

    def to_payload(self) -> dict:
        payload = {
            "Prompt": self.prompt,
            "Model": self.model,
            "Duration": self.duration,
            "EnableMesh": self.enable_mesh,
            "EnableRewrite": self.rewrite_prompt,
            "EnableDurationEst": self.estimate_duration,
        }
        if self.retarget_file:
            payload["RetargetFile"] = self.retarget_file.payload()
        return payload


class ProfileInput(Input):
    image: ImageSource = Field(description="Portrait photo; JPEG/PNG, 501–4095 px, base64 <10 MiB.")
    template: Literal[
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
    ] = Field(
        description="Character template. API spelling futuresoilder is intentional; "
        "see hy3d_list_capabilities for labels."
    )

    def to_payload(self) -> dict:
        return {"Profile": self.image.payload(kind="profile"), "Template": self.template}


class ConvertInput(Input):
    file: ModelFile = Field(description="Source FBX/OBJ/GLB model, at most 60 MB.")
    format: Literal["STL", "USDZ", "FBX", "MP4", "GIF"] = Field(
        description="Output format; MP4/GIF create a rendered preview."
    )

    def to_payload(self) -> dict:
        return {"File3D": self.file.url, "Format": self.format}
