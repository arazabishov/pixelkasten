"""
Enrich command — geocode and CLIP-embed assets in a working library.

The command runs a linear pipeline of stages:

    scan -> geocode -> embed

Both stages are idempotent: re-running an enriched library is a no-op.
Failures for individual media files are reported in the result and the run
continues.
"""

from collections.abc import Callable
from contextlib import contextmanager

from pixelkasten.commands.enrich.state import EnrichState
from pixelkasten.commands.enrich.stages.embed import embed
from pixelkasten.commands.enrich.stages.geocode import geocode
from pixelkasten.commands.enrich.stages.scan import scan
from pixelkasten.configuration import EnrichOptions


@contextmanager
def _noop_progress(_label: str, _total: int):
    """Fallback progress factory used when none is supplied."""

    def _tick(_completed: int) -> None:
        pass

    yield _tick


def enrich(options: EnrichOptions, progress: Callable | None = None) -> EnrichState:
    """Geocode + embed all assets in the working library; return counts."""
    library = options.library
    progress = progress or _noop_progress

    # Discover working-library records and media.
    raw_library = scan(library)
    records, media = raw_library["records"], raw_library["media"]
    unsupported = raw_library["unsupported"]

    # Initialize the shared state from scan totals before stages add their counts.
    state = EnrichState(records_total=len(records), unsupported_media=unsupported)

    # Reverse-geocode records that have coordinates but no location.
    geocode(records, state, progress)

    # CLIP-embed media files that are not already present in the embedding store.
    embed(library, media, state, options.video_frames, progress)

    return state
