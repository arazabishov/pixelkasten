"""
Apply stage — copy files to destination and optionally write metadata.

Ported from packages/core/src/stages/apply.js.
"""

import os
import shutil
from collections.abc import Callable

from pixelkasten.tools.exiftool import write_metadata
from pixelkasten.manifest import Apply, ApplyResult, ManifestEntry, Status
from pixelkasten.configuration import Options


def apply(
    manifest: list[ManifestEntry],
    options: Options,
    on_progress: Callable[[int], None] | None = None,
) -> None:
    """
    Copy files to destination, write metadata if write_tags exist.

    For each file that is not marked for deletion:
    1. Copy to target path (from rename stage, or original filename if skipped)
    2. Write metadata tags into the copy (if any tags to write)

    The source directory is never modified.

    Mutates entries in-place, setting entry.apply.
    """
    if options.destination is None:
        raise ValueError("destination is required for apply")
    destination = options.destination

    keepers = [e for e in manifest if e.can_keep()]
    if not keepers:
        return

    for i, entry in enumerate(keepers):
        try:
            entry.apply = _apply_entry(entry, destination, options)
        except Exception as e:
            entry.apply = Apply(status=Status.ERROR, error=str(e))
        if on_progress is not None:
            on_progress(i + 1)


def _apply_entry(entry: ManifestEntry, destination: str, options: Options) -> Apply:
    """Copy a single file to destination, write metadata if needed."""
    target_path = (entry.rename.target_path if entry.rename else None) or os.path.basename(
        entry.media_path
    )
    dest_path = os.path.join(destination, target_path)

    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    shutil.copy2(entry.media_path, dest_path)

    write_tags = entry.metadata.write_tags if entry.metadata else []
    if write_tags:
        write_metadata(dest_path, write_tags)

    # Copy sidecar when metadata writing is skipped and a sidecar exists
    if options.skip_metadata_write and entry.sidecar:
        shutil.copy2(entry.sidecar.path, dest_path + ".json")

    return Apply(
        status=Status.PROCESSED,
        result=ApplyResult.WRITTEN if write_tags else ApplyResult.COPIED,
        target_path=dest_path,
    )
