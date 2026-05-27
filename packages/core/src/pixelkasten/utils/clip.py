"""
CLIP image and video embeddings for enrich, similar, and cluster.

Loads a CLIP model once via open_clip and exposes a helper that embeds a
list of PIL images. Heavy dependencies (torch, open_clip) are imported
lazily inside functions so users running only `init` don't pay for them.
"""

from __future__ import annotations

import io
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    from PIL.Image import Image as PILImage


_MODEL: Any = None
_PREPROCESS: Any = None
_DEVICE: str | None = None
_MODEL_NAME: str | None = None


def _detect_device() -> str:
    import torch

    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def _ensure_model(model_name: str = "ViT-L-14") -> tuple[Any, Any, str]:
    """Lazy-load (and cache) the CLIP model + preprocess transform."""
    global _MODEL, _PREPROCESS, _DEVICE, _MODEL_NAME

    if _MODEL is not None and _MODEL_NAME == model_name:
        return _MODEL, _PREPROCESS, _DEVICE  # type: ignore[return-value]

    import os

    os.environ["HF_HUB_OFFLINE"] = "1"
    import open_clip

    device = _detect_device()
    try:
        model, _, preprocess = open_clip.create_model_and_transforms(
            model_name, pretrained="openai", device=device, force_quick_gelu=True
        )
    except Exception:
        del os.environ["HF_HUB_OFFLINE"]
        model, _, preprocess = open_clip.create_model_and_transforms(
            model_name, pretrained="openai", device=device, force_quick_gelu=True
        )
    model.eval()

    _MODEL, _PREPROCESS, _DEVICE, _MODEL_NAME = model, preprocess, device, model_name
    return model, preprocess, device


def embed_images(images: Sequence[PILImage], model_name: str = "ViT-L-14") -> np.ndarray:
    """
    Embed a batch of PIL images. Returns a (N, 768) float32 L2-normalized array.

    Empty input returns an empty array of shape (0, 0).
    """
    if not images:
        return np.array([]).reshape(0, 0)

    import torch

    model, preprocess, device = _ensure_model(model_name)

    tensors = [preprocess(img.convert("RGB")) for img in images]
    batch = torch.stack(tensors).to(device)

    with torch.no_grad():
        embeddings = model.encode_image(batch)
        embeddings = embeddings / embeddings.norm(dim=-1, keepdim=True)

    return embeddings.cpu().numpy().astype(np.float32)


def embed_video(path: str, video_frames: int) -> np.ndarray:
    """Represent a video as the L2-normalized mean of sampled-frame embeddings."""
    from PIL import Image

    from pixelkasten.utils.ffmpeg import capture_frames
    from pixelkasten.utils.pil import ensure_pil_plugins

    ensure_pil_plugins()

    frames = capture_frames(path, video_frames)
    images = [Image.open(io.BytesIO(frame)) for frame in frames]
    matrix = embed_images(images)
    if matrix.size == 0:
        raise RuntimeError(f"Empty embedding for {path}")

    mean = matrix.mean(axis=0)
    return mean / np.linalg.norm(mean)
