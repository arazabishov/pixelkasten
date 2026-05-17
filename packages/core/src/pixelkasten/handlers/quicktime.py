"""Metadata handler for QuickTime-based formats (MP4, MOV)."""

from pixelkasten.utils.dates import normalize_disk_date
from pixelkasten.handlers.shared import (
    COMPOSITE_GEO_TAGS,
    parse_composite_geo,
)


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

    def parse(self, raw: dict) -> dict:
        dates = [
            d for d in (normalize_disk_date(raw.get(k)) for k in self._DATE_KEYS) if d is not None
        ]

        return {
            "timestamp": normalize_disk_date(raw.get("QuickTime:CreationDate")),
            "dates": dates,
            "geo": parse_composite_geo(raw),
        }

    def timestamp(self, data: str) -> list[str]:
        return [f"CreationDate={data}"]

    def geo(self, data: dict) -> list[str]:
        return [f"Keys:GPSCoordinates={data['latitude']}, {data['longitude']}, {data['altitude']}"]
