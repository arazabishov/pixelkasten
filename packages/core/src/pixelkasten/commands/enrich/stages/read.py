"""Read the working library into enrich entries."""

from pixelkasten.commands.enrich.state import EnrichEntry, EnrichState
from pixelkasten.utils.library import read_library


def read(library: str) -> EnrichState:
    """Map the shared working-library walk (`read_library`) onto enrich's entry
    type; downstream stages fill each entry's `location` and `embed`.
    """
    scan = read_library(library)
    return EnrichState(
        entries=[EnrichEntry(media=media, record=record) for media, record in scan["entries"]],
        unmatched_media=scan["unmatched_media"],
        unmatched_records=scan["unmatched_records"],
        unsupported_media=scan["unsupported_media"],
    )
