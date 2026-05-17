"""
Group stage — assign a shared group_id to logical asset groups.

Takeout mode buckets by the matched Takeout sidecar path: Live Photo image
+ video, edited variants, and Motion Photos all share a sidecar in Google
Takeout, so they end up in the same bucket. Archive mode buckets by
(directory, stripped_stem) since there's no sidecar to key on.

Each bucket gets a fresh uuid4 hex; emit uses it as the filename stem so
group members share a stem and differ only in extension.
"""

import os
import uuid

from pixelkasten.configuration import Options
from pixelkasten.manifest import ManifestEntry
from pixelkasten.stages.link import stripped_stem


def group(manifest: list[ManifestEntry], options: Options) -> None:
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


def _bucket_takeout(keepers: list[ManifestEntry]) -> dict[object, list[ManifestEntry]]:
    """Bucket by sidecar.path; sidecar-less keepers each get their own bucket."""
    buckets: dict[object, list[ManifestEntry]] = {}
    for entry in keepers:
        key = entry.sidecar.path if entry.sidecar else id(entry)
        buckets.setdefault(key, []).append(entry)
    return buckets


def _bucket_archive(keepers: list[ManifestEntry]) -> dict[object, list[ManifestEntry]]:
    """Bucket by (dirname, stripped_stem) so siblings of one logical asset group together."""
    buckets: dict[object, list[ManifestEntry]] = {}
    for entry in keepers:
        key = (os.path.dirname(entry.media_path), stripped_stem(entry.media_path))
        buckets.setdefault(key, []).append(entry)
    return buckets
