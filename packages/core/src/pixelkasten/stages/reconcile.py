"""
Metadata reconciliation -- compare disk EXIF with sidecar data.

Ported from packages/core/src/stages/reconcile.js. For each manifest entry,
reads the disk EXIF via exiftool and compares with sidecar data. Queues
write_tags for any metadata missing from disk.
"""

import os
from collections.abc import Callable

from pixelkasten.core.datetime import parse_photo_taken_time
from pixelkasten.core.exiftool import read_metadata
from pixelkasten.core.manifest import can_keep
from pixelkasten.core.types import Geo, ManifestEntry, Metadata, Status
from pixelkasten.handlers import handlers
from pixelkasten.configuration import Options
from pixelkasten.core.sidecar import read_sidecar

BATCH_SIZE = 512


def reconcile(
    manifest: list[ManifestEntry],
    options: Options,
    on_progress: Callable[[int], None] | None = None,
) -> None:
    """
    Compare disk EXIF with sidecar data, queue write_tags for missing metadata.

    Mutates manifest entries in-place by setting entry.metadata.
    Processes entries in batches of 512 for efficient exiftool invocation.
    """
    keepers = [e for e in manifest if can_keep(e)]
    if not keepers:
        return

    # Collect all tags required by all handlers (deduplicated).
    all_tags = list({tag for h in handlers.values() for tag in h.read_tags})

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

        if on_progress is not None:
            on_progress(min(offset + BATCH_SIZE, len(keepers)))


def _resolve(
    media_path: str,
    json_path: str | None,
    raw_disk_tags: dict | None,
    options: Options,
) -> Metadata:
    """Resolve metadata for a single entry."""
    ext = os.path.splitext(media_path)[1].lower()
    handler = handlers.get(ext)

    # If there is no handler for a file type, skip it.
    if not handler:
        return Metadata(
            status=Status.SKIPPED,
            error=f"No metadata handler for {ext}",
        )

    # If exiftool has not reported on a file, something went wrong.
    if raw_disk_tags is None:
        raise RuntimeError(f"ExifTool did not report on {media_path}")

    # Normalize raw, file-type-specific tags to a common shape.
    disk_data = handler.parse(raw_disk_tags)

    write_tags: list[str] = []
    dates = list(disk_data["dates"])
    raw_geo = disk_data["geo"]

    # Retrieve and parse sidecar data.
    sidecar_data = read_sidecar(json_path)

    # If there is sidecar data, resolve missing metadata.
    if sidecar_data:
        # If there is no primary timestamp on disk, use the value from sidecar.
        if not disk_data["timestamp"] and sidecar_data.get("timestamp"):
            ptt = parse_photo_taken_time(sidecar_data["timestamp"])

            # Queue timestamp for writing if embedding is enabled.
            if not options.skip_embed:
                write_tags.extend(handler.timestamp(ptt["exif"]))

            # Make sure that timestamp is stored as the primary date (needed for rename).
            dates.insert(0, ptt["iso"])

        # Queue geo data for writing if embedding is enabled.
        if not options.skip_embed and not disk_data["geo"] and sidecar_data.get("geo"):
            write_tags.extend(handler.geo(sidecar_data["geo"]))

        # Use sidecar geo if disk has none (for downstream geocoding).
        if not raw_geo and sidecar_data.get("geo"):
            raw_geo = sidecar_data["geo"]

    # Convert raw geo dict to typed Geo at the stage boundary.
    geo = (
        Geo(
            latitude=raw_geo["latitude"],
            longitude=raw_geo["longitude"],
            altitude=raw_geo.get("altitude"),
        )
        if raw_geo
        else None
    )

    return Metadata(
        status=Status.PROCESSED,
        write_tags=write_tags,
        dates=dates,
        geo=geo,
    )
