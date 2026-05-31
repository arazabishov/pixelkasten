"""
Group stage — assign a shared group_id to logical asset groups.

Takeout mode buckets by the matched Takeout sidecar path: Live Photo image
+ video, edited variants, and Motion Photos all share a sidecar in Google
Takeout, so they end up in the same bucket.

Archive mode buckets by (directory, stem) where stem is the literal
basename-without-extension. Live Photo image+video and RAW+JPEG captures
group naturally via shared stem; edit pairs are not recognized in archive
mode because filename conventions like ``-edited`` don't generalize across
sources. Use ``--from-takeout`` for Takeout content to get edit pairing
via sidecars.

Each bucket gets a fresh uuid4 hex written to entry.group_id. Emit gives
each file an independent uuid4 stem; group membership lives only in the
record's group_id field, not in filenames.
"""

import os
import uuid

from pixelkasten.configuration import IngestOptions
from pixelkasten.commands.ingest.types import IngestEntry


def group(manifest: list[IngestEntry], options: IngestOptions) -> None:
    """Assign entry.group_id to every keeper in the manifest."""
    keepers = [e for e in manifest if e.can_keep()]
    if not keepers:
        return

    if options.mode == "archive":
        buckets = _bucket_archive(keepers)
    else:
        buckets = _bucket_takeout(keepers)

    for members in buckets.values():
        group_id = uuid.uuid4().hex
        for entry in members:
            entry.group_id = group_id


def _bucket_takeout(keepers: list[IngestEntry]) -> dict[object, list[IngestEntry]]:
    """Bucket by sidecar.path; sidecar-less keepers each get their own bucket."""
    buckets: dict[object, list[IngestEntry]] = {}
    for entry in keepers:
        key = entry.sidecar.path if entry.sidecar else id(entry)
        buckets.setdefault(key, []).append(entry)
    return buckets


def _bucket_archive(keepers: list[IngestEntry]) -> dict[object, list[IngestEntry]]:
    """Bucket by (directory, stem) — literal basename-without-extension."""
    buckets: dict[object, list[IngestEntry]] = {}
    for entry in keepers:
        name = os.path.splitext(os.path.basename(entry.media_path))[0]
        buckets.setdefault((os.path.dirname(entry.media_path), name), []).append(entry)
    return buckets
