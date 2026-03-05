"""
Manifest types for the unified pipeline.

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
    KEEP = "keep"
    DELETE = "delete"


class ApplyResult(Enum):
    COPIED = "copied"
    EMBEDDED = "embedded"


@dataclass
class Source:
    type: str
    name: str | None = None


@dataclass
class Sidecar:
    path: str
    confidence: int


@dataclass
class Geo:
    latitude: float
    longitude: float
    altitude: float | None = None


@dataclass
class Dedupe:
    status: Status
    result: DedupeResult | None = None
    hash: str | None = None
    error: str | None = None


@dataclass
class Metadata:
    status: Status
    write_tags: list[str] = field(default_factory=list)
    dates: list[str] = field(default_factory=list)
    geo: Geo | None = None
    error: str | None = None


@dataclass
class Location:
    name: str
    region: str
    country: str


@dataclass
class Rename:
    status: Status
    target_path: str | None = None
    error: str | None = None


@dataclass
class Apply:
    status: Status
    result: ApplyResult | None = None
    target_path: str | None = None
    error: str | None = None


@dataclass
class ManifestEntry:
    media_path: str
    source: Source
    sidecar: Sidecar | None = None
    dedupe: Dedupe | None = None
    metadata: Metadata | None = None
    location: Location | None = None
    rename: Rename | None = None
    apply: Apply | None = None
