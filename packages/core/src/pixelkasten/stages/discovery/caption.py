"""
VLM captioning via Ollama — Phase 3 of the AI pipeline.

Sends cluster representative images to a local vision-language model
(LLaVA, Moondream, etc.) running on Ollama to generate free-form captions.
This produces human-readable descriptions like "family dinner with birthday
cake" instead of just zero-shot tag scores.

Run after enrich and refine so that captions reflect the refined clusters.

Prerequisites:
    - Ollama installed and running (`ollama serve`)
    - A vision model pulled (`ollama pull llava`)
"""

from typing import Callable

import ollama as ollama_client


DEFAULT_PROMPT = (
    "Describe this photograph in 1-2 sentences. "
    "Focus on the main subject, setting, and any notable activity or event."
)


def check_ollama(model: str) -> None:
    """
    Verify that Ollama is reachable and the requested model is available.

    Raises RuntimeError with a clear message if something is wrong.
    """
    try:
        available = ollama_client.list()
    except Exception:
        raise RuntimeError("Ollama is not running. Start it with: ollama serve")

    model_names = [m.model for m in available.models]

    # Ollama model names may include a `:latest` tag. Match against both
    # the full name and the base name (without tag).
    base_names = [n.split(":")[0] for n in model_names if n is not None]

    if model not in model_names and model not in base_names:
        available = ", ".join(n for n in model_names if n is not None) or "(none)"
        raise RuntimeError(
            f"Model '{model}' not found. Run: ollama pull {model}\nAvailable models: {available}"
        )


def caption_image(model: str, image_path: str, prompt: str) -> str | None:
    """
    Send a single image to Ollama and return the caption text.

    Returns None if captioning fails (network error, model error, etc.)
    so the pipeline can continue with partial results.
    """
    try:
        response = ollama_client.chat(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                    "images": [image_path],
                },
            ],
        )
        content = response.message.content
        return content.strip() if content else None
    except Exception:
        return None


def caption_representatives(
    manifest: dict,
    model: str,
    prompt: str = DEFAULT_PROMPT,
    on_progress: Callable[[int], None] | None = None,
) -> dict[str, str]:
    """
    Caption all representative images in a Phase 1 manifest.

    Iterates over entries where is_representative is True, sends each
    to the VLM, and returns a dict mapping image path to caption text.

    Args:
        manifest: Parsed manifest dict (from read_manifest).
        model: Ollama vision model name (e.g. "llava").
        prompt: The prompt to send alongside each image.
        on_progress: Optional callback, called with the count of
            images processed so far.

    Returns:
        Dict of {image_path: caption} for successfully captioned images.
    """
    from pixelkasten.manifest import Status

    representatives = [
        entry
        for entry in manifest["entries"]
        if entry.discovery
        and entry.discovery.is_representative
        and entry.discovery.status == Status.PROCESSED
    ]

    captions = {}
    for i, entry in enumerate(representatives):
        caption = caption_image(model, entry.media_path, prompt)

        if caption is not None:
            captions[entry.media_path] = caption

        if on_progress is not None:
            on_progress(i + 1)

    return captions
