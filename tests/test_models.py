import base64
import io

import pytest
from PIL import Image
from pydantic import ValidationError

from hunyuan3d_mcp.models import MAX_IMAGE_BYTES, GenerationInput


def png(size=(128, 128)):
    buffer = io.BytesIO()
    Image.new("RGB", size, "red").save(buffer, format="PNG")
    return buffer.getvalue()


def test_text_payload():
    assert GenerationInput(prompt="  chair  ").to_payload() == {
        "Prompt": "chair",
        "Model": "3.0",
        "GenerateType": "Normal",
        "EnablePBR": False,
    }


@pytest.mark.parametrize(
    "fields",
    [
        {},
        {"prompt": " "},
        {"prompt": "x" * 1025},
        {"prompt": "chair", "image_url": "https://example.com/a.png"},
        {"image_url": "https://example.com/a.png", "image_path": "/tmp/a.png"},
        {"image_url": "file:///tmp/a.png"},
        {"image_url": "https://user:pass@example.com/a.png"},
        {"prompt": "chair", "model": "2.5"},
        {"prompt": "chair", "model": "3.1", "generate_type": "LowPoly"},
        {"image_url": "https://example.com/a.png", "model": "3.1", "generate_type": "Sketch"},
        {"prompt": "chair", "generate_type": "Sketch"},
        {"prompt": "chair", "polygon_type": "triangle"},
        {"prompt": "chair", "face_count": 2999},
        {"prompt": "chair", "face_count": 1500001},
        {"prompt": "chair", "face_count": True},
        {"prompt": "chair", "generate_type": "LowPoly", "face_count": 3000},
        {"prompt": "chair", "generate_type": "Geometry", "enable_pbr": True},
        {"prompt": "chair", "result_format": "GLB"},
        {"prompt": "chair", "unknown": "field"},
    ],
)
def test_invalid_inputs(fields):
    with pytest.raises(ValidationError):
        GenerationInput(**fields)


def test_image_url_and_sketch_payload():
    payload = GenerationInput(
        prompt="chair", image_url="https://example.com/sketch.png", generate_type="Sketch"
    ).to_payload()
    assert payload["ImageUrl"] == {"Url": "https://example.com/sketch.png"}
    assert payload["Prompt"] == "chair"


def test_local_image_and_base64_match(tmp_path):
    image = tmp_path / "input.png"
    image.write_bytes(png())
    expected = "data:image/png;base64," + base64.b64encode(png()).decode()
    assert GenerationInput(image_path=str(image)).to_payload()["ImageUrl"] == {"Url": expected}
    for value in (expected, expected.split(",")[1]):
        assert GenerationInput(image_base64=value).to_payload()["ImageUrl"] == {"Url": expected}


@pytest.mark.parametrize(
    "data",
    [
        b"not an image",
        png((127, 128)),
        png((5001, 128)),
        b"x" * (MAX_IMAGE_BYTES + 1),
    ],
)
def test_invalid_image_files(tmp_path, data):
    image = tmp_path / "input.png"
    image.write_bytes(data)
    with pytest.raises(ValueError):
        GenerationInput(image_path=str(image)).to_payload()


@pytest.mark.parametrize("value", ["%%%", "data:image/png,abcdef", "abc", "a" * (9 * 1024 * 1024)])
def test_invalid_base64(value):
    with pytest.raises(ValueError):
        GenerationInput(image_base64=value).to_payload()


def test_relative_path_and_directory_rejected(tmp_path):
    for value in ("relative.png", str(tmp_path), str(tmp_path / "missing.png")):
        with pytest.raises(ValueError):
            GenerationInput(image_path=value).to_payload()
