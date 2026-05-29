"""
Enrich command — geocode and CLIP-embed assets in a working library.

The command runs a linear pipeline of stages:

    scan -> link -> geocode -> embed -> emit

Stages above `emit` are pure: they record their outcome on each entry and
never touch the working library. `emit` is the single point of disk
mutation, mirroring ingest's shape. `--dry-run` skips `emit` and returns the
state so callers can inspect what *would* be written.

Each run is a full run: geocode and embed recompute from scratch and `emit`
overwrites prior output — there is no resume or skip-if-already-done.
Per-media failures are recorded on the entry and the run continues.
"""

from collections.abc import Callable

from pixelkasten.commands.enrich.state import EnrichState
from pixelkasten.commands.enrich.stages.embed import embed
from pixelkasten.commands.enrich.stages.emit import emit
from pixelkasten.commands.enrich.stages.geocode import geocode
from pixelkasten.commands.enrich.stages.link import link
from pixelkasten.commands.enrich.stages.scan import scan
from pixelkasten.configuration import EnrichOptions
from pixelkasten.utils.progress import noop_progress


def enrich(options: EnrichOptions, progress: Callable = noop_progress) -> EnrichState:
    """Geocode + embed all assets in the working library; return the state."""
    library = options.library

    # Walk the working library and partition every file by type.
    raw_library = scan(library)

    # Match supported media with their records; surface unmatched files on both sides.
    state = link(raw_library, library)

    # Record a `location` on every entry whose record has geo coordinates.
    geocode(state, progress)

    # Compute an embedding for every entry; record it (or the failure) on the entry.
    embed(state, options.video_frames, progress)

    if not options.dry_run:
        # Single point of disk mutation: write locations into records, save embeddings.
        emit(library, state, progress)

    return state
