"""
Group stage — assign a shared group_id to logical asset groups.

Takeout mode buckets by the matched Takeout sidecar path: Live Photo image
+ video, edited variants, and Motion Photos all share a sidecar in Google
Takeout, so they end up in the same bucket.

Archive mode buckets by (directory, name) where name is the literal
basename-without-extension, with one sibling-gated exception: if the name
ends in ``-edited`` (or a truncated variant) AND an un-edited counterpart
exists in the same directory, use the un-edited form. No ``(N)`` stripping
— surviving ``(N)`` files have distinct content (dedupe collapsed
identical ones) and deserve their own group. Takeout content should use
``--from-takeout`` for robust pairing via sidecars; archive mode cannot
recover edits/Live-Photo siblings reliably when filenames alone don't
carry the signal (name truncation, collision-marker ambiguity).

Each bucket gets a fresh uuid4 hex written to entry.group_id. Emit gives
each file an independent uuid4 name; group membership lives only in the
record's group_id field, not in filenames.
"""

import os
import uuid

from pixelkasten.configuration import IngestOptions
from pixelkasten.manifest import ManifestEntry
from pixelkasten.commands.ingest.stages.link import _EDITED_SUFFIX_PATTERN


def group(manifest: list[ManifestEntry], options: IngestOptions) -> None:
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
    """Bucket by (directory, name) with sibling-evidence -edited stripping."""
    # Per-directory set of literal names used to gate the -edited strip below.
    base_names_by_directory: dict[str, set[str]] = {}
    for entry in keepers:
        dirname = os.path.dirname(entry.media_path)
        base_name = os.path.splitext(os.path.basename(entry.media_path))[0]
        base_names_by_directory.setdefault(dirname, set()).add(base_name)

    # With sibling names known, assign each entry to its (directory, name) bucket.
    buckets: dict[object, list[ManifestEntry]] = {}
    for entry in keepers:
        dirname = os.path.dirname(entry.media_path)
        base_name = os.path.splitext(os.path.basename(entry.media_path))[0]
        base_name_trimmed = _EDITED_SUFFIX_PATTERN.sub("", base_name)

        # Strip -edited only when an un-edited sibling exists in the same directory.
        if base_name_trimmed != base_name and base_name_trimmed in base_names_by_directory[dirname]:
            base_name = base_name_trimmed

        buckets.setdefault((dirname, base_name), []).append(entry)

    return buckets
