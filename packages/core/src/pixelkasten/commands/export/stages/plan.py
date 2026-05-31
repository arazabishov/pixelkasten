"""Plan each entry's relative destination ``target`` from its loaded record data."""

import os
from datetime import datetime
from itertools import count

from pixelkasten.commands.export.types import Export, Group


def plan(state: Export) -> None:
    """Set each entry's relative ``target`` from its record. Assumes ``validate`` passed.

    Two layouts: ``<YYYY>/<YYYYMMDD>-<album>/<name>`` for albumed entries and
    ``<YYYY>/<name>`` for dated loose files, where ``<name>`` is
    ``<YYYYMMDD-HHMMSS>.<ext>``. Every record is dated (``first_date`` fails hard
    otherwise), so there is no undated fallback.
    """
    groups = state.grouped()

    album_min_dates = _compute_album_min_dates(groups)
    used_paths: set[str] = set()

    # Sort groups so collision suffixes (-1, -2) are assigned in a stable order.
    for group in sorted(groups, key=lambda g: g.id):
        album = group.target_album()

        for entry in group.entries:
            extension = os.path.splitext(entry.media)[1]
            own_date = entry.record.first_date()
            name = f"{own_date.strftime('%Y%m%d-%H%M%S')}{extension}"

            if album:
                # Folder uses the album-wide earliest date so all its groups collapse
                # into one folder; the filename uses the file's own date.
                folder_date = album_min_dates[album]
                folder = f"{folder_date.year}/{folder_date.strftime('%Y%m%d')}-{album}"

                target = os.path.join(folder, name)
            else:
                target = os.path.join(str(own_date.year), name)

            entry.target = _disambiguate(target, used_paths)
            used_paths.add(entry.target)


def _compute_album_min_dates(groups: list[Group]) -> dict[str, datetime]:
    """For each target album, the earliest date across every group in it.

    Precomputed before any path is assigned because the folder date spans groups:
    all groups in one album collapse into a single folder named by that earliest date.
    """
    out: dict[str, datetime] = {}
    for group in groups:
        album = group.target_album()
        if album:
            date = group.min_date()
            out[album] = min(date, out.get(album, date))
    return out


def _disambiguate(rel_path: str, used: set[str]) -> str:
    """Append -1, -2, ... before extension when ``rel_path`` is already taken."""
    if rel_path not in used:
        return rel_path
    root, ext = os.path.splitext(rel_path)
    candidates = (f"{root}-{n}{ext}" for n in count(1))
    return next(c for c in candidates if c not in used)
