"""
Enrich command — geocode and CLIP-embed assets in a working library.

The command runs a linear pipeline of stages:

    geocode -> embed

Both stages are idempotent: re-running an enriched library is a no-op.
Failures for individual media files are reported in the result and the run
continues.
"""

import os
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field

from pixelkasten.commands.enrich.stages.embed import embed
from pixelkasten.commands.enrich.stages.geocode import geocode
from pixelkasten.configuration import EnrichOptions, RECORDS_DIR
from pixelkasten.utils.record import records_dir


@dataclass
class EnrichResult:
    """End-of-run counts from the `enrich` command."""

    # total records walked across the working library
    records_total: int = 0

    # records that gained a `location` field this run
    locations_added: int = 0

    # records skipped because `location` was already set
    locations_already_set: int = 0

    # images that gained an embedding this run
    images_embedded: int = 0

    # videos that gained an embedding this run
    videos_embedded: int = 0

    # images skipped because their filename is already in embeddings.paths.json
    images_already_embedded: int = 0

    # videos skipped because their filename is already in embeddings.paths.json
    videos_already_embedded: int = 0

    # absolute paths of images that failed to embed (corrupt, decode error)
    images_failed: list[str] = field(default_factory=list)

    # absolute paths of videos that failed to embed (ffmpeg / CLIP failure)
    videos_failed: list[str] = field(default_factory=list)


@contextmanager
def _noop_progress(_label: str, _total: int):
    """Fallback progress factory used when none is supplied."""

    def _tick(_completed: int) -> None:
        pass

    yield _tick


def enrich(options: EnrichOptions, progress: Callable | None = None) -> EnrichResult:
    """Geocode + embed all assets in the working library; return counts."""
    library = options.library
    rdir = records_dir(library)

    if not os.path.isdir(rdir):
        raise RuntimeError(
            f"Not a working library (missing {RECORDS_DIR}/ at {library}). "
            "Run `pixelkasten import` first."
        )

    progress = progress or _noop_progress
    geocode_result = geocode(library, progress)
    embed_result = embed(library, options.video_frames, progress)

    return EnrichResult(
        records_total=geocode_result.records_total,
        locations_added=geocode_result.locations_added,
        locations_already_set=geocode_result.locations_already_set,
        images_embedded=embed_result.images_embedded,
        videos_embedded=embed_result.videos_embedded,
        images_already_embedded=embed_result.images_already_embedded,
        videos_already_embedded=embed_result.videos_already_embedded,
        images_failed=embed_result.images_failed,
        videos_failed=embed_result.videos_failed,
    )
