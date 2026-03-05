"""
Metadata handlers — format-specific logic for reading and writing metadata.

Each handler knows which exiftool tags to read, how to parse the raw output,
and how to format write commands for timestamps and GPS data. The registry
maps file extensions to handlers.
"""

from pathlib import Path

from pixelkasten.handlers.exif import ExifHandler
from pixelkasten.handlers.quicktime import QuickTimeHandler


IMAGE_EXTENSIONS: frozenset[str] = frozenset({".jpg", ".jpeg", ".heic", ".png"})
VIDEO_EXTENSIONS: frozenset[str] = frozenset({".mp4", ".mov"})
UNSUPPORTED_MEDIA_EXTENSIONS: frozenset[str] = frozenset(
    {".avi", ".mkv", ".wmv", ".flv"}
)

exif_handler = ExifHandler()
quicktime_handler = QuickTimeHandler()

handlers: dict[str, ExifHandler | QuickTimeHandler] = {
    ".jpg": exif_handler,
    ".jpeg": exif_handler,
    ".heic": exif_handler,
    ".png": exif_handler,
    ".mp4": quicktime_handler,
    ".mov": quicktime_handler,
    ".mp": exif_handler,  # Google media format
}

SUPPORTED_EXTENSIONS: frozenset[str] = frozenset(handlers.keys())
ALL_KNOWN_MEDIA_EXTENSIONS: frozenset[str] = (
    SUPPORTED_EXTENSIONS | UNSUPPORTED_MEDIA_EXTENSIONS
)


def is_image(path: Path) -> bool:
    """Check if a path is a supported image (not video) file."""
    return path.suffix.lower() in IMAGE_EXTENSIONS


def is_video(path: Path) -> bool:
    """Check if a path is a supported video file."""
    return path.suffix.lower() in VIDEO_EXTENSIONS
