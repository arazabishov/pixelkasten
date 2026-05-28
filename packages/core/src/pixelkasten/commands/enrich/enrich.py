"""
Enrich command — geocode and CLIP-embed assets in a working library.

The command runs a linear pipeline of stages:

    scan -> link -> geocode -> embed

Both stages are idempotent: re-running an enriched library is a no-op.
Failures for individual media files are reported in the result and the run
continues.
"""

from collections.abc import Callable

from pixelkasten.commands.enrich.state import EnrichState
from pixelkasten.commands.enrich.stages.embed import embed
from pixelkasten.commands.enrich.stages.geocode import geocode
from pixelkasten.commands.enrich.stages.link import link
from pixelkasten.commands.enrich.stages.scan import scan
from pixelkasten.configuration import EnrichOptions
from pixelkasten.utils.progress import noop_progress


def enrich(options: EnrichOptions, progress: Callable | None = None) -> EnrichState:
    """Geocode + embed all assets in the working library; return counts."""
    library = options.library
    progress = progress or noop_progress

    # Walk the working library and partition every file by type.
    raw_library = scan(library)

    # Pair supported media with their records; surface orphans on both sides.
    state = link(raw_library, library)

    # Reverse-geocode records that have coordinates but no location.
    geocode(state, progress)

    # CLIP-embed media files that are not already present in the embedding store.
    embed(library, state, options.video_frames, progress)

    return state
