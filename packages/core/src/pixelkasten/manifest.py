"""
Manifest types and helpers for the unified pipeline.

Each stage enriches ManifestEntry in-place; downstream stages consume what
upstream stages wrote. Types are grouped by pipeline stage:

  link → dedupe → reconcile → [discover] → rename → apply
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
    EMBEDDED = "embedded"
    COPIED = "copied"


@dataclass
class Source:
    # "album" or "loose" — from Takeout folder structure
    type: str

    # album name from the containing folder, None for loose files
    name: str | None = None


@dataclass
class Sidecar:
    # path to the matched .json file
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
class Location:
    # city or place — used in album names by discovery
    name: str

    # state/province — used by refine to merge nearby clusters
    region: str

    # not used downstream yet, reserved for future grouping
    country: str


@dataclass
class Tag:
    # zero-shot classification label
    name: str

    # classification confidence
    score: float


@dataclass
class Rename:
    # tracks whether path resolution succeeded
    status: Status

    # date-based destination path — used by apply for the file copy
    target_path: str | None = None

    # surfaced in CSV report
    error: str | None = None


@dataclass
class Apply:
    # tracks whether the copy/embed succeeded
    status: Status

    # whether exiftool tags were embedded or file was only copied
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

    # matched JSON sidecar — provides timestamps and geo for reconcile
    sidecar: Sidecar | None = None

    # content hash and keep/delete decision — gates all downstream stages
    dedupe: Dedupe | None = None

    # disk vs sidecar diff — carries write_tags for apply, dates for rename
    metadata: Metadata | None = None

    # reverse-geocoded place — feeds album naming in discovery
    location: Location | None = None

    # date-based destination path — consumed by apply for file copy
    rename: Rename | None = None

    # final outcome — copied/embedded result and actual disk path
    apply: Apply | None = None

    def can_keep(self) -> bool:
        """
        Returns True if the entry should be processed (not deleted or errored during dedupe).

        When dedupe was skipped, the dedupe field is None, so the entry is kept.
        """
        if self.dedupe is None:
            return True
        return self.dedupe.result != DedupeResult.DELETE and self.dedupe.status != Status.ERROR


@dataclass
class DiscoveryEntry:
    # the underlying pipeline entry
    entry: ManifestEntry

    # tracks progress through discovery stages
    status: Status = Status.PENDING

    # HDBSCAN cluster assignment — None until clustering runs
    cluster: int | None = None

    # whether this entry represents its cluster in captioning
    is_representative: bool = False

    # zero-shot classification results from CLIP
    tags: list[Tag] = field(default_factory=list)

    # VLM-generated description of the image
    caption: str | None = None

    error: str | None = None
