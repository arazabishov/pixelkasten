"""
Export a working library to a user-facing organized photo library.

Reads ``.pk.json`` records, buckets by each record's ``group_id`` (so Live
Photo image+video and edited variants stay co-located), resolves a
per-group target album via the fallback chain (proposed_album → album →
date-driven year folder → destination root for undated files), and copies
files into a date-and-album folder hierarchy.

The working library is read-only here. Re-running this command produces the
same export deterministically.
"""

import os
import re
import shutil
from dataclasses import dataclass
from datetime import datetime

from pixelkasten.configuration import ExportOptions
from pixelkasten.layout import RECORDS_DIR, RECORD_SUFFIX, read_record, records_dir

_INVALID_NAME_CHARS = re.compile(r"[/\\\x00-\x1f]")


@dataclass
class ExportSummary:
    """End-of-run counts from the `export` command."""

    # destination directory the export was written to
    destination: str

    # total files exported (or that would have been exported on dry_run)
    total: int

    # files with no parseable date — landed at the destination root
    undated: int

    # True when the run was a dry-run (no files copied)
    dry_run: bool


def export(library: str, destination: str, options: ExportOptions) -> ExportSummary:
    """
    Export ``library`` to ``destination``. Returns an ``ExportSummary`` of counts.

    Raises:
        RuntimeError if destination exists and force=False.
        RuntimeError if two members of one group disagree on proposed_album.
    """
    rdir = records_dir(library)
    if not os.path.isdir(rdir):
        raise RuntimeError(f"Not a working library (missing {RECORDS_DIR}/ at {library}).")

    if os.path.exists(destination) and os.listdir(destination):
        if not options.force:
            raise RuntimeError(
                f"Destination {destination} already exists and is not empty; "
                "pass --force to overwrite."
            )

    entries = _load_entries(library, rdir)
    groups = _bucket_by_group_id(entries)
    _detect_and_propagate_proposals(groups)
    operations = _plan_operations(destination, groups)

    if options.dry_run:
        for src, dst in operations:
            print(f"copy {src} -> {dst}")
        return _summarize(operations, destination, dry_run=True)

    if options.force and os.path.exists(destination):
        shutil.rmtree(destination)
    os.makedirs(destination, exist_ok=True)

    for src, dst in operations:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)

    return _summarize(operations, destination, dry_run=False)


# ---------- load + group ----------


def _load_entries(library: str, rdir: str) -> list[dict]:
    """Read every ``.pk.json`` into a typed-ish dict with derived fields."""
    entries: list[dict] = []
    for name in sorted(os.listdir(rdir)):
        if not name.endswith(RECORD_SUFFIX):
            continue
        media_filename = name[: -len(RECORD_SUFFIX)]
        media_path = os.path.join(library, media_filename)
        if not os.path.isfile(media_path):
            # Stale record with no media file; ignore.
            continue
        data = read_record(os.path.join(rdir, name))
        _, ext = os.path.splitext(media_filename)
        entries.append(
            {
                "media_path": media_path,
                "filename": media_filename,
                "ext": ext.lower(),
                "dates": data.get("dates") or [],
                "album": data.get("album"),
                "proposed_album": data.get("proposed_album"),
                "group_id": data.get("group_id"),
            }
        )
    return entries


def _bucket_by_group_id(entries: list[dict]) -> dict[str, list[dict]]:
    """Group entries by their record's ``group_id``. Records with no
    ``group_id`` each get a bucket keyed by their unique filename so they
    behave like singleton groups."""
    out: dict[str, list[dict]] = {}
    for entry in entries:
        key = entry.get("group_id") or entry["filename"]
        out.setdefault(key, []).append(entry)
    return out


def _detect_and_propagate_proposals(groups: dict[str, list[dict]]) -> None:
    """
    Within each group, ensure every member has the same ``proposed_album``.

    Raises RuntimeError when members disagree (multiple non-null distinct
    values). When only some members have it set, propagate to the rest.
    """
    conflicts: list[str] = []
    for key, members in groups.items():
        proposals = {m["proposed_album"] for m in members if m["proposed_album"]}
        if len(proposals) > 1:
            conflicts.append(f"  {key}: {sorted(proposals)}")
            continue
        if proposals:
            value = next(iter(proposals))
            for m in members:
                m["proposed_album"] = value
    if conflicts:
        joined = "\n".join(conflicts)
        raise RuntimeError(
            "proposed_album disagreement within group(s); resolve before exporting:\n" + joined
        )


# ---------- target paths ----------


def _plan_operations(destination: str, groups: dict[str, list[dict]]) -> list[tuple[str, str]]:
    """Compute (src, dst) pairs for every keeper. Mutates nothing on disk."""
    album_min_dates = _compute_album_min_dates(groups)

    used_paths: set[str] = set()
    ops: list[tuple[str, str]] = []
    # Process groups in deterministic order so collision tie-breaking is stable.
    for key in sorted(groups):
        members = groups[key]
        album = _group_target_album(members)
        group_min_date = _group_min_date(members)
        # The folder's date prefix uses the album's earliest date across all
        # groups in the album; the filename's HHMMSS uses the file's own date
        # (or the group's date as fallback within an album).
        folder_min_date = album_min_dates.get(album) if album else group_min_date
        for member in members:
            target = _resolve_member_path(
                member, album, folder_min_date, group_min_date, used_paths
            )
            used_paths.add(target)
            ops.append((member["media_path"], os.path.join(destination, target)))
    return ops


def _compute_album_min_dates(groups: dict[str, list[dict]]) -> dict[str, datetime]:
    """For each target album, the earliest date across every group's members."""
    out: dict[str, datetime] = {}
    for members in groups.values():
        album = _group_target_album(members)
        if not album:
            continue
        group_date = _group_min_date(members)
        if group_date is None:
            continue
        existing = out.get(album)
        if existing is None or group_date < existing:
            out[album] = group_date
    return out


def _group_target_album(members: list[dict]) -> str | None:
    """proposed_album wins; otherwise the import-time album; otherwise None."""
    proposed = next((m["proposed_album"] for m in members if m["proposed_album"]), None)
    if proposed:
        return proposed
    return next((m["album"] for m in members if m["album"]), None)


def _group_min_date(members: list[dict]) -> datetime | None:
    """Earliest valid date across all members, used as the album folder date."""
    best: datetime | None = None
    for m in members:
        for d in m["dates"]:
            try:
                parsed = datetime.fromisoformat(d)
            except (TypeError, ValueError):
                continue
            if best is None or parsed < best:
                best = parsed
    return best


def _resolve_member_path(
    member: dict,
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
    own_date = _first_valid_date(member["dates"])
    timestamp_date = own_date or group_min_date or folder_min_date

    if album and timestamp_date is not None:
        folder = (
            f"{folder_min_date.year}/{folder_min_date.strftime('%Y%m%d')}-{_sanitize_album(album)}"
        )
        base = f"{timestamp_date.strftime('%Y%m%d-%H%M%S')}{member['ext']}"
        return _disambiguate(os.path.join(folder, base), used)

    if own_date is not None:
        folder = f"{own_date.year}"
        base = f"{own_date.strftime('%Y%m%d-%H%M%S')}{member['ext']}"
        return _disambiguate(os.path.join(folder, base), used)

    # Undated: keep the working-library filename at the destination root.
    return _disambiguate(member["filename"], used)


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


def _first_valid_date(dates: list[str]) -> datetime | None:
    for d in dates:
        try:
            return datetime.fromisoformat(d)
        except (TypeError, ValueError):
            continue
    return None


def _sanitize_album(name: str) -> str:
    """Replace path separators and control chars with ``-``."""
    return _INVALID_NAME_CHARS.sub("-", name).strip()


def _summarize(
    operations: list[tuple[str, str]],
    destination: str,
    dry_run: bool,
) -> ExportSummary:
    """Count buckets so the CLI can print a summary."""
    # Undated files keep the working-library filename and land at the root,
    # so their destination has no subdirectory between dest and the file.
    undated = sum(
        1 for _, dst in operations if os.path.dirname(dst) == os.path.normpath(destination)
    )
    return ExportSummary(
        destination=destination,
        total=len(operations),
        undated=undated,
        dry_run=dry_run,
    )
