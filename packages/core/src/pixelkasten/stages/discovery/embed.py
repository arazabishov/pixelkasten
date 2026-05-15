"""
CLIP embedding generation — the core of the AI pipeline.

# What are embeddings?

An embedding is a fixed-size array of numbers (a "vector") that represents
the semantic meaning of an image or text. Think of it as a fingerprint for
content: two beach photos will produce similar vectors, while a beach photo
and a document scan will produce very different vectors.

# What is CLIP?

CLIP (Contrastive Language-Image Pretraining) is a model published by OpenAI
in 2021. It was trained on ~400 million image-text pairs from the internet,
learning to map BOTH images and text into the same vector space.

This means you can directly compare an image vector against a text vector:
- Embed the text "birthday party" → get a 768-dimensional vector
- Embed a photo of a birthday → get a 768-dimensional vector
- Compute cosine similarity between them → high score (they're related)

# How this module works

embed_images() loads a CLIP model (ViT-L/14 by default), preprocesses each
image (resize, normalize pixel values to what CLIP expects), and runs them
through the model to produce one 768-dimensional vector per image. The model
runs on GPU if available (MPS on Apple Silicon, CUDA on NVIDIA).

All vectors are L2-normalized (unit length), which means cosine similarity
between any two vectors is simply their dot product.
"""

from typing import Any

import numpy as np

from pixelkasten.configuration import DiscoveryOptions


def detect_device() -> str:
    """
    Pick the best available compute device for inference.

    - "mps"  — Apple Silicon GPU (Metal Performance Shaders). Available on
               M1/M2/M3/M4 Macs. Uses the GPU cores (not the Neural Engine).
    - "cuda" — NVIDIA GPU. Available on Linux/Windows with NVIDIA hardware.
    - "cpu"  — Fallback. Works everywhere but is ~10-20x slower.
    """
    import torch

    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def _load_model(
    model_name: str = "ViT-L-14",
    pretrained: str = "openai",
    device: str | None = None,
) -> tuple[Any, Any, str]:
    """
    Load a CLIP model and its image preprocessing transform.

    Returns (model, preprocess, device_str). `device` is auto-detected
    when None. `pretrained` selects the weights ("openai" or alternatives
    like "laion2b_s32b_b82k").
    """
    import os

    if device is None:
        device = detect_device()

    # Set offline mode before importing open_clip so huggingface_hub
    # sees it at import time. Falls back to online if not cached yet.
    os.environ["HF_HUB_OFFLINE"] = "1"
    import open_clip

    try:
        model, _, preprocess = open_clip.create_model_and_transforms(
            model_name, pretrained=pretrained, device=device, force_quick_gelu=True
        )
    except Exception:
        del os.environ["HF_HUB_OFFLINE"]
        model, _, preprocess = open_clip.create_model_and_transforms(
            model_name, pretrained=pretrained, device=device, force_quick_gelu=True
        )

    # Set the model to evaluation mode. This disables training-specific
    # behaviors like dropout (randomly zeroing neurons). During inference,
    # we want deterministic, full-precision results.
    model.eval()

    return model, preprocess, device


def embed_images(
    image_paths: list[str],
    options: DiscoveryOptions,
    on_progress=None,
) -> tuple[np.ndarray, list[int]]:
    """
    Generate CLIP embeddings for a list of images.

    Loads the model, then processes images in batches. Each image is:
    1. Loaded from disk as a PIL Image
    2. Preprocessed (resized to 224x224, pixel values normalized)
    3. Fed through the CLIP vision encoder
    4. L2-normalized to unit length

    Reads `clip_model` and `batch_size` from options. Returns
    (embeddings, failed_indices). Failed indices are positions in
    `image_paths` that couldn't be loaded (corrupt files, unsupported
    formats); they're skipped, not errored.
    """
    import torch
    from PIL import Image

    model, preprocess, device = _load_model(options.clip_model)
    batch_size = options.batch_size

    all_embeddings = []
    failed_indices = []
    processed = 0

    # torch.no_grad() tells PyTorch we're not training — don't track gradients.
    # This saves memory and speeds up computation.
    with torch.no_grad():
        for batch_start in range(0, len(image_paths), batch_size):
            batch_paths = image_paths[batch_start : batch_start + batch_size]
            batch_tensors = []
            batch_failed = []

            for i, path in enumerate(batch_paths):
                try:
                    # Open the image and apply CLIP's preprocessing:
                    # - Resize to 224x224 pixels
                    # - Convert to RGB (handles grayscale, RGBA, etc.)
                    # - Normalize pixel values to the range CLIP was trained on
                    image = Image.open(path).convert("RGB")
                    tensor = preprocess(image)
                    batch_tensors.append(tensor)
                except Exception:
                    # Corrupt file, unsupported format, permission error, etc.
                    # Record the failure and continue — don't crash the whole
                    # pipeline for one bad file.
                    batch_failed.append(batch_start + i)

            failed_indices.extend(batch_failed)

            if len(batch_tensors) == 0:
                processed += len(batch_paths)
                if on_progress:
                    on_progress(processed)
                continue

            # Stack individual image tensors into a single batch tensor.
            # Shape: (batch_size, 3, 224, 224) — batch of RGB images.
            batch = torch.stack(batch_tensors).to(device)

            # Run the batch through CLIP's vision encoder.
            # Output shape: (batch_size, 768) — one embedding per image.
            embeddings = model.encode_image(batch)

            # L2-normalize each embedding to unit length. After this,
            # cosine similarity between any two embeddings is simply their
            # dot product: similarity = a · b (no need to divide by norms).
            embeddings = embeddings / embeddings.norm(dim=-1, keepdim=True)

            # Move from GPU to CPU and convert to numpy for storage.
            all_embeddings.append(embeddings.cpu().numpy())

            processed += len(batch_paths)
            if on_progress:
                on_progress(processed)

    if len(all_embeddings) == 0:
        return np.array([]).reshape(0, 0), failed_indices

    # Vertically stack all batch results into one big (N, 768) array.
    return np.vstack(all_embeddings), failed_indices
