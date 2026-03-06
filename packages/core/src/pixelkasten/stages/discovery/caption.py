"""
VLM captioning via Ollama.

Sends cluster representative images to a local vision-language model
(LLaVA, Moondream, etc.) running on Ollama to generate free-form captions.

Prerequisites:
    - Ollama installed and running (`ollama serve`)
    - A vision model pulled (`ollama pull llava`)
"""

from typing import Callable

from pixelkasten.manifest import ManifestEntry, Status


DEFAULT_PROMPT = (
    "Describe this photograph in 1-2 sentences. "
    "Focus on the main subject, setting, and any notable activity or event."
)


def check_ollama(model: str) -> None:
    """
    Verify that Ollama is reachable and the requested model is available.

    Raises RuntimeError with a clear message if something is wrong.
    """
    import ollama as ollama_client

    try:
        available = ollama_client.list()
    except Exception:
        raise RuntimeError("Ollama is not running. Start it with: ollama serve")

    model_names = [m.model for m in available.models]

    base_names = [n.split(":")[0] for n in model_names if n is not None]

    if model not in model_names and model not in base_names:
        available_str = ", ".join(n for n in model_names if n is not None) or "(none)"
        raise RuntimeError(
            f"Model '{model}' not found. Run: ollama pull {model}\nAvailable models: {available_str}"
        )


def caption_image(model: str, image_path: str, prompt: str) -> str | None:
    """
    Send a single image to Ollama and return the caption text.

    Returns None if captioning fails so the pipeline can continue.
    """
    import ollama as ollama_client

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
    entries: list[ManifestEntry],
    model: str,
    prompt: str = DEFAULT_PROMPT,
    on_progress: Callable[[int], None] | None = None,
) -> dict[str, str]:
    """
    Caption all representative images.

    Returns a dict mapping image path to caption text for successfully
    captioned images.
    """
    representatives = [
        entry
        for entry in entries
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
