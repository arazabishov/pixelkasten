"""
Ollama integration — chat with local LLMs and VLMs via Ollama.

Prerequisites:
    - Ollama installed and running (`ollama serve`)
    - Required models pulled (`ollama pull gemma4:e4b`, `ollama pull gemma4:31b`)
"""

from collections.abc import Sequence


def check_ollama(model: str) -> None:
    """
    Verify that Ollama is reachable and the requested model is available.

    Raises RuntimeError with a clear message if not found.
    """
    import ollama

    try:
        available = ollama.list()
    except Exception:
        raise RuntimeError("Ollama is not running. Start it with: ollama serve")

    model_names = [m.model for m in available.models]

    # Ollama model names may include a `:latest` tag. Match against both
    # the full name and the base name (without tag).
    base_names = [n.split(":")[0] for n in model_names if n is not None]

    if model not in model_names and model not in base_names:
        available_str = ", ".join(n for n in model_names if n is not None) or "(none)"
        raise RuntimeError(
            f"Model '{model}' not found. Run: ollama pull {model}\n"
            f"Available models: {available_str}"
        )


def chat(model: str, prompt: str, images: Sequence[str | bytes] | None = None) -> str | None:
    """
    Send a chat message to Ollama and return the response text.

    Args:
        model: Ollama model name (e.g. "gemma4:e4b", "gemma4:31b").
        prompt: The text prompt to send.
        images: Optional list of image paths or raw bytes for vision models.

    Returns the stripped response text, or None if the response is empty.
    """
    import ollama

    message: dict = {"role": "user", "content": prompt}
    if images:
        message["images"] = images

    response = ollama.chat(model=model, messages=[message])

    content = response.message.content
    return content.strip() if content else None
