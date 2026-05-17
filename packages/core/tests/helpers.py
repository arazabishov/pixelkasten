"""Shared test utilities."""

from contextlib import nullcontext

from pixelkasten.configuration import IngestOptions


def noop_progress(label: str, total: int):
    """No-op progress context manager for tests."""
    return nullcontext()


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
