"""
On-demand VLM captioning of one media asset.

`caption()` looks up the sidecar in `<library>/.pixelkasten/`, runs a local
VLM (via Ollama) on the image or on N evenly-sampled frames of a video, and
writes the resulting caption back to the sidecar. Idempotent: if `caption`
is already present in the sidecar and `force=False`, the existing caption
is returned without invoking the model.
"""

import io
import json
import os
import sys

DEFAULT_MODEL = "gemma4:e4b"
MAX_EDGE = 768

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".heic", ".png", ".mp"}
VIDEO_EXTENSIONS = {".mp4", ".mov"}

SIDECAR_DIR = ".pixelkasten"
SIDECAR_SUFFIX = ".pk.json"


def caption(
    path: str,
    force: bool = False,
    model: str = DEFAULT_MODEL,
    video_frames: int = 5,
) -> str | None:
    """
    Caption one asset and persist the result to its sidecar.

    Returns the caption string on success (whether freshly generated or
    re-used from the sidecar), or None on failure. Sidecar file is left
    untouched on failure.
    """
    library = _resolve_library(path)
    sidecar_path = _sidecar_path(library, path)
    data = _read_json(sidecar_path)

    existing = data.get("caption")
    if existing and not force:
        return existing

    try:
        text = _generate(path, model, video_frames)
    except Exception as e:
        print(f"caption: failed for {path}: {e}", file=sys.stderr)
        return None

    if not text:
        print(f"caption: model returned empty caption for {path}", file=sys.stderr)
        return None

    data["caption"] = text
    _write_json(sidecar_path, data)
    return text


def _generate(path: str, model: str, video_frames: int) -> str | None:
    ext = os.path.splitext(path)[1].lower()
    if ext in IMAGE_EXTENSIONS:
        return _caption_image(path, model)
    if ext in VIDEO_EXTENSIONS:
        return _caption_video(path, model, video_frames)
    raise RuntimeError(f"Unsupported extension {ext} for {path}")


def _caption_image(path: str, model: str) -> str | None:
    from PIL import Image

    from pixelkasten.tools.ollama import chat
    from pixelkasten.tools.pil_setup import ensure_pil_plugins

    ensure_pil_plugins()
    img = Image.open(path).convert("RGB")
    payload = _to_jpeg_bytes(_downscale(img))
    return chat(model, "Describe this photo in one short sentence.", images=[payload])


def _caption_video(path: str, model: str, n_frames: int) -> str | None:
    from PIL import Image

    from pixelkasten.tools.ffmpeg import extract_frames
    from pixelkasten.tools.ollama import chat

    raw_frames = extract_frames(path, n_frames)
    payloads = [
        _to_jpeg_bytes(_downscale(Image.open(io.BytesIO(b)).convert("RGB"))) for b in raw_frames
    ]
    prompt = (
        f"These {len(payloads)} images are frames of a single video sampled evenly "
        "across its duration. Describe the video in one short sentence."
    )
    return chat(model, prompt, images=payloads)


def _downscale(img):
    """Resize so the longer edge is at most MAX_EDGE; preserve aspect ratio."""
    w, h = img.size
    longer = max(w, h)
    if longer <= MAX_EDGE:
        return img
    scale = MAX_EDGE / longer
    return img.resize((int(w * scale), int(h * scale)))


def _to_jpeg_bytes(img) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def _resolve_library(path: str) -> str:
    current = os.path.dirname(os.path.abspath(path))
    while True:
        if os.path.isdir(os.path.join(current, SIDECAR_DIR)):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            raise RuntimeError(
                f"No {SIDECAR_DIR}/ found at or above {path}; is this inside a working library?"
            )
        current = parent


def _sidecar_path(library: str, asset_path: str) -> str:
    return os.path.join(library, SIDECAR_DIR, os.path.basename(asset_path) + SIDECAR_SUFFIX)


def _read_json(path: str) -> dict:
    if not os.path.exists(path):
        raise RuntimeError(f"No sidecar at {path}; was this asset emitted by init?")
    with open(path) as f:
        return json.load(f)


def _write_json(path: str, data: dict) -> None:
    with open(path, "w") as f:
        json.dump(data, f)
