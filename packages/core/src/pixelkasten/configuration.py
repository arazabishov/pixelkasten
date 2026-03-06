"""Pipeline configuration — options, hooks, and other pipeline-level types."""

from collections.abc import Callable
from dataclasses import dataclass


def _noop(*args) -> None:
    pass


@dataclass
class DiscoveryOptions:
    # CLIP model for image embeddings
    clip_model: str

    # Ollama vision model for captioning
    caption_model: str

    # Ollama text model for album naming
    organize_model: str

    # images per CLIP batch
    batch_size: int

    # smallest group HDBSCAN will form
    min_cluster_size: int

    # zero-shot classification confidence cutoff
    classify_threshold: float

    # skip VLM captioning
    skip_caption: bool

    # skip temporal cluster refinement
    skip_refine: bool


@dataclass
class Options:
    # root directory to scan
    source: str

    # output directory for processed files
    destination: str | None

    # AI album discovery sub-pipeline
    discovery: DiscoveryOptions | None

    # preview changes without writing
    dry_run: bool

    # skip duplicate detection
    skip_dedupe: bool

    # skip writing metadata into files
    skip_embed: bool

    # skip target path computation
    skip_rename: bool

    # prefer "album" or "loose" when deduplicating
    prefer: str

    # enable fuzzy sidecar matching
    fuzzy: bool

    # minimum filename length for fuzzy matching
    fuzzy_threshold: int


@dataclass
class Hooks:
    # called after directory scan
    on_scan: Callable = _noop

    # called after sidecar matching
    on_link: Callable = _noop

    # called after duplicates are resolved
    on_dedupe: Callable = _noop

    # called after reading disk metadata
    on_reconcile: Callable = _noop

    # called after target paths are set
    on_rename: Callable = _noop

    # called after files are copied and tagged
    on_apply: Callable = _noop

    # called after error summary
    on_errors: Callable = _noop
