"""
Export a working library to a user-facing organized photo library.

Pipeline: ``read -> plan -> emit``. ``read`` pairs each media file with its
record (and reads its fields); ``plan`` resolves a date/album destination path
per entry via the fallback chain (proposed_album → album → year folder →
destination root for undated files); ``emit`` copies. Planning is pure; ``emit``
is the single disk mutation, so ``--dry-run`` skips the copy. The working
library is read-only here; re-running produces the same export deterministically.
"""

from pixelkasten.commands.export.stages.emit import emit
from pixelkasten.commands.export.stages.plan import plan
from pixelkasten.commands.export.state import ExportEntry, ExportResult, ExportState
from pixelkasten.configuration import ExportOptions
from pixelkasten.utils.library import read_library


def export(library: str, destination: str, options: ExportOptions) -> ExportResult:
    """Export ``library`` to ``destination``; return the planned/executed copies.

    Raises:
        FileNotFoundError if ``library`` is not a working library.
        RuntimeError if ``destination`` is non-empty and ``force`` is unset.
        RuntimeError if a group's members disagree on ``proposed_album``.
    """

    # Read the working library: pair each supported media file with its record.
    raw_library = read_library(library)

    # Initialize the command state
    state = ExportState(
        entries=[ExportEntry(media=media, record=record) for media, record in raw_library["entries"]],
        unmatched_media=raw_library["unmatched_media"],
        unmatched_records=raw_library["unmatched_records"],
        unsupported_media=raw_library["unsupported_media"],
    )

    plan(state)

    operations = emit(state, destination, options)

    return ExportResult(destination=destination, operations=operations)
