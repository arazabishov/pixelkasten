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
            "timestamp": photo_taken_time.get("timestamp") if photo_taken_time else None,
            "geo": geo,
        }
    except Exception as e:
        raise RuntimeError(f"Failed to read sidecar file at {json_path}: {e}") from e


def get_geo_data(
    geo_data_exif: dict | None,
    geo_data: dict | None,
) -> dict | None:
    """
    Extract geo data, preferring geoDataExif over geoData.

    Rejects if EITHER latitude or longitude is 0, since Google uses 0
    as default for missing coordinates. Strips latitudeSpan/longitudeSpan
    fields (GPS accuracy, not portable to EXIF metadata).
    """
    return _extract_geo(geo_data_exif) or _extract_geo(geo_data)


def _extract_geo(geo: dict | None) -> dict | None:
    """
    Extract and validate geo data from a single sidecar geo dict.

    Returns None if the dict is missing or contains zero coordinates.
    """
    if not geo:
        return None

    lat = geo.get("latitude", 0)
    lon = geo.get("longitude", 0)

    if lat == 0 or lon == 0:
        return None

    return {
        "latitude": lat,
        "longitude": lon,
        "altitude": geo.get("altitude"),
    }
