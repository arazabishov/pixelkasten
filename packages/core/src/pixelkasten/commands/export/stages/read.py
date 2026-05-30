"""Read the working library into export entries."""

from pixelkasten.commands.export.state import ExportEntry, ExportState
from pixelkasten.utils.library import read_library


def read(library: str) -> ExportState:
    """Map the shared working-library walk (`read_library`) onto export's entry
    type. Record contents are read later, in `plan`, where the layout needs them.
    """
    scan = read_library(library)
    return ExportState(
        entries=[ExportEntry(media=media, record=record) for media, record in scan["entries"]],
        unmatched_media=scan["unmatched_media"],
        unmatched_records=scan["unmatched_records"],
        unsupported_media=scan["unsupported_media"],
    )
