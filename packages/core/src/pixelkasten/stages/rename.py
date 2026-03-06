"""
Rename stage — compute target paths for media files.

Ported from packages/core/src/stages/rename.js with intentional divergence:
no month directories. Format is YYYY/yyyymmdd-hhmmss.ext (loose) or
YYYY/yyyymmdd - Album Name/yyyymmdd-hhmmss.ext (album).
"""

import os
from datetime import datetime

from pixelkasten.manifest import ManifestEntry, Rename, Status


def rename(manifest: list[ManifestEntry]) -> None:
    """
    Resolve target paths for media files based on their timestamps.

    Mutates manifest entries in-place, setting entry.rename.
    Skips entries marked for deletion, error, or with skipped metadata.
    """
    # Filter to candidates: keepable and not skipped by reconcile
    candidates = [
        e
        for e in manifest
        if e.can_keep() and (e.metadata is None or e.metadata.status != Status.SKIPPED)
    ]

    if not candidates:
        return

    # Resolve earliest dates for each album
    album_dates = _resolve_album_dates(candidates)

    # Track used paths for collision detection
    used_paths: set[str] = set()

    for entry in candidates:
        try:
            entry.rename = _resolve_target_path(entry, used_paths, album_dates)
        except Exception as e:
            entry.rename = Rename(status=Status.ERROR, error=str(e))


def _resolve_album_dates(candidates: list[ManifestEntry]) -> dict[str, datetime]:
    """Resolve the earliest valid date for each album."""
    album_dates: dict[str, datetime] = {}

    for entry in candidates:
        if entry.source.type != "album":
            continue

        dates = entry.metadata.dates if entry.metadata else []
        parsed = _first_valid_date(dates)

        if not parsed:
            continue

        album_name = entry.source.name
        if not album_name:
            continue

        existing = album_dates.get(album_name)
        if not existing or parsed < existing:
            album_dates[album_name] = parsed

    return album_dates


def _first_valid_date(dates: list[str]) -> datetime | None:
    """Return the first parseable date from the list, or None."""
    for d in dates:
        try:
            return datetime.fromisoformat(d)
        except (ValueError, TypeError):
            pass
    return None


def _resolve_target_path(
    entry: ManifestEntry,
    used_paths: set[str],
    album_dates: dict[str, datetime],
) -> Rename:
    """Resolve the target path for a single manifest entry."""
    dates = entry.metadata.dates if entry.metadata else []

    if not dates:
        raise ValueError(f"No timestamp available for {entry.media_path}")

    parsed = _first_valid_date(dates)
    if not parsed:
        raise ValueError(f"No valid date format found for {entry.media_path}")

    timestamp = parsed.strftime("%Y%m%d-%H%M%S")
    ext = os.path.splitext(entry.media_path)[1].lower()

    # Determine directory structure
    album_name = entry.source.name if entry.source.type == "album" else None
    album_date = album_dates.get(album_name) if album_name else None

    # Use album's earliest date for directory, or entry's own date
    dir_date = album_date or parsed

    if album_name:
        dir_prefix = dir_date.strftime("%Y%m%d")
        base_path = f"{dir_date.year}/{dir_prefix} - {album_name}/{timestamp}{ext}"
    else:
        base_path = f"{parsed.year}/{timestamp}{ext}"

    target_path = _resolve_collision(base_path, used_paths)
    used_paths.add(target_path)

    return Rename(status=Status.PROCESSED, target_path=target_path)


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
