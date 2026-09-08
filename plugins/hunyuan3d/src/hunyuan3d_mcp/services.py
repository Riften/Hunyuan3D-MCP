"""Documented Tencent AI3D actions; never derive remote action names from user input."""

from dataclasses import dataclass
from typing import Literal

Service = Literal[
    "pro", "rapid", "texture", "parts", "uv", "reduce_faces", "rig", "motion", "profile"
]
Backend = Literal["auto", "tc3"]


@dataclass(frozen=True)
class ServiceActions:
    submit: str
    query: str


SERVICES = {
    "pro": ServiceActions("SubmitHunyuanTo3DProJob", "QueryHunyuanTo3DProJob"),
    "rapid": ServiceActions("SubmitHunyuanTo3DRapidJob", "QueryHunyuanTo3DRapidJob"),
    "texture": ServiceActions("SubmitTextureTo3DJob", "DescribeTextureTo3DJob"),
    "parts": ServiceActions("SubmitHunyuan3DPartJob", "QueryHunyuan3DPartJob"),
    "uv": ServiceActions("SubmitHunyuanTo3DUVJob", "DescribeHunyuanTo3DUVJob"),
    "reduce_faces": ServiceActions("SubmitReduceFaceJob", "DescribeReduceFaceJob"),
    "rig": ServiceActions("SubmitAutoRiggingJob", "DescribeAutoRiggingJob"),
    "motion": ServiceActions("SubmitHunyuanTo3DMotionJob", "DescribeHunyuanTo3DMotionJob"),
    "profile": ServiceActions("SubmitProfileTo3DJob", "DescribeProfileTo3DJob"),
}
TC3_HOST = "ai3d.tencentcloudapi.com"
API_VERSION = "2025-05-13"
