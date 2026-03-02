"""
File discovery — find and categorize all files in a source directory.

Walks a source directory and classifies every file by extension into
buckets: media, metadata (JSON sidecars), album metadata, or other.
This unified scan is used by both takeout and archive modes.
"""

import os
from pathlib import Path

from pixelkasten.core.handlers import all_known_media_extensions

# Extensions we can generate CLIP embeddings for.
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".heic", ".png"}
VIDEO_EXTENSIONS = {".mp4", ".mov"}


def scan(source_path: str) -> dict:
    """
    Categorize all files under source_path into four buckets.

    Walks the directory tree using os.walk() and classifies every file by
    extension into one of: media, metadata (JSON sidecars), album metadata
    (metadata.json), or other/ignored.

    Returns dict with:
        files_media: list[str]           - Known media extensions
        files_metadata: list[str]        - .json sidecar files (excluding metadata.json)
        files_metadata_albums: list[str] - metadata.json album files
        files_other_ignored: list[str]   - Everything else
        files_total: int                 - Total file count

    Raises FileNotFoundError if source_path doesn't exist or isn't a directory.
    """
    if not os.path.isdir(source_path):
        raise FileNotFoundError(f"Source directory not found: {source_path}")

    files_media: list[str] = []
    files_metadata: list[str] = []
    files_metadata_albums: list[str] = []
    files_other_ignored: list[str] = []

    for dirpath, _dirnames, filenames in os.walk(source_path):
        for filename in filenames:
            full_path = os.path.join(dirpath, filename)
            ext = os.path.splitext(filename)[1].lower()

            if filename == "metadata.json":
                files_metadata_albums.append(full_path)
            elif ext == ".json":
                files_metadata.append(full_path)
            elif ext in all_known_media_extensions:
                files_media.append(full_path)
            else:
                files_other_ignored.append(full_path)

    files_total = (
        len(files_media)
        + len(files_metadata)
        + len(files_metadata_albums)
        + len(files_other_ignored)
    )

    return {
        "files_media": files_media,
        "files_metadata": files_metadata,
        "files_metadata_albums": files_metadata_albums,
        "files_other_ignored": files_other_ignored,
        "files_total": files_total,
    }


def is_image(path: Path) -> bool:
    """Check if a path is a supported image (not video) file."""
    return path.suffix.lower() in IMAGE_EXTENSIONS


def is_video(path: Path) -> bool:
    """Check if a path is a supported video file."""
    return path.suffix.lower() in VIDEO_EXTENSIONS
