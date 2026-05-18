"""
On-demand VLM captioning of one media asset.

``caption()`` looks up the asset's record in ``<library>/.pixelkasten/``,
runs a local VLM (via Ollama) on the image or on N evenly-sampled frames of
a video, and writes the resulting caption back to the record. Idempotent:
if ``caption`` is already present in the record and ``force=False``, the
existing caption is returned without invoking the model.
"""

import io
import os
import sys

from pixelkasten.handlers import is_image, is_video
from pixelkasten.utils.record import read_record, write_record
from pixelkasten.utils.record import record_path, records_dir_home

# Inherited convention from earlier discovery passes; balances VLM payload size
# against caption accuracy on typical mid-resolution sources.
MAX_EDGE = 768


def caption(
    path: str,
    model: str,
    video_frames: int,
    force: bool = False,
) -> str | None:
    """
    Caption one asset and persist the result to its record.

    Returns the caption string on success (whether freshly generated or
    re-used from the record), or None on failure. The record is left
    untouched on failure.
    """
    library = records_dir_home(path)
    rpath = record_path(library, os.path.basename(path))
    data = read_record(rpath)

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
    write_record(rpath, data)
    return text


def _generate(path: str, model: str, video_frames: int) -> str | None:
    if is_image(path):
        return _caption_image(path, model)
    if is_video(path):
        return _caption_video(path, model, video_frames)
    ext = os.path.splitext(path)[1].lower()
    raise RuntimeError(f"Unsupported extension {ext} for {path}")


def _caption_image(path: str, model: str) -> str | None:
    from PIL import Image

    from pixelkasten.utils.ollama import chat
    from pixelkasten.utils.pil import ensure_pil_plugins

    ensure_pil_plugins()

    img = Image.open(path).convert("RGB")
    payload = _to_jpeg_bytes(_downscale(img))

    return chat(model, "Describe this photo in one short sentence.", images=[payload])


def _caption_video(path: str, model: str, n_frames: int) -> str | None:
    from PIL import Image

    from pixelkasten.utils.ffmpeg import capture_frames
    from pixelkasten.utils.ollama import chat

    raw_frames = capture_frames(path, n_frames)
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
    # Caller is expected to have flattened to RGB; JPEG doesn't carry alpha
    # and PIL raises on RGBA inputs. quality=90 is the conventional sweet
    # spot for VLM caption queries — smaller payloads visibly degrade
    # detail; larger ones rarely help.
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()
