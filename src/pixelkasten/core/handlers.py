"""
Metadata handlers for EXIF (images) and QuickTime (videos).

Ported from packages/core/src/handlers/. Each handler knows which exiftool
tags to read, how to parse the raw output, and how to format write commands
for timestamps and GPS data.

Also provides the handler registry mapping file extensions to handlers,
and extension sets used by the scan stage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from pixelkasten.core.datetime import normalize_disk_date


@dataclass
class ParsedMetadata:
    """Normalized metadata extracted from a media file."""

    timestamp: str | None = None
    dates: list[str] = field(default_factory=list)
    geo: dict | None = None


class Handler(Protocol):
    """Protocol for format-specific metadata handlers."""

    read_tags: list[str]

    def parse(self, raw: dict) -> ParsedMetadata: ...

    def timestamp(self, data: str) -> list[str]: ...

    def geo(self, data: dict) -> list[str]: ...


# ---------------------------------------------------------------------------
# Composite GPS tags (shared by EXIF and QuickTime handlers)
# ---------------------------------------------------------------------------

COMPOSITE_GEO_TAGS = [
    "Composite:GPSAltitude",
    "Composite:GPSLatitude",
    "Composite:GPSLongitude",
]


def parse_composite_geo(raw: dict) -> dict | None:
    """
    Extract GPS data from ExifTool's Composite tags.

    Returns None if either latitude or longitude is missing (undefined).
    Note: 0 IS a valid coordinate here (unlike sidecar's has_geo_data).
    """
    lat = raw.get("Composite:GPSLatitude")
    lon = raw.get("Composite:GPSLongitude")

    if lat is None or lon is None:
        return None

    return {
        "latitude": lat,
        "longitude": lon,
        "altitude": raw.get("Composite:GPSAltitude"),
    }


# ---------------------------------------------------------------------------
# EXIF handler (JPEG, HEIC, PNG)
# ---------------------------------------------------------------------------


class ExifHandler:
    """Metadata handler for EXIF-based formats (JPEG, HEIC, PNG)."""

    read_tags: list[str] = [
        *COMPOSITE_GEO_TAGS,
        "Composite:GPSDateTime",
        "EXIF:DateTimeOriginal",
        "EXIF:CreateDate",
        "EXIF:ModifyDate",
        "File:FileCreateDate",
        "File:FileModifyDate",
    ]

    _DATE_KEYS = [
        "EXIF:DateTimeOriginal",
        "EXIF:CreateDate",
        "Composite:GPSDateTime",
        "EXIF:ModifyDate",
        "File:FileCreateDate",
        "File:FileModifyDate",
    ]

    def parse(self, raw: dict) -> ParsedMetadata:
        dates = [
            d
            for d in (normalize_disk_date(raw.get(k)) for k in self._DATE_KEYS)
            if d is not None
        ]

        return ParsedMetadata(
            timestamp=normalize_disk_date(raw.get("EXIF:DateTimeOriginal")),
            dates=dates,
            geo=parse_composite_geo(raw),
        )

    def timestamp(self, data: str) -> list[str]:
        return [f"SubSecDateTimeOriginal={data}"]

    def geo(self, data: dict) -> list[str]:
        return [
            f"Composite:GPSLatitude={data['latitude']}",
            f"Composite:GPSLongitude={data['longitude']}",
            f"GPSAltitude={data['altitude']}",
            f"GPSAltitudeRef={data['altitude']}",
        ]


# ---------------------------------------------------------------------------
# QuickTime handler (MP4, MOV)
# ---------------------------------------------------------------------------


class QuickTimeHandler:
    """Metadata handler for QuickTime-based formats (MP4, MOV)."""

    read_tags: list[str] = [
        *COMPOSITE_GEO_TAGS,
        "QuickTime:CreationDate",
        "QuickTime:CreateDate",
        "QuickTime:GPSDateTime",
        "QuickTime:ModifyDate",
        "File:FileCreateDate",
        "File:FileModifyDate",
    ]

    _DATE_KEYS = [
        "QuickTime:CreationDate",
        "QuickTime:CreateDate",
        "QuickTime:GPSDateTime",
        "QuickTime:ModifyDate",
        "File:FileCreateDate",
        "File:FileModifyDate",
    ]

    def parse(self, raw: dict) -> ParsedMetadata:
        dates = [
            d
            for d in (normalize_disk_date(raw.get(k)) for k in self._DATE_KEYS)
            if d is not None
        ]

        return ParsedMetadata(
            timestamp=normalize_disk_date(raw.get("QuickTime:CreationDate")),
            dates=dates,
            geo=parse_composite_geo(raw),
        )

    def timestamp(self, data: str) -> list[str]:
        return [f"CreationDate={data}"]

    def geo(self, data: dict) -> list[str]:
        return [
            f"Keys:GPSCoordinates={data['latitude']}, {data['longitude']}, {data['altitude']}"
        ]


# ---------------------------------------------------------------------------
# Extension sets — single source of truth for format classification.
# ---------------------------------------------------------------------------

IMAGE_EXTENSIONS: frozenset[str] = frozenset({".jpg", ".jpeg", ".heic", ".png"})
VIDEO_EXTENSIONS: frozenset[str] = frozenset({".mp4", ".mov"})
UNSUPPORTED_MEDIA_EXTENSIONS: frozenset[str] = frozenset(
    {".avi", ".mkv", ".wmv", ".flv"}
)

# ---------------------------------------------------------------------------
# Handler registry — derived from extension sets.
# ---------------------------------------------------------------------------

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
