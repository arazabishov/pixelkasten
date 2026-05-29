"""Apply pending changes from enrich stages to disk.

Mirrors `commands/ingest/stages/emit.py`: the stages above stay pure (they
record outcomes on each entry), and this stage is the single place the
working library is mutated. `--dry-run` skips it, leaving the library
untouched. Each run overwrites prior output rather than merging with it —
enrich re-derives everything from scratch every run.
"""

import os
from collections.abc import Callable

import numpy as np

from pixelkasten.commands.enrich.state import EnrichState
from pixelkasten.pipeline import Status
from pixelkasten.utils.embeddings import write_embeddings
from pixelkasten.utils.record import read_record, write_record


def emit(library: str, state: EnrichState, progress: Callable) -> None:
    """Write geocoded locations into records, then overwrite the embeddings store."""
    # Merge each geocoded location into its record.
    with progress("Writing locations", len(state.entries)) as tick:
        for i, entry in enumerate(state.entries):
            if entry.location is not None:
                # Intentional second read (geocode read this for geo): enrich updates records
                # that other commands also write (caption, proposed_album), so we work from the
                # current on-disk version rather than carry a dict that could clobber their fields.
                data = read_record(entry.record)
                data["location"] = entry.location
                write_record(entry.record, data)
            tick(i + 1)

    # Overwrite the embeddings store with this run's successful embeddings. Skipped
    # when empty (no entries, or all failed per-item — a hard CLIP failure aborts
    # upstream); np.vstack([]) would raise, and we won't clobber a good store with nothing.
    embeddings: list[np.ndarray] = []
    names: list[str] = []
    for e in state.entries:
        embed = e.embed
        if embed and embed.status == Status.PROCESSED and embed.embedding is not None:
            embeddings.append(embed.embedding)
            names.append(os.path.basename(e.media))

    if embeddings:
        write_embeddings(library, np.vstack(embeddings).astype(np.float32), names)
