"""Shared types for metadata handlers."""

from dataclasses import dataclass, field
from typing import Protocol


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
