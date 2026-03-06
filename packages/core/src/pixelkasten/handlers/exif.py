"""Metadata handler for EXIF-based formats (JPEG, HEIC, PNG)."""

from pixelkasten.core.datetime import normalize_disk_date
from pixelkasten.handlers.shared import (
    COMPOSITE_GEO_TAGS,
    parse_composite_geo,
)


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

    def parse(self, raw: dict) -> dict:
        dates = [
            d for d in (normalize_disk_date(raw.get(k)) for k in self._DATE_KEYS) if d is not None
        ]

        return {
            "timestamp": normalize_disk_date(raw.get("EXIF:DateTimeOriginal")),
            "dates": dates,
            "geo": parse_composite_geo(raw),
        }

    def timestamp(self, data: str) -> list[str]:
        return [f"SubSecDateTimeOriginal={data}"]

    def geo(self, data: dict) -> list[str]:
        return [
            f"Composite:GPSLatitude={data['latitude']}",
            f"Composite:GPSLongitude={data['longitude']}",
            f"GPSAltitude={data['altitude']}",
            f"GPSAltitudeRef={data['altitude']}",
        ]
