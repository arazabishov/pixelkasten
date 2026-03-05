"""Manifest helpers for the unified pipeline."""

from pixelkasten.core.types import DedupeResult, ManifestEntry, Status


def can_keep(entry: ManifestEntry) -> bool:
    """
    Returns True if the entry should be processed (not deleted or errored during dedupe).

    When dedupe was skipped, the dedupe field is None, so the entry is kept.
    """
    if entry.dedupe is None:
        return True
    return entry.dedupe.result != DedupeResult.DELETE and entry.dedupe.status != Status.ERROR
