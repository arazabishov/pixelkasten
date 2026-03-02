"""
ExifTool integration — read, parse, and write metadata via exiftool subprocess.

Provides:
- Subprocess wrapper: check_exiftool, read_metadata, write_metadata
- Parsed EXIF reading: read_exif, read_exif_for_representatives
- Tag parsing: timestamp normalization, GPS validation, camera extraction

Prerequisites:
    - exiftool installed and on PATH (`brew install exiftool`)
"""

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, TypedDict

from pixelkasten.core.datetime import normalize_disk_date


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


class GpsData(TypedDict, total=False):
    latitude: float
    longitude: float
    altitude: float | None


class ExifData(TypedDict, total=False):
    timestamp: str | None
    gps: GpsData | None
    camera: str | None


# ---------------------------------------------------------------------------
# Subprocess wrapper
# ---------------------------------------------------------------------------


def check_exiftool() -> None:
    """
    Verify that exiftool is installed and available on PATH.

    Raises RuntimeError with a clear installation message if not found.
    """
    try:
        result = subprocess.run(
            ["exiftool", "-ver"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            raise RuntimeError(
                "exiftool is installed but returned an error. Check your installation."
            )
    except FileNotFoundError:
        raise RuntimeError(
            "exiftool is not installed. Install it with: brew install exiftool"
        )


def read_metadata(
    file_paths: list[Path],
    tags: list[str] | None = None,
) -> dict[str, dict]:
    """
    Read metadata from files using exiftool.

    Args:
        file_paths: Paths to the files to read.
        tags: Metadata tags to extract (e.g., ["EXIF:DateTimeOriginal"]).
              If None or empty, reads default tags.

    Returns:
        Dict mapping SourceFile path to raw exiftool metadata dict.
    """
    if not file_paths:
        return {}

    args = [
        "exiftool",
        "-api",
        "largefilesupport=1",
        "-json",
        "-n",
        "-G",
        "-fast",
    ]

    if tags:
        for tag in tags:
            args.append(f"-{tag}")

    args.extend(["-@", "-"])

    stdin_text = "\n".join(str(p) for p in file_paths)

    result = subprocess.run(
        args,
        input=stdin_text,
        capture_output=True,
        text=True,
        timeout=300,
    )

    # exiftool returns 1 for minor warnings (missing tags), not errors.
    if result.returncode not in (0, 1):
        raise RuntimeError(f"Failed to read metadata using exiftool: {result.stderr}")

    if not result.stdout.strip():
        return {}

    entries = json.loads(result.stdout)
    # Normalize SourceFile paths: exiftool uses forward slashes on Windows,
    # but callers use os.path (backslashes). os.path.normpath ensures consistency.
    return {os.path.normpath(entry.get("SourceFile", "")): entry for entry in entries}


def write_metadata(file_path: str | Path, tags: list[str]) -> None:
    """
    Write metadata tags to a file using exiftool.

    Args:
        file_path: Path to the file to write metadata to.
        tags: Tags to write (e.g., ["SubSecDateTimeOriginal=2023:05:20 14:30:00+00:00"]).
              If empty, returns immediately without calling exiftool.
    """
    if not tags:
        return

    args = [
        "exiftool",
        "-api",
        "largefilesupport=1",
        "-overwrite_original",
    ]

    for tag in tags:
        args.append(f"-{tag}")

    args.append(str(file_path))

    result = subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=60,
    )

    if result.returncode != 0:
        raise RuntimeError(f"Failed to write metadata using exiftool: {result.stderr}")


# ---------------------------------------------------------------------------
# Parsed EXIF reading
# ---------------------------------------------------------------------------

_EXIF_TAGS = [
    "EXIF:DateTimeOriginal",
    "EXIF:CreateDate",
    "QuickTime:CreationDate",
    "QuickTime:CreateDate",
    "Composite:GPSLatitude",
    "Composite:GPSLongitude",
    "Composite:GPSAltitude",
    "EXIF:Model",
    "EXIF:Make",
]


def read_exif(file_paths: list[Path]) -> dict[str, ExifData]:
    """
    Read EXIF metadata from multiple files in a single exiftool invocation.

    Uses exiftool's -json mode with stdin file list for efficiency (one
    process for all files, not one per file).

    Args:
        file_paths: List of image file paths to read.

    Returns:
        Dict mapping file path (string) to parsed ExifData. Files that
        fail to read or have no relevant metadata get an ExifData with
        all None values.
    """
    if not file_paths:
        return {}

    raw_results = read_metadata(file_paths, _EXIF_TAGS)

    parsed = {}
    for source_file, raw in raw_results.items():
        parsed[source_file] = _parse_exiftool_entry(raw)

    # Fill in any files that didn't appear in the output.
    for p in file_paths:
        key = str(p)
        if key not in parsed:
            parsed[key] = _empty_exif()

    return parsed


def read_exif_for_representatives(
    manifest: dict,
    on_progress: Callable[[int], None] | None = None,
) -> dict[str, ExifData]:
    """
    Read EXIF from representative images in a manifest.

    Filters to entries where is_representative=True and status="ok",
    then batch-reads EXIF for all of them in a single exiftool call.

    Args:
        manifest: Parsed manifest dict (from read_manifest).
        on_progress: Optional callback, called with count processed.

    Returns:
        Dict of {image_path: ExifData} for all representatives.
    """
    representatives = [
        entry
        for entry in manifest["entries"]
        if entry.get("is_representative", False) and entry.get("status") == "ok"
    ]

    file_paths = [Path(entry["path"]) for entry in representatives]

    if on_progress is not None:
        on_progress(0)

    result = read_exif(file_paths)

    if on_progress is not None:
        on_progress(len(file_paths))

    return result


# ---------------------------------------------------------------------------
# Tag parsing helpers
# ---------------------------------------------------------------------------


def _empty_exif() -> ExifData:
    """Return an ExifData with all None values."""
    return ExifData(timestamp=None, gps=None, camera=None)


def _parse_exiftool_entry(raw: dict) -> ExifData:
    """
    Parse a single exiftool JSON entry into our normalized ExifData shape.

    Handles the tag priority chain:
    - Timestamp: DateTimeOriginal > CreateDate (EXIF) > CreationDate (QT)
    - GPS: Composite GPSLatitude + GPSLongitude (skip 0,0)
    - Camera: Model (fallback: Make)
    """
    # Timestamp: try tags in priority order.
    timestamp = None
    for tag in [
        "EXIF:DateTimeOriginal",
        "EXIF:CreateDate",
        "QuickTime:CreationDate",
        "QuickTime:CreateDate",
    ]:
        if tag in raw:
            timestamp = _normalize_timestamp(raw[tag])
            if timestamp is not None:
                break

    # GPS: use Composite tags (cross-format, already decimal with -n).
    gps = None
    lat = raw.get("Composite:GPSLatitude")
    lon = raw.get("Composite:GPSLongitude")
    if _validate_gps(lat, lon):
        gps = GpsData(
            latitude=float(lat),
            longitude=float(lon),
            altitude=_safe_float(raw.get("Composite:GPSAltitude")),
        )

    # Camera: prefer Model, fall back to Make.
    camera = raw.get("EXIF:Model") or raw.get("EXIF:Make") or None

    return ExifData(timestamp=timestamp, gps=gps, camera=camera)


def _normalize_timestamp(raw_value) -> str | None:
    """
    Normalize an exiftool timestamp value to ISO 8601.

    Strips timezone offsets to preserve wall-clock time (matching Node.js
    behavior). Delegates string parsing to normalize_disk_date().

    Handles:
    - EXIF string: "2019:07:15 14:30:00" -> "2019-07-15T14:30:00"
    - EXIF with tz: "2019:07:15 14:30:00+02:00" -> "2019-07-15T14:30:00"
    - Numeric (Unix epoch): 1563197400 -> "2019-07-15T13:30:00"

    Returns None if the value is missing, empty, or unparseable.
    """
    if raw_value is None:
        return None

    # Numeric (Unix epoch).
    if isinstance(raw_value, (int, float)):
        try:
            dt = datetime.fromtimestamp(raw_value, tz=timezone.utc)
            return dt.strftime("%Y-%m-%dT%H:%M:%S")
        except (ValueError, OSError):
            return None

    raw_str = str(raw_value).strip()
    if not raw_str or raw_str == "0000:00:00 00:00:00":
        return None

    return normalize_disk_date(raw_str)


def _validate_gps(lat, lon) -> bool:
    """
    Validate GPS coordinates. Returns False for missing or zero-zero data.

    Per the project's guiding principle: if latitude or longitude are
    0, 0.0, null, or undefined, skip geo data entirely.
    """
    if lat is None or lon is None:
        return False

    try:
        lat_f = float(lat)
        lon_f = float(lon)
    except (ValueError, TypeError):
        return False

    if lat_f == 0.0 and lon_f == 0.0:
        return False

    return True


def _safe_float(value) -> float | None:
    """Convert to float, returning None if not possible."""
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None
