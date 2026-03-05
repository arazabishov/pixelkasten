"""Shared test utilities."""

from pixelkasten.core.options import PipelineOptions


def make_options(**overrides) -> PipelineOptions:
    """Build PipelineOptions with test defaults. Override any field via kwargs."""
    defaults = {
        "source": "/src",
        "destination": "/dest",
        "takeout": False,
        "catalog": False,
        "dry_run": False,
        "skip_dedupe": False,
        "skip_embed": False,
        "skip_rename": False,
        "skip_caption": False,
        "skip_refine": False,
        "prefer": "album",
        "fuzzy": True,
        "fuzzy_threshold": 40,
        "rescan": False,
        "workspace": None,
        "clip_model": "ViT-L-14",
        "batch_size": 32,
        "min_cluster_size": 5,
        "classify_threshold": 0.15,
        "caption_model": "llava",
        "organize_model": "qwen3.5:35b",
        "progress": None,
    }
    defaults.update(overrides)
    return PipelineOptions(**defaults)
