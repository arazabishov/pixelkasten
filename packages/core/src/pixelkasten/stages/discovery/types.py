"""Types local to the discovery sub-pipeline — not exposed to the main pipeline."""

from dataclasses import dataclass, field

from pixelkasten.core.types import ManifestEntry, Status


@dataclass
class Tag:
    name: str
    score: float


@dataclass
class DiscoveryEntry:
    entry: ManifestEntry
    status: Status = Status.PENDING
    cluster: int | None = None
    is_representative: bool = False
    tags: list[Tag] = field(default_factory=list)
    caption: str | None = None
    error: str | None = None
