"""Mutable state shared by enrich stages."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from pixelkasten.pipeline import Status

if TYPE_CHECKING:
    import numpy as np


@dataclass
class Embed:
    """One media file's embedding outcome, set by the `embed` stage.

    Mirrors ingest's `Apply`/`Metadata`: a `status` plus the payload it
    produced and an `error` for the report. `PROCESSED` carries the
    `embedding`; `ERROR` carries the failure message.
    """

    status: Status
    embedding: np.ndarray | None = None
    error: str | None = None


@dataclass
class EnrichEntry:
    """One working-library media file paired with its record.

    Each stage records its outcome on the entry — `location` from geocode,
    `embed` from embed — so the run summary is derived from the entries
    rather than tracked in counters alongside them.
    """

    # top-level media file in the working library
    media: str

    # matching .pk.json record for the media file
    record: str

    # geocoded location dict (None = the record had no geo to geocode)
    location: dict | None = None

    # embedding outcome
    embed: Embed | None = None


@dataclass
class EnrichState:
    """Run state for the `enrich` command: the paired entries plus the files
    that never became entries. Per-entry outcomes live on `EnrichEntry`; the
    counts shown to the user are derived from `entries` at render time.
    """

    # paired (media, record) entries that the stages process
    entries: list[EnrichEntry] = field(default_factory=list)

    # supported media with no matching record
    unmatched_media: list[str] = field(default_factory=list)

    # records with no matching media file at the library root
    unmatched_records: list[str] = field(default_factory=list)

    # top-level visible files skipped because enrich does not support their format
    unsupported_media: list[str] = field(default_factory=list)
