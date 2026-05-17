"""
Manifest types and helpers for the unified pipeline.

Each stage enriches ManifestEntry in-place; downstream stages consume what
upstream stages wrote. Types are grouped by pipeline stage:

  scan → link → dedupe → reconcile → group → emit
"""

from dataclasses import dataclass, field
from enum import Enum


class Status(Enum):
    PENDING = "pending"
    PROCESSED = "processed"
    SKIPPED = "skipped"
    ERROR = "error"


class DedupeResult(Enum):
    DELETE = "delete"
    KEEP = "keep"


class ApplyResult(Enum):
    WRITTEN = "written"
    COPIED = "copied"


@dataclass
class Source:
    # "album" or "loose" — from Takeout folder structure
    type: str

    # album name from the containing folder, None for loose files
    name: str | None = None


@dataclass
class SidecarMatch:
    # path to the matched Google Takeout .json sidecar file
    path: str

    # 3=exact, 2=name-only, 1=fuzzy — shown in CSV report
    confidence: int


@dataclass
class Geo:
    # signed decimal degrees
    latitude: float

    # signed decimal degrees
    longitude: float

    # meters above sea level, can be negative
    altitude: float | None = None


@dataclass
class Dedupe:
    # tracks progress through hash → resolve phases
    status: Status

    # whether to keep or discard this duplicate — drives can_keep()
    result: DedupeResult | None = None

    # SHA-256 digest for grouping identical files across albums
    hash: str | None = None

    # surfaced in CSV report when hashing fails
    error: str | None = None


@dataclass
class Metadata:
    # skipped when no handler exists for the file format
    status: Status

    # exiftool tag=value pairs, written to disk during apply
    write_tags: list[str] = field(default_factory=list)

    # all known dates in priority order — first entry drives rename path
    dates: list[str] = field(default_factory=list)

    # best available GPS — disk EXIF wins, sidecar as fallback
    geo: Geo | None = None

    # surfaced in CSV report — e.g. "No metadata handler for .mkv"
    error: str | None = None


@dataclass
class Apply:
    # tracks whether the copy/metadata write succeeded
    status: Status

    # whether exiftool tags were written or file was only copied
    result: ApplyResult | None = None

    # actual path on disk — may differ from rename on filename collision
    target_path: str | None = None

    # surfaced in CSV report
    error: str | None = None


@dataclass
class ManifestEntry:
    # absolute path to the source media file
    media_path: str

    # album or loose — determines dedupe preference
    source: Source

    # matched Google Takeout JSON sidecar — provides timestamps and geo for reconcile
    sidecar: SidecarMatch | None = None

    # content hash and keep/delete decision — gates all downstream stages
    dedupe: Dedupe | None = None

    # disk vs sidecar diff — carries write_tags for emit and dates for grouping
    metadata: Metadata | None = None

    # final outcome — copied/written result and actual disk path
    apply: Apply | None = None

    # uuid4 hex shared by group members (Live Photo, Motion Photo, edited variant)
    group_id: str | None = None

    def can_keep(self) -> bool:
        """
        Returns True if the entry should be processed (not deleted or errored during dedupe).

        When dedupe was skipped, the dedupe field is None, so the entry is kept.
        """
        if self.dedupe is None:
            return True
        return self.dedupe.result != DedupeResult.DELETE and self.dedupe.status != Status.ERROR
