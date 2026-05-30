"""Plan: read each record onto its entry and resolve a relative destination
``target``. Reads records but writes nothing — ``emit`` is the only writer."""

import os
import re
from datetime import datetime

from pixelkasten.commands.export.state import ExportEntry, ExportState
from pixelkasten.utils.record import read_record

_INVALID_NAME_CHARS = re.compile(r"[/\\\x00-\x1f]")


def plan(state: ExportState) -> None:
    """Read each entry's record onto the entry, bucket by group, reject
    proposed_album conflicts, and set each entry's relative ``target``. Only
    mutates entries in memory; ``emit`` performs the copies."""
    for entry in state.entries:
        data = read_record(entry.record)
        entry.dates = data.get("dates") or []
        entry.album = data.get("album")
        entry.proposed_album = data.get("proposed_album")
        entry.group_id = data.get("group_id")

    groups = _bucket_by_group_id(state.entries)
    _check_proposal_conflicts(groups)

    album_min_dates = _compute_album_min_dates(groups)
    used_paths: set[str] = set()
    # Process groups in deterministic order so collision tie-breaking is stable.
    for key in sorted(groups):
        group = groups[key]
        album = _group_target_album(group)
        group_min_date = _group_min_date(group)
        # The folder's date prefix uses the album's earliest date across all
        # groups in the album; the filename's HHMMSS uses the file's own date
        # (or the group's date as fallback within an album).
        folder_min_date = album_min_dates.get(album) if album else group_min_date
        for entry in group:
            target = _resolve_member_path(entry, album, folder_min_date, group_min_date, used_paths)
            used_paths.add(target)
            entry.target = target


def _bucket_by_group_id(entries: list[ExportEntry]) -> dict[str, list[ExportEntry]]:
    """Group entries by ``group_id``. Entries without one are keyed by their
    (unique) media filename so they behave like singleton groups."""
    out: dict[str, list[ExportEntry]] = {}
    for entry in entries:
        key = entry.group_id or os.path.basename(entry.media)
        out.setdefault(key, []).append(entry)
    return out


def _check_proposal_conflicts(groups: dict[str, list[ExportEntry]]) -> None:
    """Raise if any group's members carry two distinct ``proposed_album`` values.

    A group exports to a single album (``_group_target_album`` picks the one
    non-null proposal and applies it to every member), so members only need to
    *agree* — a partial proposal (some members null) resolves fine.
    """
    conflicts: list[str] = []
    for key, entries in groups.items():
        proposals = {e.proposed_album for e in entries if e.proposed_album}
        if len(proposals) > 1:
            conflicts.append(f"  {key}: {sorted(proposals)}")
    if conflicts:
        raise RuntimeError(
            "proposed_album disagreement within group(s); resolve before exporting:\n"
            + "\n".join(conflicts)
        )


def _compute_album_min_dates(groups: dict[str, list[ExportEntry]]) -> dict[str, datetime]:
    """For each target album, the earliest date across every group's members."""
    out: dict[str, datetime] = {}
    for entries in groups.values():
        album = _group_target_album(entries)
        if not album:
            continue
        group_date = _group_min_date(entries)
        if group_date is None:
            continue
        existing = out.get(album)
        if existing is None or group_date < existing:
            out[album] = group_date
    return out


def _group_target_album(entries: list[ExportEntry]) -> str | None:
    """proposed_album wins; otherwise the import-time album; otherwise None."""
    proposed = next((e.proposed_album for e in entries if e.proposed_album), None)
    if proposed:
        return proposed
    return next((e.album for e in entries if e.album), None)


def _group_min_date(entries: list[ExportEntry]) -> datetime | None:
    """Earliest valid date across all members, used as the album folder date."""
    best: datetime | None = None
    for entry in entries:
        for d in entry.dates:
            parsed = _parse_iso(d)
            if parsed is not None and (best is None or parsed < best):
                best = parsed
    return best


def _resolve_member_path(
    entry: ExportEntry,
    album: str | None,
    folder_min_date: datetime | None,
    group_min_date: datetime | None,
    used: set[str],
) -> str:
    """
    Compute the relative target path for one entry.

    Three outcomes:
      - Album folder: ``<YYYY>/<YYYYMMDD>-<album>/<YYYYMMDD-HHMMSS>.<ext>``
        when both an album and a date are available. The folder ``YYYYMMDD``
        is the album's earliest date across all groups (so all groups in
        one album collapse into the same folder).
      - Year folder:  ``<YYYY>/<YYYYMMDD-HHMMSS>.<ext>`` for dated loose files.
      - Destination root: ``<filename>`` (the working-library uuid name)
        for undated entries. ``find <dst> -maxdepth 1 -type f`` lists them.
    """
    own_date = _first_valid_date(entry.dates)
    timestamp_date = own_date or group_min_date or folder_min_date

    filename = os.path.basename(entry.media)
    ext = os.path.splitext(filename)[1]

    if album and timestamp_date is not None:
        folder = (
            f"{folder_min_date.year}/{folder_min_date.strftime('%Y%m%d')}-{_sanitize_album(album)}"
        )
        base = f"{timestamp_date.strftime('%Y%m%d-%H%M%S')}{ext}"
        return _disambiguate(os.path.join(folder, base), used)

    if own_date is not None:
        folder = f"{own_date.year}"
        base = f"{own_date.strftime('%Y%m%d-%H%M%S')}{ext}"
        return _disambiguate(os.path.join(folder, base), used)

    # Undated: keep the working-library filename at the destination root.
    return _disambiguate(filename, used)


def _disambiguate(rel_path: str, used: set[str]) -> str:
    """Append -1, -2, ... before extension when ``rel_path`` is already taken."""
    if rel_path not in used:
        return rel_path
    root, ext = os.path.splitext(rel_path)
    counter = 1
    while True:
        candidate = f"{root}-{counter}{ext}"
        if candidate not in used:
            return candidate
        counter += 1


def _parse_iso(d: str) -> datetime | None:
    """Parse an ISO date string, or ``None`` if it isn't one."""
    try:
        return datetime.fromisoformat(d)
    except (TypeError, ValueError):
        return None


def _first_valid_date(dates: list[str]) -> datetime | None:
    for d in dates:
        parsed = _parse_iso(d)
        if parsed is not None:
            return parsed
    return None


def _sanitize_album(name: str) -> str:
    """Replace path separators and control chars with ``-``."""
    return _INVALID_NAME_CHARS.sub("-", name).strip()
