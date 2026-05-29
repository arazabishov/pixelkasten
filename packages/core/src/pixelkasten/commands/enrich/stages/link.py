"""
Link working-library media to records — the enrich pipeline's matching stage.

Mirrors `commands/ingest/stages/link.py` in shape: consumes the typed
buckets returned by `scan` and produces the shared `EnrichState` that
downstream stages (`geocode`, `embed`) populate. Unlike ingest's link, the
matching is fully deterministic — a media file's record path is
mechanically derived from its filename — so there is no scoring or
algorithm here, just structural matching.
"""

import os

from pixelkasten.commands.enrich.state import EnrichEntry, EnrichState
from pixelkasten.handlers import SUPPORTED_EXTENSIONS
from pixelkasten.utils.record import record_path


def link(raw_library: dict, library: str) -> EnrichState:
    """Match supported media with records; surface unmatched files on both sides.

    Returns the shared `EnrichState` with `entries` populated and the report
    fields (`unmatched_media`, `unmatched_records`, `unsupported_media`)
    filled in. Per-entry outcomes stay unset until `geocode` and `embed`
    record them.
    """
    state = EnrichState(unsupported_media=list(raw_library["files_other_ignored"]))
    records_remaining = set(raw_library["files_records"])

    for media_path in raw_library["files_media"]:
        extension = os.path.splitext(media_path)[1].lower()
        record_file = record_path(library, os.path.basename(media_path))

        if extension not in SUPPORTED_EXTENSIONS:
            state.unsupported_media.append(media_path)
        elif record_file in records_remaining:
            records_remaining.discard(record_file)
            state.entries.append(EnrichEntry(media=media_path, record=record_file))
        else:
            state.unmatched_media.append(media_path)

    state.unmatched_records = sorted(records_remaining)
    return state
