"""
Metadata reconciliation -- compare disk EXIF with sidecar data.

Ported from packages/core/src/stages/reconcile.js. For each manifest entry,
reads the disk EXIF via exiftool and compares with sidecar data. Queues
writeTags for any metadata missing from disk.
"""

import os
from collections.abc import Callable

from pixelkasten.core.datetime import parse_photo_taken_time
from pixelkasten.core.exiftool import read_metadata
from pixelkasten.core.handlers import handlers
from pixelkasten.core.manifest import can_keep
from pixelkasten.core.sidecar import read_sidecar

BATCH_SIZE = 512


def reconcile(
    manifest: list[dict],
    options: dict | None = None,
    on_progress: Callable[[int], None] | None = None,
) -> None:
    """
    Compare disk EXIF with sidecar data, queue writeTags for missing metadata.

    Mutates manifest entries in-place by adding 'metadata' dict with:
        status: "noop" | "processed" | "skipped" | "error"
        writeTags: list[str] -- exiftool tag=value pairs
        dates: list[str] -- ISO 8601 timestamps
        reason: str -- (only for skipped/error)

    Processes entries in batches of 512 for efficient exiftool invocation.
    """
    options = options or {}

    keepers = [e for e in manifest if can_keep(e)]
    if not keepers:
        return

    # Collect all tags required by all handlers (deduplicated).
    all_tags = list({tag for h in handlers.values() for tag in h.read_tags})

    # Process in batches to prevent OOM with large manifests.
    for offset in range(0, len(keepers), BATCH_SIZE):
        batch = keepers[offset : offset + BATCH_SIZE]
        batch_paths = [e["mediaPath"] for e in batch]

        raw_metadata = read_metadata(batch_paths, all_tags)

        for entry in batch:
            raw_disk_tags = raw_metadata.get(entry["mediaPath"])
            json_path = None
            if entry.get("json"):
                json_path = entry["json"].get("path")

            try:
                entry["metadata"] = _resolve(
                    entry["mediaPath"], json_path, raw_disk_tags, options
                )
            except Exception as e:
                entry["metadata"] = {
                    "status": "error",
                    "reason": str(e),
                    "writeTags": [],
                    "dates": [],
                }

        if on_progress is not None:
            on_progress(min(offset + BATCH_SIZE, len(keepers)))


def _resolve(
    media_path: str,
    json_path: str | None,
    raw_disk_tags: dict | None,
    options: dict,
) -> dict:
    """Resolve metadata for a single entry."""
    ext = os.path.splitext(media_path)[1].lower()
    handler = handlers.get(ext)

    # If there is no handler for a file type, skip it.
    if not handler:
        return {
            "status": "skipped",
            "reason": f"No metadata handler for {ext}",
            "writeTags": [],
            "dates": [],
        }

    # If exiftool has not reported on a file, something went wrong.
    if raw_disk_tags is None:
        raise RuntimeError(f"ExifTool did not report on {media_path}")

    # Normalize raw, file-type-specific tags to a common shape.
    disk_data = handler.parse(raw_disk_tags)

    metadata: dict = {
        "status": "noop",
        "writeTags": [],
        "dates": list(disk_data.dates),
    }

    # Retrieve and parse sidecar data.
    sidecar_data = read_sidecar(json_path)

    # If there is no sidecar data, there is nothing to resolve.
    if not sidecar_data:
        return metadata

    # If there is no primary timestamp on disk, use the value from sidecar.
    if not disk_data.timestamp and sidecar_data.get("timestamp"):
        ptt = parse_photo_taken_time(sidecar_data["timestamp"])

        # Queue timestamp for writing if embedding is enabled.
        if not options.get("skip_embed"):
            metadata["writeTags"].extend(handler.timestamp(ptt["exif"]))

        # Make sure that timestamp is stored as the primary date (needed for rename).
        metadata["dates"].insert(0, ptt["iso"])

    # Queue geo data for writing if embedding is enabled.
    if not options.get("skip_embed") and not disk_data.geo and sidecar_data.get("geo"):
        metadata["writeTags"].extend(handler.geo(sidecar_data["geo"]))

    if metadata["writeTags"]:
        metadata["status"] = "processed"

    return metadata
