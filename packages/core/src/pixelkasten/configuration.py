"""Pipeline configuration — option dataclasses for each command."""

from dataclasses import dataclass


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
class EnrichOptions:
    # path to the working library (contains .pixelkasten/)
    library: str

    # frames sampled per video for both embed and caption
    video_frames: int = 5
