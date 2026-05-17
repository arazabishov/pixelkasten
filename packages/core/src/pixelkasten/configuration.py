"""Pipeline configuration — options, hooks, summaries, and other shared types."""

from collections.abc import Callable
from dataclasses import dataclass, field


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


@dataclass
class ExportOptions:
    # overwrite the destination directory if it already exists
    force: bool = False

    # print planned operations without copying
    dry_run: bool = False


@dataclass
class ExportSummary:
    """End-of-run counts from the `export` command."""

    # destination directory the export was written to
    destination: str

    # total files exported (or that would have been exported on dry_run)
    total: int

    # files with no parseable date — landed at the destination root
    undated: int

    # True when the run was a dry-run (no files copied)
    dry_run: bool


@dataclass
class EnrichOptions:
    # path to the working library (contains .pixelkasten/)
    library: str

    # frames sampled per video for both embed and caption
    video_frames: int = 5


@dataclass
class EnrichSummary:
    """End-of-run counts from the `enrich` command.

    Populated by ``commands.enrich.enrich`` and rendered by
    ``pixelkasten_cli.reports.render_enrich_summary``. Per-file failure
    paths are also recorded so the renderer can show a sample inline.
    """

    # total records walked across the working library
    records_total: int = 0

    # records that gained a `location` field this run
    locations_added: int = 0

    # records skipped because `location` was already set
    locations_already_set: int = 0

    # images that gained an embedding this run
    images_embedded: int = 0

    # videos that gained an embedding this run
    videos_embedded: int = 0

    # files skipped because their embedding was already in embeddings.npy
    already_embedded: int = 0

    # absolute paths of images that failed to embed (corrupt, decode error)
    images_failed: list[str] = field(default_factory=list)

    # absolute paths of videos that failed to embed (ffmpeg / CLIP failure)
    videos_failed: list[str] = field(default_factory=list)


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
