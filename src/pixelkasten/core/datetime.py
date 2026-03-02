"""
Date normalization and parsing utilities for the takeout pipeline.

Ported from packages/core/src/core/datetime.js. These functions handle
EXIF-style dates, Unix epoch timestamps, and ISO date strings.

Key behavior: timezone offsets are stripped early to preserve "wall clock"
time in filenames (e.g., 14:30 stays 14:30 regardless of timezone).
"""

import re
from datetime import datetime, timezone

# Regex to capture: YYYY[:/-]MM[:/-]DD <space> HH:MM:SS
# No $ anchor — subseconds (.123) and timezone (+02:00) after seconds
# are naturally ignored by only capturing up to the 6th group.
_DISK_DATE_RE = re.compile(
    r"^(\d{4})[:/-](\d{2})[:/-](\d{2})\s+(\d{2}):(\d{2}):(\d{2})"
)


def normalize_disk_date(date: str) -> str | None:
    """
    Normalize raw ExifTool date strings to ISO format (YYYY-MM-DDTHH:MM:SS).

    Strips timezone offsets to preserve wall-clock time. Strips subsecond
    precision. Accepts flexible date separators (: - /).

    Returns None for non-string, None, empty, or unparseable input.
    """
    if not isinstance(date, str):
        return None

    m = _DISK_DATE_RE.match(date.strip())
    if not m:
        return None

    y, mo, d, h, mi, s = m.groups()
    return f"{y}-{mo}-{d}T{h}:{mi}:{s}"


def parse_iso_date(iso_date: str) -> dict | None:
    """
    Parse an ISO date string into its components.

    Returns a dict with:
        - year: int
        - month: int (1-12)
        - day: int (1-31)
        - hour: int (0-23)
        - minute: int (0-59)
        - second: int (0-59)

    Returns None for non-string, None, empty, or unparseable input.
    """
    if not isinstance(iso_date, str) or not iso_date:
        return None

    try:
        dt = datetime.fromisoformat(iso_date)
    except ValueError:
        return None

    return {
        "year": dt.year,
        "month": dt.month,
        "day": dt.day,
        "hour": dt.hour,
        "minute": dt.minute,
        "second": dt.second,
    }


def parse_photo_taken_time(timestamp: str | int) -> dict:
    """
    Convert a Unix epoch timestamp (seconds) to ISO and EXIF datetime formats.

    Args:
        timestamp: Unix epoch in seconds (string or int).

    Returns:
        {"iso": "YYYY-MM-DDTHH:MM:SS", "exif": "YYYY:MM:DD HH:MM:SS+00:00"}

    Raises:
        ValueError: If the timestamp cannot be parsed.
    """
    try:
        ts = int(timestamp)
    except (ValueError, TypeError):
        raise ValueError(f"Failed to parse photoTakenTime timestamp: {timestamp}")

    dt = datetime.fromtimestamp(ts, tz=timezone.utc)

    # Validate — int() on "" raises ValueError above, but NaN-equivalent
    # strings like "invalid" also raise, so this is mostly defensive.
    if dt.year < 1:
        raise ValueError(f"Failed to parse photoTakenTime timestamp: {timestamp}")

    iso = dt.strftime("%Y-%m-%dT%H:%M:%S")
    exif = dt.strftime("%Y:%m:%d %H:%M:%S") + "+00:00"

    return {"iso": iso, "exif": exif}
