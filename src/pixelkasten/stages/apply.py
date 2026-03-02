"""
Apply stage — copy files to destination and optionally embed metadata.

Ported from packages/core/src/stages/apply.js.
"""

import os
import shutil
from collections.abc import Callable

from pixelkasten.core.exiftool import write_metadata
from pixelkasten.core.manifest import can_keep


def apply(
    manifest: list[dict],
    options: dict | None = None,
    on_progress: Callable[[int], None] | None = None,
) -> None:
    """
    Copy files to destination, embed metadata if write_tags exist.

    For each file that is not marked for deletion:
    1. Copy to target path (from rename stage, or original filename if skipped)
    2. Embed metadata tags into the copy (if any tags to write)

    The source directory is never modified.

    Mutates entries in-place, adding entry["apply"] with status and targetPath.

    Options:
        destination (str): required -- root destination directory
        skip_embed (bool): if True, copy sidecar instead of embedding
    """
    options = options or {}
    destination = options.get("destination", "")

    keepers = [e for e in manifest if can_keep(e)]
    if not keepers:
        return

    for i, entry in enumerate(keepers):
        try:
            # Resolve destination path: use rename targetPath or fall back to original filename
            target_path = entry.get("rename", {}).get("targetPath") or os.path.basename(
                entry["mediaPath"]
            )
            dest_path = os.path.join(destination, target_path)

            # Ensure directory exists
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)

            # Copy file to destination
            shutil.copy2(entry["mediaPath"], dest_path)

            # Embed metadata if write_tags exist
            write_tags = entry.get("metadata", {}).get("writeTags", [])
            if write_tags:
                write_metadata(dest_path, write_tags)
                entry["apply"] = {
                    "status": "embedded",
                    "targetPath": dest_path,
                }
            else:
                entry["apply"] = {
                    "status": "copied",
                    "targetPath": dest_path,
                }

            # Copy sidecar when embedding is skipped and a sidecar exists
            if options.get("skip_embed") and entry.get("json", {}).get("path"):
                shutil.copy2(entry["json"]["path"], dest_path + ".json")

        except Exception as e:
            entry["apply"] = {
                "status": "error",
                "reason": str(e),
            }
        if on_progress is not None:
            on_progress(i + 1)
