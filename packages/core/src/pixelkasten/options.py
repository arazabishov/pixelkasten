"""Pipeline configuration — single source of truth for all pipeline options."""

from dataclasses import dataclass


@dataclass
class CatalogOptions:
    clip_model: str
    batch_size: int
    min_cluster_size: int
    classify_threshold: float
    caption_model: str
    organize_model: str
    skip_caption: bool
    skip_refine: bool


@dataclass
class PipelineOptions:
    source: str
    destination: str | None
    takeout: bool
    dry_run: bool
    skip_dedupe: bool
    skip_embed: bool
    skip_rename: bool
    prefer: str
    fuzzy: bool
    fuzzy_threshold: int
    rescan: bool
    workspace: str | None
    catalog: CatalogOptions | None
