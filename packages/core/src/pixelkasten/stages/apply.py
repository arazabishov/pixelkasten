"""
Apply stage — copy files to destination and optionally embed metadata.

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
    Copy files to destination, embed metadata if write_tags exist.

    For each file that is not marked for deletion:
    1. Copy to target path (from rename stage, or original filename if skipped)
    2. Embed metadata tags into the copy (if any tags to write)

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
            # Resolve destination path: use rename target_path or fall back to original filename
            target_path = (entry.rename.target_path if entry.rename else None) or os.path.basename(
                entry.media_path
            )
            dest_path = os.path.join(destination, target_path)

            # Ensure directory exists
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)

            # Copy file to destination
            shutil.copy2(entry.media_path, dest_path)

            # Embed metadata if write_tags exist
            write_tags = entry.metadata.write_tags if entry.metadata else []
            if write_tags:
                write_metadata(dest_path, write_tags)
                entry.apply = Apply(
                    status=Status.PROCESSED,
                    result=ApplyResult.EMBEDDED,
                    target_path=dest_path,
                )
            else:
                entry.apply = Apply(
                    status=Status.PROCESSED,
                    result=ApplyResult.COPIED,
                    target_path=dest_path,
                )

            # Copy sidecar when embedding is skipped and a sidecar exists
            if options.skip_embed and entry.sidecar:
                shutil.copy2(entry.sidecar.path, dest_path + ".json")

        except Exception as e:
            entry.apply = Apply(status=Status.ERROR, error=str(e))
        if on_progress is not None:
            on_progress(i + 1)
