"""
Image discovery — find all supported media files in a directory.

This module walks a source directory and collects files whose extensions
match the formats we can process. It mirrors the supported formats from
the Node.js pipeline (packages/core/src/handlers/index.js) so both tools
agree on what counts as a "photo" or "video."
"""

from pathlib import Path

# Extensions we can generate CLIP embeddings for.
# Images are processed directly. Videos require frame extraction (not yet
# implemented — for now we collect them but skip during embedding).
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".heic", ".png"}
VIDEO_EXTENSIONS = {".mp4", ".mov"}
ALL_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS


def scan(source: Path) -> list[Path]:
    """
    Recursively find all supported media files under `source`.

    Returns a sorted list of absolute Path objects. Sorting ensures
    deterministic ordering — running the pipeline twice on the same
    directory produces the same manifest.

    Raises FileNotFoundError if the source directory does not exist.
    """
    if not source.is_dir():
        raise FileNotFoundError(f"Source directory not found: {source}")

    files = []
    for path in source.rglob("*"):
        if path.is_file() and path.suffix.lower() in ALL_EXTENSIONS:
            files.append(path.resolve())

    return sorted(files)


def is_image(path: Path) -> bool:
    """Check if a path is a supported image (not video) file."""
    return path.suffix.lower() in IMAGE_EXTENSIONS


def is_video(path: Path) -> bool:
    """Check if a path is a supported video file."""
    return path.suffix.lower() in VIDEO_EXTENSIONS
