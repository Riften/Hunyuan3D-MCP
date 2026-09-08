"""TC3-HMAC-SHA256 signing for the fixed Tencent AI3D endpoint."""

import hashlib
import hmac
from datetime import UTC, datetime

from .services import API_VERSION, TC3_HOST


def tc3_headers(
    body: bytes,
    action: str,
    secret_id: str,
    secret_key: str,
    timestamp: int,
    *,
    token: str = "",
    region: str = "",
) -> dict[str, str]:
    date = datetime.fromtimestamp(timestamp, UTC).strftime("%Y-%m-%d")
    content_type = "application/json"
    signed_headers = "content-type;host"
    canonical = (
        f"POST\n/\n\ncontent-type:{content_type}\nhost:{TC3_HOST}\n\n"
        f"{signed_headers}\n{hashlib.sha256(body).hexdigest()}"
    )
    scope = f"{date}/ai3d/tc3_request"
    to_sign = (
        f"TC3-HMAC-SHA256\n{timestamp}\n{scope}\n{hashlib.sha256(canonical.encode()).hexdigest()}"
    )

    def sign(key: bytes, value: str) -> bytes:
        return hmac.new(key, value.encode(), hashlib.sha256).digest()

    key = sign(sign(sign(("TC3" + secret_key).encode(), date), "ai3d"), "tc3_request")
    signature = sign(key, to_sign).hex()
    headers = {
        "Authorization": (
            f"TC3-HMAC-SHA256 Credential={secret_id}/{scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        ),
        "Content-Type": content_type,
        "Host": TC3_HOST,
        "X-TC-Action": action,
        "X-TC-Version": API_VERSION,
        "X-TC-Timestamp": str(timestamp),
    }
    if token:
        headers["X-TC-Token"] = token
    if region:
        headers["X-TC-Region"] = region
    return headers
