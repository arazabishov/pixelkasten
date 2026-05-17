"""
Emit stage — write the working library.

Per keeper entry:
  1. Compute the target filename: <file_id>.<lowercased_ext>, where
     ``file_id`` is a fresh uuid4 hex per file. Group identity travels in
     the record (``group_id`` field), not the filename, so filename
     collisions inside a working library are impossible by construction.
  2. Copy the source file to <dst>/<filename>.
  3. If write_tags is non-empty, apply them via exiftool on the copy.
  4. Write a record to <dst>/.pixelkasten/<filename>.pk.json with four
     fields: dates, geo, album, group_id.

Unsupported formats (reconcile marked them SKIPPED) are not emitted. The
working library only contains files the pipeline can reason about.
"""

import os
import shutil
import uuid
from collections.abc import Callable

from pixelkasten.configuration import Options
from pixelkasten.layout import records_dir, record_path, write_record
from pixelkasten.manifest import Apply, ApplyResult, ManifestEntry, Status
from pixelkasten.utils.exiftool import write_metadata


def emit(
    manifest: list[ManifestEntry],
    options: Options,
    on_progress: Callable[[int], None] | None = None,
) -> None:
    """Emit the working library: per-file uuid-named copies + per-asset records."""
    if options.destination is None:
        raise ValueError("destination is required for emit")
    destination = options.destination

    keepers = [e for e in manifest if e.can_keep()]
    if not keepers:
        return

    os.makedirs(records_dir(destination), exist_ok=True)

    for i, entry in enumerate(keepers):
        try:
            entry.apply = _emit_entry(entry, destination)
        except Exception as e:
            entry.apply = Apply(status=Status.ERROR, error=str(e))
        if on_progress is not None:
            on_progress(i + 1)


def _emit_entry(entry: ManifestEntry, destination: str) -> Apply:
    """Copy one entry to the working library and write its record."""
    if entry.metadata and entry.metadata.status == Status.SKIPPED:
        # Unsupported handlers leave the file out of the working library.
        return Apply(status=Status.SKIPPED, error=entry.metadata.error)

    ext = os.path.splitext(entry.media_path)[1].lower()
    file_id = uuid.uuid4().hex
    final_name = f"{file_id}{ext}"

    dest_path = os.path.join(destination, final_name)
    shutil.copy2(entry.media_path, dest_path)

    write_tags = entry.metadata.write_tags if entry.metadata else []
    if write_tags:
        write_metadata(dest_path, write_tags)

    write_record(record_path(destination, final_name), _build_record(entry))

    return Apply(
        status=Status.PROCESSED,
        result=ApplyResult.WRITTEN if write_tags else ApplyResult.COPIED,
        target_path=dest_path,
    )


def _build_record(entry: ManifestEntry) -> dict:
    """Four-field record: dates, geo, album, group_id."""
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

    return {"dates": dates, "geo": geo, "album": album, "group_id": entry.group_id}
