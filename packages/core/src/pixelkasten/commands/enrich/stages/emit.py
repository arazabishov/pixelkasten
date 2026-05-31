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
from pixelkasten.stores.embeddings import write_embeddings
from pixelkasten.stores.record import write_record


def emit(library: str, state: EnrichState, progress: Callable) -> None:
    """Persist records geocode located, then overwrite the embeddings store."""
    # geocode set `location` on the record of every geo-bearing entry; persist those.
    located = [entry for entry in state.entries if entry.record.location is not None]
    with progress("Writing locations", len(located)) as tick:
        for i, entry in enumerate(located):
            write_record(entry.record)
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
