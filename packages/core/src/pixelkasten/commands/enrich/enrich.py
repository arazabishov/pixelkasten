"""
Enrich command — geocode and CLIP-embed assets in a working library.

The command runs a linear pipeline of stages:

    read -> geocode -> embed -> emit

Stages above `emit` are pure: they record their outcome on each entry and
never touch the working library. `emit` is the single point of disk mutation,
mirroring ingest's shape. `--dry-run` skips `emit` and returns the state so
callers can inspect what *would* be written.

Each run is a full run: geocode and embed recompute from scratch and `emit`
overwrites prior output — there is no resume or skip-if-already-done.
Per-media failures are recorded on the entry and the run continues.
"""

from collections.abc import Callable

from pixelkasten.commands.enrich.state import EnrichEntry, EnrichState
from pixelkasten.commands.enrich.stages.embed import embed
from pixelkasten.commands.enrich.stages.emit import emit
from pixelkasten.commands.enrich.stages.geocode import geocode
from pixelkasten.configuration import EnrichOptions
from pixelkasten.utils.library import read_library
from pixelkasten.utils.progress import noop_progress


def enrich(options: EnrichOptions, progress: Callable = noop_progress) -> EnrichState:
    """Geocode + embed all assets in the working library; return the state."""
    library = options.library

    # Read the working library: pair each supported media file with its record.
    raw_library = read_library(library)

    # Initialize the command state
    state = EnrichState(
        entries=[EnrichEntry(media=media, record=record) for media, record in raw_library["entries"]],
        unmatched_media=raw_library["unmatched_media"],
        unmatched_records=raw_library["unmatched_records"],
        unsupported_media=raw_library["unsupported_media"],
    )

    # Record a `location` on every entry whose record has geo coordinates.
    geocode(state, progress)

    # Compute an embedding for every entry; record it (or the failure) on the entry.
    embed(state, options.video_frames, progress)

    if not options.dry_run:
        # Single point of disk mutation: write locations into records, save embeddings.
        emit(library, state, progress)

    return state
