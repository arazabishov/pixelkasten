"""
VLM captioning via Ollama.

Sends cluster representative images to a local vision-language model
running on Ollama to generate free-form captions. Images are downscaled
before sending to reduce vision encoder processing time.

Prerequisites:
    - Ollama installed and running (`ollama serve`)
    - A vision model pulled (`ollama pull gemma4:e4b`)
"""

import io
from typing import Callable

from pixelkasten.configuration import DiscoveryOptions
from pixelkasten.manifest import ManifestEntry, Status
from pixelkasten.tools.ollama import chat

MAX_EDGE = 768

DEFAULT_PROMPT = (
    "Describe this photograph in 1-2 sentences. "
    "Focus on the main subject, setting, and any notable activity or event."
)


def _downscale(image_path: str) -> bytes:
    """
    Load an image, downscale to MAX_EDGE preserving aspect ratio,
    and return JPEG bytes. Skips resizing if already small enough.
    """
    from PIL import Image

    img = Image.open(image_path).convert("RGB")
    if max(img.size) > MAX_EDGE:
        img.thumbnail((MAX_EDGE, MAX_EDGE))

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def caption_image(model: str, image_path: str, prompt: str) -> str | None:
    """
    Send a single image to Ollama and return the caption text.

    Downscales the image before sending to speed up inference.
    Returns None if captioning fails so the pipeline can continue.
    """
    try:
        image_bytes = _downscale(image_path)
        return chat(model, prompt, images=[image_bytes])
    except Exception:
        return None


def caption_representatives(
    entries: list[ManifestEntry],
    options: DiscoveryOptions,
    on_progress: Callable[[int], None] | None = None,
) -> None:
    """
    Caption all representative images, writing results to entry.discovery.caption.

    Reads `caption_model` from options. Skips entries where captioning fails
    so the pipeline can continue.
    """
    representatives = [
        entry
        for entry in entries
        if entry.discovery
        and entry.discovery.is_representative
        and entry.discovery.status == Status.PROCESSED
    ]

    for i, entry in enumerate(representatives):
        caption = caption_image(options.caption_model, entry.media_path, DEFAULT_PROMPT)

        if caption is not None and entry.discovery is not None:
            entry.discovery.caption = caption

        if on_progress is not None:
            on_progress(i + 1)
