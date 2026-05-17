"""Pipeline configuration — options, hooks, and other pipeline-level types."""

from collections.abc import Callable
from dataclasses import dataclass


def _noop(*args) -> None:
    pass


@dataclass
class Options:
    # root directory to scan
    source: str

    # output directory for processed files
    destination: str | None

    # "takeout" matches JSON sidecars; "archive" treats every media file as loose
    mode: str

    # preview changes without writing
    dry_run: bool

    # skip duplicate detection
    skip_dedupe: bool

    # skip writing metadata into files
    skip_metadata_write: bool

    # prefer "album" or "loose" when deduplicating (Takeout mode only)
    prefer: str

    # enable fuzzy sidecar matching
    fuzzy: bool

    # minimum filename length for fuzzy matching
    fuzzy_threshold: int

    # save manifest as JSON for debugging
    write_manifest: bool = False


@dataclass
class ApplyOptions:
    # overwrite the destination directory if it already exists
    force: bool = False

    # print planned operations without copying
    dry_run: bool = False


@dataclass
class EnrichOptions:
    # path to the working library (contains .pixelkasten/)
    library: str

    # opt-in bulk captioning (currently deferred to Phase 10)
    with_captions: bool = False

    # frames sampled per video for both embed and caption
    video_frames: int = 5


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

    # called after files are copied and tagged
    on_apply: Callable = _noop

    # called after error summary
    on_errors: Callable = _noop
