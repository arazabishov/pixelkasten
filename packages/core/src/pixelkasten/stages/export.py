"""
Export a working library to a user-facing organized photo library.

Reads `.pk.json` sidecars, groups by stem (so Live Photo image+video and
edited variants stay co-located), resolves a per-group target album via the
fallback chain (proposed_album → album → date folder → Unsorted), and copies
files into a date-and-album folder hierarchy.

The working library is read-only here. Re-running this command produces the
same export deterministically.
"""

import json
import os
import re
import shutil
from datetime import datetime

from pixelkasten.configuration import ApplyOptions

SIDECAR_DIR = ".pixelkasten"
SIDECAR_SUFFIX = ".pk.json"
UNSORTED_DIR = "Unsorted"
_INVALID_NAME_CHARS = re.compile(r"[/\\\x00-\x1f]")


def apply_export(library: str, destination: str, options: ApplyOptions) -> dict:
    """
    Export `library` to `destination`. Returns a summary dict of counts.

    Raises:
        RuntimeError if destination exists and force=False.
        RuntimeError if two members of one group disagree on proposed_album.
    """
    sidecar_dir = os.path.join(library, SIDECAR_DIR)
    if not os.path.isdir(sidecar_dir):
        raise RuntimeError(f"Not a working library (missing {SIDECAR_DIR}/ at {library}).")

    if os.path.exists(destination) and os.listdir(destination):
        if not options.force:
            raise RuntimeError(
                f"Destination {destination} already exists and is not empty; pass --force to overwrite."
            )

    entries = _load_entries(library, sidecar_dir)
    groups = _bucket_by_stem(entries)
    _detect_and_propagate_proposals(groups)
    operations = _plan_operations(library, destination, groups)

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


def _load_entries(library: str, sidecar_dir: str) -> list[dict]:
    """Read every .pk.json into a typed-ish dict with derived fields."""
    entries: list[dict] = []
    for name in sorted(os.listdir(sidecar_dir)):
        if not name.endswith(SIDECAR_SUFFIX):
            continue
        media_filename = name[: -len(SIDECAR_SUFFIX)]
        media_path = os.path.join(library, media_filename)
        if not os.path.isfile(media_path):
            # Stale sidecar with no media file; ignore.
            continue
        with open(os.path.join(sidecar_dir, name)) as f:
            data = json.load(f)
        stem, ext = os.path.splitext(media_filename)
        entries.append(
            {
                "media_path": media_path,
                "filename": media_filename,
                "stem": stem,
                "ext": ext.lower(),
                "dates": data.get("dates") or [],
                "album": data.get("album"),
                "proposed_album": data.get("proposed_album"),
            }
        )
    return entries


def _bucket_by_stem(entries: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for entry in entries:
        out.setdefault(entry["stem"], []).append(entry)
    return out


def _detect_and_propagate_proposals(groups: dict[str, list[dict]]) -> None:
    """
    Within each group, ensure every member has the same `proposed_album`.

    Raises RuntimeError when members disagree (multiple non-null distinct
    values). When only some members have it set, propagate to the rest.
    """
    conflicts: list[str] = []
    for stem, members in groups.items():
        proposals = {m["proposed_album"] for m in members if m["proposed_album"]}
        if len(proposals) > 1:
            conflicts.append(f"  {stem}: {sorted(proposals)}")
            continue
        if proposals:
            value = next(iter(proposals))
            for m in members:
                m["proposed_album"] = value
    if conflicts:
        joined = "\n".join(conflicts)
        raise RuntimeError(
            "proposed_album disagreement within group(s); resolve before applying:\n" + joined
        )


# ---------- target paths ----------


def _plan_operations(
    library: str, destination: str, groups: dict[str, list[dict]]
) -> list[tuple[str, str]]:
    """Compute (src, dst) pairs for every keeper. Mutates nothing on disk."""
    album_min_dates = _compute_album_min_dates(groups)

    used_paths: set[str] = set()
    ops: list[tuple[str, str]] = []
    # Process groups in deterministic order so collision tie-breaking is stable.
    for stem in sorted(groups):
        members = groups[stem]
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
            member["_target_rel"] = target  # remembered for summary stats
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
    """proposed_album wins; otherwise the init-time album; otherwise None."""
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

    Album:                <YYYY>/<YYYYMMDD>-<album>/<YYYYMMDD-HHMMSS>.<ext>
                          where the folder YYYYMMDD is the album's earliest date
                          across all groups (so all groups in one album collapse
                          into the same folder).
    Loose with date:      <YYYY>/<YYYYMMDD-HHMMSS>.<ext>
    Loose without date:   Unsorted/<group_id>.<ext>
    """
    own_date = _first_valid_date(member["dates"])

    if album:
        if folder_min_date is None:
            # Album has no parsable date anywhere; fall back to Unsorted/.
            return _disambiguate(os.path.join(UNSORTED_DIR, member["filename"]), used)
        folder = (
            f"{folder_min_date.year}/{folder_min_date.strftime('%Y%m%d')}-{_sanitize_album(album)}"
        )
        # Filename HHMMSS prefers the file's own date, then its group's date,
        # then the album-wide date. Group siblings without their own date
        # co-locate using the group's date.
        timestamp_date = own_date or group_min_date or folder_min_date
        base = f"{timestamp_date.strftime('%Y%m%d-%H%M%S')}{member['ext']}"
        return _disambiguate(os.path.join(folder, base), used)

    if own_date is None:
        return _disambiguate(os.path.join(UNSORTED_DIR, member["filename"]), used)

    folder = f"{own_date.year}"
    base = f"{own_date.strftime('%Y%m%d-%H%M%S')}{member['ext']}"
    return _disambiguate(os.path.join(folder, base), used)


def _disambiguate(rel_path: str, used: set[str]) -> str:
    """Append -1, -2, ... before extension when `rel_path` is already taken."""
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
    """Replace path separators and control chars with `-`."""
    return _INVALID_NAME_CHARS.sub("-", name).strip()


def _summarize(
    operations: list[tuple[str, str]],
    destination: str,
    dry_run: bool,
) -> dict:
    """Count buckets so the CLI can print a summary."""
    unsorted_count = sum(1 for _, dst in operations if os.sep + UNSORTED_DIR + os.sep in dst)
    return {
        "total": len(operations),
        "unsorted": unsorted_count,
        "destination": destination,
        "dry_run": dry_run,
    }
