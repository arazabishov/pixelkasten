"""Emit: copy each planned entry to the destination — the single disk mutation."""

import os
import shutil

from pixelkasten.commands.export.state import ExportState
from pixelkasten.configuration import ExportOptions


def emit(state: ExportState, destination: str, options: ExportOptions) -> list[tuple[str, str]]:
    """Copy each entry's media to its planned target; return the (src, dst) ops.

    Refuses a non-empty destination unless ``force``. ``--dry-run`` returns the
    planned operations without touching disk.
    """
    if os.path.exists(destination) and os.listdir(destination) and not options.force:
        raise RuntimeError(
            f"Destination {destination} already exists and is not empty; pass --force to overwrite."
        )

    operations = [
        (e.media, os.path.join(destination, e.target))
        for e in state.entries
        if e.target is not None
    ]

    if not options.dry_run:
        if options.force and os.path.exists(destination):
            shutil.rmtree(destination)
        os.makedirs(destination, exist_ok=True)
        for src, dst in operations:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)

    return operations
