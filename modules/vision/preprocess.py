"""Image preprocessing — resize before VLM inference to reduce visual token count.

Resizing a 1920×1080 screenshot to 1024 wide cuts visual tokens by ~4x,
reducing per-inference time from ~40s to ~10s on i5-12th Gen CPU.
"""
from __future__ import annotations

import base64
import io
from pathlib import Path

try:
    from PIL import Image
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False

MAX_WIDTH = 1024


def load_and_resize(source) -> "Image.Image":
    """Load an image from a PIL Image, file path, or bytes and resize to MAX_WIDTH."""
    if not _PIL_AVAILABLE:
        raise RuntimeError("Pillow is not installed. Run: pip install Pillow")

    if isinstance(source, Image.Image):
        img = source.convert("RGB")
    elif isinstance(source, (str, Path)):
        img = Image.open(str(source)).convert("RGB")
    elif isinstance(source, bytes):
        img = Image.open(io.BytesIO(source)).convert("RGB")
    else:
        raise TypeError(f"Unsupported image source type: {type(source)}")

    if img.width > MAX_WIDTH:
        ratio = MAX_WIDTH / img.width
        new_height = max(1, int(img.height * ratio))
        img = img.resize((MAX_WIDTH, new_height), Image.LANCZOS)

    return img


def image_to_base64_jpeg(img: "Image.Image", quality: int = 85) -> str:
    """Encode a PIL Image as a base64 JPEG string."""
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def image_to_data_uri(img: "Image.Image") -> str:
    """Return a data URI for use in llama_cpp multimodal chat messages."""
    return f"data:image/jpeg;base64,{image_to_base64_jpeg(img)}"
