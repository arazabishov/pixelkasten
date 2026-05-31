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

from pixelkasten.configuration import IngestOptions
from pixelkasten.commands.ingest.state import Apply, ApplyResult, IngestEntry
from pixelkasten.pipeline import Status
from pixelkasten.tools.exiftool import write_metadata
from pixelkasten.utils.progress import noop_progress
from pixelkasten.stores.record import Record, record_path, records_dir, write_record


def emit(
    manifest: list[IngestEntry],
    options: IngestOptions,
    progress: Callable = noop_progress,
) -> None:
    """Emit the working library: per-file uuid-named copies + per-asset records."""
    if options.destination is None:
        raise ValueError("destination is required for emit")
    destination = options.destination

    keepers = [e for e in manifest if e.can_keep()]
    if not keepers:
        return

    os.makedirs(records_dir(destination), exist_ok=True)

    with progress("Emitting working library", len(keepers)) as tick:
        for i, entry in enumerate(keepers):
            try:
                entry.apply = _emit_entry(entry, destination)
            except Exception as e:
                entry.apply = Apply(status=Status.ERROR, error=str(e))
            tick(i + 1)


def _emit_entry(entry: IngestEntry, destination: str) -> Apply:
    """Copy one entry to the working library and write its record."""
    if entry.metadata and entry.metadata.status == Status.SKIPPED:
        # Unsupported handlers leave the file out of the working library.
        return Apply(status=Status.SKIPPED, error=entry.metadata.error)

    # ``os.path.splitext`` returns ``(root, ext)``; we pick [1] to keep just
    # the extension and append it to a fresh uuid4 hex. Examples:
    #   "IMG_001.HEIC"       -> ".heic"
    #   "IMG_001-edited.jpg" -> ".jpg"    (suffixes are part of the basename)
    #   "IMG_001.MP.jpg"     -> ".jpg"    (Motion Photo — final ext wins)
    #   "<uuid>-000"         -> ""        (no extension; dest_name has none)
    # Same extraction link's ``_parse_media`` uses for its ``extension`` field,
    # so the two stages agree on what the extension is.
    dest_name = f"{uuid.uuid4().hex}{os.path.splitext(entry.media_path)[1].lower()}"
    dest_path = os.path.join(destination, dest_name)
    shutil.copy2(entry.media_path, dest_path)

    write_tags = entry.metadata.write_tags if entry.metadata else []
    if write_tags:
        write_metadata(dest_path, write_tags)

    write_record(_build_record(record_path(destination, dest_name), entry))

    return Apply(
        status=Status.PROCESSED,
        result=ApplyResult.WRITTEN if write_tags else ApplyResult.COPIED,
        target_path=dest_path,
    )


def _build_record(path: str, entry: IngestEntry) -> Record:
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

    return Record(path=path, dates=dates, geo=geo, album=album, group_id=entry.group_id)
