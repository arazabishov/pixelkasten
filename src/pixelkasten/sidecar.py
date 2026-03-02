"""
Google Photos JSON sidecar file parsing.

Ported from packages/core/src/core/sidecar.js. Reads .json sidecar files
that Google Photos Takeout produces alongside media files, extracting
timestamps and geo data.
"""

import json
from pathlib import Path


def read_sidecar(json_path: str | Path | None) -> dict | None:
    """
    Read a Google Photos JSON sidecar file.

    Returns a dict with:
        - timestamp: str | None  (Unix epoch string from photoTakenTime)
        - geo: dict | None       ({latitude, longitude, altitude})

    Returns None if json_path is falsy.
    Raises RuntimeError wrapping the original error on file/parse failures.
    """
    if not json_path:
        return None

    try:
        with open(json_path) as f:
            data = json.load(f)

        photo_taken_time = data.get("photoTakenTime")
        geo_data_exif = data.get("geoDataExif")
        geo_data = data.get("geoData")

        geo = get_geo_data(geo_data_exif, geo_data)

        return {
            "timestamp": photo_taken_time.get("timestamp")
            if photo_taken_time
            else None,
            "geo": geo,
        }
    except Exception as e:
        raise RuntimeError(f"Failed to read sidecar file at {json_path}: {e}") from e


def has_geo_data(geo: dict | None) -> bool:
    """
    Validate geo data from a sidecar. Rejects (0, 0) as Google's placeholder.

    Unlike _validate_gps in exif.py (which only rejects when BOTH are zero),
    this rejects if EITHER latitude or longitude is 0. This is correct for
    sidecar data because Google uses 0 as default for missing coordinates.
    """
    if not geo:
        return False
    return geo.get("latitude", 0) != 0 and geo.get("longitude", 0) != 0


def get_geo_data(
    geo_data_exif: dict | None,
    geo_data: dict | None,
) -> dict | None:
    """
    Extract geo data, preferring geoDataExif over geoData.

    Strips latitudeSpan/longitudeSpan fields (GPS accuracy, not portable
    to EXIF metadata).
    """
    if has_geo_data(geo_data_exif):
        return {
            "latitude": geo_data_exif["latitude"],
            "longitude": geo_data_exif["longitude"],
            "altitude": geo_data_exif.get("altitude"),
        }

    if has_geo_data(geo_data):
        return {
            "latitude": geo_data["latitude"],
            "longitude": geo_data["longitude"],
            "altitude": geo_data.get("altitude"),
        }

    return None
