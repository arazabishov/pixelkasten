"""Plan each entry's relative destination ``target`` from its loaded record data."""

import os
from datetime import datetime

from pixelkasten.commands.export.state import ExportEntry, ExportState
from pixelkasten.utils.album import check_album_conflicts, check_album_name


def plan(state: ExportState) -> None:
    """Map record data onto entries, reject conflicts, and set ``target``."""
    # Bucket entries by group — one logical asset's files (e.g. an HEIC and its
    # .mov / -edited variant) share a group_id and export to one album together.
    groups: dict[str, list[ExportEntry]] = {}
    for entry in state.entries:
        group_id = entry.record.group_id or os.path.basename(entry.media)
        groups.setdefault(group_id, []).append(entry)

    _reject_proposal_conflicts(groups)
    _reject_invalid_album_names(groups)

    album_min_dates = _compute_album_min_dates(groups)
    used_paths: set[str] = set()

    # Sort groups so collision suffixes (-1, -2) are assigned in a stable,
    # reproducible order when unrelated files resolve to the same target path.
    for group_id in sorted(groups):
        group = groups[group_id]

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


def _reject_proposal_conflicts(groups: dict[str, list[ExportEntry]]) -> None:
    """Raise if any group's members disagree on ``proposed_album``.

    ``check`` surfaces the same conflicts for the agent to resolve (via
    ``propose``) before export; this is the hard stop if one slips through.
    """
    proposals_by_group: dict[str, set[str]] = {}
    for group_id, group in groups.items():
        proposals_by_group[group_id] = {
            e.record.proposed_album for e in group if e.record.proposed_album
        }

    conflicts = check_album_conflicts(proposals_by_group)
    if not conflicts:
        return

    detail = "\n".join(f"  {group_id}: {proposals}" for group_id, proposals in conflicts)
    raise RuntimeError(
        "proposed_album disagreement within group(s); resolve before exporting:\n" + detail
    )


def _reject_invalid_album_names(groups: dict[str, list[ExportEntry]]) -> None:
    invalid: set[str] = set()
    for group in groups.values():
        album = _group_target_album(group)
        if album and not check_album_name(album):
            invalid.add(album)

    if not invalid:
        return

    detail = "\n".join(f"  {album!r}" for album in sorted(invalid))
    raise RuntimeError("invalid album name(s); resolve before exporting:\n" + detail)


def _compute_album_min_dates(groups: dict[str, list[ExportEntry]]) -> dict[str, datetime]:
    """For each target album, the earliest date across every group in it."""
    out: dict[str, datetime] = {}
    for group in groups.values():
        album = _group_target_album(group)
        if not album:
            continue
        group_date = _group_min_date(group)
        if group_date is None:
            continue
        existing = out.get(album)
        if existing is None or group_date < existing:
            out[album] = group_date
    return out


def _group_target_album(group: list[ExportEntry]) -> str | None:
    """proposed_album wins; otherwise the import-time album; otherwise None."""
    proposed = next((e.record.proposed_album for e in group if e.record.proposed_album), None)
    if proposed:
        return proposed
    return next((e.record.album for e in group if e.record.album), None)


def _group_min_date(group: list[ExportEntry]) -> datetime | None:
    """Earliest date across all members, or None when no member is dated."""
    dates = [datetime.fromisoformat(d) for entry in group for d in entry.record.dates]
    return min(dates) if dates else None


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
    own_date = datetime.fromisoformat(entry.record.dates[0]) if entry.record.dates else None
    timestamp_date = own_date or group_min_date or folder_min_date

    filename = os.path.basename(entry.media)
    ext = os.path.splitext(filename)[1]

    if album and timestamp_date is not None:
        folder = f"{folder_min_date.year}/{folder_min_date.strftime('%Y%m%d')}-{album}"
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
