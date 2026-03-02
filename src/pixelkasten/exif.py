"""
EXIF metadata reading via exiftool — Phase 2a of the AI pipeline.

Reads timestamps, GPS coordinates, and camera model from all images
using exiftool as a subprocess. Also provides offline reverse geocoding
to resolve GPS coordinates to city/region/country names.

Prerequisites:
    - exiftool installed and on PATH (`brew install exiftool`)
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, TypedDict

from pixelkasten.datetime import normalize_disk_date
from pixelkasten.exiftool import check_exiftool  # noqa: F401 — re-exported
from pixelkasten.exiftool import read_metadata as _read_metadata_raw


class GpsData(TypedDict, total=False):
    latitude: float
    longitude: float
    altitude: float | None


class ExifData(TypedDict, total=False):
    timestamp: str | None
    gps: GpsData | None
    camera: str | None


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
    process for all files, not one per file). Delegates subprocess work
    to exiftool.read_metadata().

    Args:
        file_paths: List of image file paths to read.

    Returns:
        Dict mapping file path (string) to parsed ExifData. Files that
        fail to read or have no relevant metadata get an ExifData with
        all None values.
    """
    if not file_paths:
        return {}

    raw_results = _read_metadata_raw(file_paths, _EXIF_TAGS)

    parsed = {}
    for source_file, raw in raw_results.items():
        parsed[source_file] = _parse_exiftool_entry(raw)

    # Fill in any files that didn't appear in the output.
    for p in file_paths:
        key = str(p)
        if key not in parsed:
            parsed[key] = _empty_exif()

    return parsed


def read_exif_for_all(
    manifest: dict,
    on_progress: Callable[[int], None] | None = None,
) -> dict[str, ExifData]:
    """
    Read EXIF from all successfully embedded images in a manifest.

    Filters to entries where status="ok", then batch-reads EXIF for all
    of them in a single exiftool call.

    Args:
        manifest: Parsed manifest dict (from read_manifest).
        on_progress: Optional callback, called with count processed.

    Returns:
        Dict of {image_path: ExifData} for all ok-status images.
    """
    ok_entries = [entry for entry in manifest["entries"] if entry.get("status") == "ok"]

    file_paths = [Path(entry["path"]) for entry in ok_entries]

    if on_progress is not None:
        on_progress(0)

    result = read_exif(file_paths)

    if on_progress is not None:
        on_progress(len(file_paths))

    return result


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


class LocationInfo(TypedDict):
    city: str
    region: str
    country: str
    display_name: str


def reverse_geocode(exif_data: dict[str, ExifData]) -> dict[str, LocationInfo]:
    """
    Resolve GPS coordinates to structured location data.

    Takes the output of read_exif() or read_exif_for_all(), extracts
    unique GPS coordinates, batch-resolves them via the reverse_geocoder
    library (offline, no API calls), and returns structured location info.

    The returned LocationInfo includes city, region (state/province),
    country code, and a display_name for human-readable output. The
    region + country combination is used for hierarchical matching
    (e.g., "California, US" groups San Francisco, Stanford, and
    Mountain View together).

    Args:
        exif_data: Dict mapping image path -> ExifData.

    Returns:
        Dict mapping image path -> LocationInfo.
        Only includes entries that have valid GPS data.
    """
    import reverse_geocoder as rg

    # Collect unique coordinates (rounded to 2 decimal places for dedup).
    coord_to_paths: dict[tuple[float, float], list[str]] = {}
    for path, exif in exif_data.items():
        gps = exif.get("gps")
        if not gps:
            continue
        rounded = (round(gps["latitude"], 2), round(gps["longitude"], 2))
        if rounded not in coord_to_paths:
            coord_to_paths[rounded] = []
        coord_to_paths[rounded].append(path)

    if not coord_to_paths:
        return {}

    # Batch resolve all unique coordinates in one call.
    coords_list = list(coord_to_paths.keys())
    results = rg.search(coords_list)

    # Build path -> LocationInfo mapping.
    location_data = {}
    for coord, result in zip(coords_list, results):
        city = result.get("name", "")
        region = result.get("admin1", "")
        country = result.get("cc", "")

        parts = [p for p in [city, region, country] if p]
        display_name = ", ".join(parts)

        info = LocationInfo(
            city=city,
            region=region,
            country=country,
            display_name=display_name,
        )

        for path in coord_to_paths[coord]:
            location_data[path] = info

    return location_data
