"""
Emit stage — write the working library.

Replaces apply() in the init pipeline. Per keeper entry:
  1. Compute the target filename: <group_id>.<lowercased_ext>. Within a single
     emit run, multiple members of the same group sharing an extension (e.g.,
     edited image variants) get a _2, _3, ... suffix.
  2. Copy the source file to <dst>/<filename>.
  3. If write_tags is non-empty, apply them via exiftool on the copy.
  4. Write a sidecar JSON to <dst>/.pixelkasten/<filename>.pk.json with
     three fields: dates, geo, album.

Unsupported formats (reconcile marked them SKIPPED) are not emitted. The
working library only contains files the pipeline can reason about.
"""

import json
import os
import shutil
from collections.abc import Callable

from pixelkasten.tools.exiftool import write_metadata
from pixelkasten.configuration import Options
from pixelkasten.manifest import Apply, ApplyResult, ManifestEntry, Status

SIDECAR_DIR_NAME = ".pixelkasten"
SIDECAR_SUFFIX = ".pk.json"


def emit(
    manifest: list[ManifestEntry],
    options: Options,
    on_progress: Callable[[int], None] | None = None,
) -> None:
    """Emit the working library: GUID-named copies + per-asset sidecars."""
    if options.destination is None:
        raise ValueError("destination is required for emit")
    destination = options.destination

    keepers = [e for e in manifest if e.can_keep()]
    if not keepers:
        return

    sidecar_dir = os.path.join(destination, SIDECAR_DIR_NAME)
    os.makedirs(sidecar_dir, exist_ok=True)

    used_names: set[str] = set()

    for i, entry in enumerate(keepers):
        try:
            entry.apply = _emit_entry(entry, destination, sidecar_dir, used_names)
        except Exception as e:
            entry.apply = Apply(status=Status.ERROR, error=str(e))
        if on_progress is not None:
            on_progress(i + 1)


def _emit_entry(
    entry: ManifestEntry,
    destination: str,
    sidecar_dir: str,
    used_names: set[str],
) -> Apply:
    """Copy one entry to the working library and write its sidecar."""
    if entry.metadata and entry.metadata.status == Status.SKIPPED:
        # Unsupported handlers leave the file out of the working library.
        return Apply(status=Status.SKIPPED, error=entry.metadata.error)

    ext = os.path.splitext(entry.media_path)[1].lower()
    final_name = _disambiguate(f"{entry.group_id}{ext}", entry.group_id, ext, used_names)
    used_names.add(final_name)

    dest_path = os.path.join(destination, final_name)
    shutil.copy2(entry.media_path, dest_path)

    write_tags = entry.metadata.write_tags if entry.metadata else []
    if write_tags:
        write_metadata(dest_path, write_tags)

    sidecar_path = os.path.join(sidecar_dir, f"{final_name}{SIDECAR_SUFFIX}")
    with open(sidecar_path, "w") as f:
        json.dump(_build_sidecar(entry), f)

    return Apply(
        status=Status.PROCESSED,
        result=ApplyResult.WRITTEN if write_tags else ApplyResult.COPIED,
        target_path=dest_path,
    )


def _disambiguate(candidate: str, stem: str, ext: str, used: set[str]) -> str:
    """Return candidate, or <stem>_2.<ext>, <stem>_3.<ext>, ... if taken."""
    if candidate not in used:
        return candidate
    counter = 2
    while True:
        attempt = f"{stem}_{counter}{ext}"
        if attempt not in used:
            return attempt
        counter += 1


def _build_sidecar(entry: ManifestEntry) -> dict:
    """Three-field sidecar: dates, geo, album."""
    dates = list(entry.metadata.dates) if entry.metadata else []

    geo = None
    if entry.metadata and entry.metadata.geo:
        g = entry.metadata.geo
        geo = {
            "latitude": g.latitude,
            "longitude": g.longitude,
            "altitude": g.altitude,
        }

    album = entry.source.name if entry.source.type == "album" else None

    return {"dates": dates, "geo": geo, "album": album}
