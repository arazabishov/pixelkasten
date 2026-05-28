"""Shared test utilities."""

from pixelkasten.configuration import IngestOptions
from pixelkasten.utils.progress import noop_progress


__all__ = ["make_options", "noop_progress"]


def make_options(**overrides) -> IngestOptions:
    """Build IngestOptions with test defaults. Override any field via kwargs."""
    defaults = {
        "source": "/src",
        "destination": "/dest",
        "mode": "takeout",
        "dry_run": False,
        "skip_dedupe": False,
        "skip_metadata_write": False,
        "prefer": "album",
        "fuzzy": True,
        "fuzzy_threshold": 40,
    }
    defaults.update(overrides)
    return IngestOptions(**defaults)
