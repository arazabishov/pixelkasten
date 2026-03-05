"""
Rename stage — compute target paths for media files.

Ported from packages/core/src/stages/rename.js with intentional divergence:
no month directories. Format is YYYY/yyyymmdd-hhmmss.ext (loose) or
YYYY/yyyymmdd - Album Name/yyyymmdd-hhmmss.ext (album).
"""

import os

from pixelkasten.core.datetime import parse_iso_date
from pixelkasten.core.manifest import can_keep


def rename(manifest: list[dict]) -> None:
    """
    Resolve target paths for media files based on their timestamps.

    Mutates manifest entries in-place, adding entry["rename"] with
    status and targetPath.

    Skips entries marked for deletion, error, or with skipped metadata.
    """
    # Filter to candidates: keepable and not skipped by reconcile
    candidates = [
        e for e in manifest if can_keep(e) and e.get("metadata", {}).get("status") != "skipped"
    ]

    if not candidates:
        return

    # Resolve earliest dates for each album
    album_dates = _resolve_album_dates(candidates)

    # Track used paths for collision detection
    used_paths: set[str] = set()

    for entry in candidates:
        try:
            entry["rename"] = _resolve_target_path(entry, used_paths, album_dates)
        except Exception as e:
            entry["rename"] = {
                "status": "error",
                "reason": str(e),
            }


def _resolve_album_dates(candidates: list[dict]) -> dict[str, dict]:
    """Resolve the earliest valid date for each album."""
    album_dates: dict[str, dict] = {}

    for entry in candidates:
        if entry.get("source", {}).get("type") != "album":
            continue

        dates = entry.get("metadata", {}).get("dates", [])
        parsed = None
        for d in dates:
            parsed = parse_iso_date(d)
            if parsed:
                break

        if not parsed:
            continue

        album_name = entry["source"]["name"]
        existing = album_dates.get(album_name)

        if not existing or _is_earlier_date(parsed, existing):
            album_dates[album_name] = parsed

    return album_dates


def _is_earlier_date(a: dict, b: dict) -> bool:
    """Returns True if date a is earlier than date b."""
    for field in ["year", "month", "day", "hour", "minute", "second"]:
        if a[field] != b[field]:
            return a[field] < b[field]
    return False


def _resolve_target_path(
    entry: dict,
    used_paths: set[str],
    album_dates: dict[str, dict],
) -> dict:
    """Resolve the target path for a single manifest entry."""
    dates = entry.get("metadata", {}).get("dates", [])

    if not dates:
        raise ValueError(f"No timestamp available for {entry['mediaPath']}")

    # Try each date in order until one parses
    parsed = None
    for d in dates:
        parsed = parse_iso_date(d)
        if parsed:
            break

    if not parsed:
        raise ValueError(f"No valid date format found for {entry['mediaPath']}")

    year = str(parsed["year"]).zfill(4)
    month = str(parsed["month"]).zfill(2)
    day = str(parsed["day"]).zfill(2)
    hour = str(parsed["hour"]).zfill(2)
    minute = str(parsed["minute"]).zfill(2)
    second = str(parsed["second"]).zfill(2)

    timestamp = f"{year}{month}{day}-{hour}{minute}{second}"
    ext = os.path.splitext(entry["mediaPath"])[1].lower()

    # Determine directory structure
    is_album = entry.get("source", {}).get("type") == "album"
    album_date = album_dates.get(entry["source"]["name"]) if is_album else None

    # Use album's earliest date for directory, or entry's own date
    dir_date = album_date or parsed
    dir_year = str(dir_date["year"]).zfill(4)
    dir_month = str(dir_date["month"]).zfill(2)
    dir_day = str(dir_date["day"]).zfill(2)

    if is_album:
        album_date_prefix = f"{dir_year}{dir_month}{dir_day}"
        base_path = f"{dir_year}/{album_date_prefix} - {entry['source']['name']}/{timestamp}{ext}"
    else:
        base_path = f"{dir_year}/{timestamp}{ext}"

    target_path = _resolve_collision(base_path, used_paths)
    used_paths.add(target_path)

    return {
        "status": "processed",
        "targetPath": target_path,
    }


def _resolve_collision(base_path: str, used_paths: set[str]) -> str:
    """Resolve path collisions by appending -1, -2, etc. before extension."""
    if base_path not in used_paths:
        return base_path

    root, ext = os.path.splitext(base_path)
    counter = 1

    while True:
        candidate = f"{root}-{counter}{ext}"
        if candidate not in used_paths:
            return candidate
        counter += 1
