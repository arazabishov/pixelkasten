"""
Image discovery — find all supported media files in a directory.

This module walks a source directory and collects files whose extensions
match the formats we can process. Images are embedded directly by CLIP.
Videos are collected but skipped during embedding (frame extraction is
not yet implemented).

Also provides scan_takeout() for the Google Takeout pipeline, which
categorizes ALL files (not just media) into four buckets.
"""

import os
from pathlib import Path

from pixelkasten.core.handlers import all_known_media_extensions

# Extensions we can generate CLIP embeddings for.
# Images are processed directly. Videos require frame extraction (not yet
# implemented — for now we collect them but skip during embedding).
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".heic", ".png"}
VIDEO_EXTENSIONS = {".mp4", ".mov"}
ALL_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS


def scan(source: Path) -> list[Path]:
    """
    Find all supported media files under `source`, including subdirectories.

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


def scan_takeout(source_path: str) -> dict:
    """
    Categorize all files under source_path into four buckets for takeout processing.

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

    # Invariant: every file must land in exactly one bucket.
    assert files_total == (
        len(files_media)
        + len(files_metadata)
        + len(files_metadata_albums)
        + len(files_other_ignored)
    ), "Bucket counts do not sum to total file count"

    return {
        "files_media": files_media,
        "files_metadata": files_metadata,
        "files_metadata_albums": files_metadata_albums,
        "files_other_ignored": files_other_ignored,
        "files_total": files_total,
    }
