"""Shared test utilities."""

from pixelkasten.configuration import CatalogOptions, Options


def make_options(**overrides) -> Options:
    """Build Options with test defaults. Override any field via kwargs."""
    defaults = {
        "source": "/src",
        "destination": "/dest",
        "dry_run": False,
        "skip_dedupe": False,
        "skip_embed": False,
        "skip_rename": False,
        "prefer": "album",
        "fuzzy": True,
        "fuzzy_threshold": 40,
        "catalog": None,
    }
    defaults.update(overrides)
    return Options(**defaults)


def make_catalog_options(**overrides) -> CatalogOptions:
    """Build CatalogOptions with test defaults."""
    defaults = {
        "clip_model": "ViT-L-14",
        "batch_size": 32,
        "min_cluster_size": 5,
        "classify_threshold": 0.15,
        "caption_model": "llava",
        "organize_model": "qwen3.5:35b",
        "skip_caption": False,
        "skip_refine": False,
    }
    defaults.update(overrides)
    return CatalogOptions(**defaults)
