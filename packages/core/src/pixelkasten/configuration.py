"""Pipeline configuration — options, hooks, and other pipeline-level types."""

from collections.abc import Callable
from contextlib import nullcontext
from dataclasses import dataclass, field


def _noop(*args) -> None:
    pass


def _noop_progress(label: str, total: int):
    return nullcontext()


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
class Options:
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
    catalog: CatalogOptions | None


@dataclass
class Hooks:
    on_scan: Callable = field(default=_noop)
    on_link: Callable = field(default=_noop)
    on_dedupe: Callable = field(default=_noop)
    on_reconcile: Callable = field(default=_noop)
    on_rename: Callable = field(default=_noop)
    on_apply: Callable = field(default=_noop)
    on_errors: Callable = field(default=_noop)
