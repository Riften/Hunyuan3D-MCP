"""Validate generation inputs before making a potentially billable request."""

import base64
import binascii
import io
from pathlib import Path
from typing import Literal, Self
from urllib.parse import urlsplit

from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MAX_IMAGE_BYTES = 6 * 1024 * 1024
MAX_REQUEST_BYTES = 8 * 1024 * 1024


def validate_image(
    data: bytes,
    *,
    max_bytes: int = MAX_IMAGE_BYTES,
    min_side: int = 128,
    max_side: int = 5000,
    formats: frozenset[str] = frozenset({"JPEG", "PNG", "WEBP"}),
) -> str:
    if not data or len(data) > max_bytes:
        raise ValueError(f"Image must be nonempty and at most {max_bytes} bytes before encoding.")
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.format not in formats:
                raise ValueError(f"Supported image formats: {', '.join(sorted(formats))}.")
            if not all(min_side <= side <= max_side for side in image.size):
                raise ValueError(f"Each image dimension must be between {min_side} and {max_side}.")
            mime = Image.MIME[image.format]
            image.verify()
    except (OSError, SyntaxError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
        raise ValueError("Invalid or damaged image.") from exc
    return f"data:{mime};base64," + base64.b64encode(data).decode("ascii")


class GenerationInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    prompt: str | None = Field(default=None, min_length=1, max_length=1024)
    image_url: str | None = Field(default=None, min_length=1, max_length=8192)
    image_path: str | None = Field(default=None, min_length=1)
    image_base64: str | None = Field(default=None, min_length=1, repr=False)
    model: Literal["3.0", "3.1"] = "3.0"
    generate_type: Literal["Normal", "LowPoly", "Geometry", "Sketch"] = "Normal"
    enable_pbr: bool = False
    face_count: int | None = Field(default=None, ge=3000, le=1500000, strict=True)
    polygon_type: Literal["triangle", "quadrilateral"] | None = None
    result_format: Literal["STL", "USDZ", "FBX"] | None = None

    @field_validator("image_url")
    @classmethod
    def public_url(cls, value: str | None) -> str | None:
        if value is not None:
            parsed = urlsplit(value)
            if parsed.scheme not in {"https", "http"} or not parsed.hostname:
                raise ValueError("image_url must be an absolute HTTP(S) URL.")
            if parsed.username or parsed.password:
                raise ValueError("image_url must not contain credentials.")
        return value

    @model_validator(mode="after")
    def check_combinations(self) -> Self:
        images = sum(x is not None for x in (self.image_url, self.image_path, self.image_base64))
        if images > 1:
            raise ValueError("Supply only one of image_url, image_path and image_base64.")
        if not images and not self.prompt:
            raise ValueError("Supply a prompt or an image.")
        if images and self.prompt and self.generate_type != "Sketch":
            raise ValueError("A prompt and an image can be combined only in Sketch mode.")
        if self.generate_type == "Sketch" and not images:
            raise ValueError("Sketch mode requires an image.")
        if self.model == "3.1" and self.generate_type in {"LowPoly", "Sketch"}:
            raise ValueError("The API Key endpoint does not support LowPoly/Sketch with model 3.1.")
        if self.polygon_type and self.generate_type != "LowPoly":
            raise ValueError("polygon_type requires LowPoly mode.")
        if self.face_count is not None and self.generate_type == "LowPoly":
            raise ValueError("face_count has no effect in LowPoly mode; omit it.")
        if self.enable_pbr and self.generate_type == "Geometry":
            raise ValueError("enable_pbr has no effect in Geometry mode; disable it.")
        return self

    def to_payload(self) -> dict:
        payload = {
            "Model": self.model,
            "GenerateType": self.generate_type,
            "EnablePBR": self.enable_pbr,
        }
        for key, value in (
            ("Prompt", self.prompt),
            ("FaceCount", self.face_count),
            ("PolygonType", self.polygon_type),
            ("ResultFormat", self.result_format),
        ):
            if value is not None:
                payload[key] = value
        image = self.image_url
        if self.image_path:
            path = Path(self.image_path).expanduser()
            if not path.is_absolute():
                raise ValueError("image_path must be absolute.")
            if not path.is_file():
                raise ValueError("image_path must point to an existing regular file.")
            with path.open("rb") as stream:
                image = validate_image(stream.read(MAX_IMAGE_BYTES + 1))
        elif self.image_base64:
            encoded = self.image_base64
            if encoded.startswith("data:"):
                header, separator, encoded = encoded.partition(",")
                if not separator or not header.endswith(";base64"):
                    raise ValueError("Expected a base64 image data URI.")
            if len(encoded) > 4 * ((MAX_IMAGE_BYTES + 2) // 3):
                raise ValueError("Base64 image exceeds the 6 MiB decoded size limit.")
            try:
                data = base64.b64decode(encoded, validate=True)
            except (binascii.Error, ValueError) as exc:
                raise ValueError("Invalid image base64 encoding.") from exc
            image = validate_image(data)
        if image:
            # The API Key compatibility endpoint documents ImageUrl.Url, unlike TC3.
            payload["ImageUrl"] = {"Url": image}
        return payload


class JobInput(BaseModel):
    job_id: str = Field(min_length=1, max_length=128, pattern=r"^[0-9]+$")
