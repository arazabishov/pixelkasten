"""
Metadata reconciliation -- compare disk EXIF with sidecar data.

Ported from packages/core/src/stages/reconcile.js. For each manifest entry,
reads the disk EXIF via exiftool and compares with sidecar data. Queues
write_tags for any metadata missing from disk.
"""

import os
from collections.abc import Callable

from pixelkasten.configuration import IngestOptions
from pixelkasten.handlers import handlers
from pixelkasten.commands.ingest.state import Geo, IngestEntry, Metadata
from pixelkasten.pipeline import Status
from pixelkasten.utils.dates import parse_photo_taken_time
from pixelkasten.utils.exiftool import read_metadata
from pixelkasten.utils.progress import noop_progress
from pixelkasten.utils.sidecar import read_sidecar

BATCH_SIZE = 512


def reconcile(
    manifest: list[IngestEntry],
    options: IngestOptions,
    progress: Callable = noop_progress,
) -> None:
    """
    Compare disk EXIF with sidecar data, queue write_tags for missing metadata.

    Mutates manifest entries in-place by setting entry.metadata.
    Processes entries in batches of 512 for efficient exiftool invocation.
    """
    keepers = [e for e in manifest if e.can_keep()]
    if not keepers:
        return

    # Collect all tags required by all handlers (deduplicated).
    all_tags = list({tag for h in handlers.values() for tag in h.read_tags})

    with progress("Reading metadata", len(keepers)) as tick:
        # Process in batches to prevent OOM with large manifests.
        for offset in range(0, len(keepers), BATCH_SIZE):
            batch = keepers[offset : offset + BATCH_SIZE]
            batch_paths = [e.media_path for e in batch]

            raw_metadata = read_metadata(batch_paths, all_tags)

            for entry in batch:
                raw_disk_tags = raw_metadata.get(entry.media_path)
                json_path = entry.sidecar.path if entry.sidecar else None

                try:
                    entry.metadata = _resolve(entry.media_path, json_path, raw_disk_tags, options)
                except Exception as e:
                    entry.metadata = Metadata(status=Status.ERROR, error=str(e))

            tick(min(offset + BATCH_SIZE, len(keepers)))


def _resolve(
    media_path: str,
    json_path: str | None,
    raw_disk_tags: dict | None,
    options: IngestOptions,
) -> Metadata:
    """Resolve metadata for a single entry."""
    ext = os.path.splitext(media_path)[1].lower()
    handler = handlers.get(ext)

    # If there is no handler for a file type, skip it.
    if not handler:
        return Metadata(status=Status.SKIPPED, error=f"No metadata handler for {ext}")

    # If exiftool has not reported on a file, something went wrong.
    if raw_disk_tags is None:
        raise RuntimeError(f"ExifTool did not report on {media_path}")

    # Normalize raw, file-type-specific tags to a common shape.
    disk_data = handler.parse(raw_disk_tags)

    metadata = Metadata(
        status=Status.PROCESSED,
        dates=list(disk_data["dates"]),
        geo=_to_geo(disk_data["geo"]),
    )

    # Retrieve and parse sidecar data. If absent, nothing to resolve.
    sidecar_data = read_sidecar(json_path)
    if not sidecar_data:
        return metadata

    # If there is no primary timestamp on disk, use the value from sidecar.
    if not disk_data["timestamp"] and sidecar_data.get("timestamp"):
        ptt = parse_photo_taken_time(sidecar_data["timestamp"])

        # Queue timestamp for writing if metadata writing is enabled.
        if not options.skip_metadata_write:
            metadata.write_tags.extend(handler.timestamp(ptt["exif"]))

        # Make sure that timestamp is stored as the primary date (needed for rename).
        metadata.dates.insert(0, ptt["iso"])

    # Queue geo data for writing if metadata writing is enabled.
    if not options.skip_metadata_write and not disk_data["geo"] and sidecar_data.get("geo"):
        metadata.write_tags.extend(handler.geo(sidecar_data["geo"]))

    # Use sidecar geo if disk has none (for downstream geocoding).
    if not metadata.geo and sidecar_data.get("geo"):
        metadata.geo = _to_geo(sidecar_data["geo"])

    return metadata


def _to_geo(raw: dict | None) -> Geo | None:
    """Convert a raw geo dict to a typed Geo at the stage boundary."""
    if not raw:
        return None
    return Geo(latitude=raw["latitude"], longitude=raw["longitude"], altitude=raw.get("altitude"))
