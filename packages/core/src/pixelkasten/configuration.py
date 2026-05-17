"""
Pipeline configuration — option dataclasses for each command, plus the
constants that pin a working library's on-disk layout.
"""

from dataclasses import dataclass


# Working-library directory + file names. Every reader and writer of the
# working library goes through ``utils/library.py`` (path helpers) and
# ``utils/record.py`` (I/O), which reference these constants.
RECORDS_DIR = ".pixelkasten"
RECORD_SUFFIX = ".pk.json"
EMBEDDINGS_NPY = "embeddings.npy"
EMBEDDINGS_PATHS_JSON = "embeddings.paths.json"


@dataclass
class IngestOptions:
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
