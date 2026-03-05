"""
Manifest types and helpers for the unified pipeline.

All TypedDict types that describe the shape of manifest entries live here.
Each stage enriches entries in-place; downstream stages consume what upstream
stages wrote. The types are grouped by pipeline stage.
"""

from __future__ import annotations

from typing import Literal, NotRequired, TypedDict


class SourceInfo(TypedDict):
    """Source classification — set by the link stage (or scan for non-takeout runs)."""

    type: Literal["album", "loose"]
    name: NotRequired[str]


class SidecarInfo(TypedDict):
    """Matched sidecar JSON — set by the link stage."""

    path: str
    confidence: int


class GeoInfo(TypedDict):
    """GPS coordinates — nested inside MetadataInfo."""

    latitude: float
    longitude: float
    altitude: NotRequired[float]


class MetadataInfo(TypedDict):
    """Reconciliation result — set by the reconcile stage."""

    status: Literal["noop", "processed", "skipped", "error"]
    writeTags: list[str]
    dates: list[str]
    geo: NotRequired[GeoInfo | None]
    reason: NotRequired[str]


class LocationInfo(TypedDict):
    """Geocoded location — set by reverse_geocode (moved from core/geocode.py)."""

    name: str
    region: str
    country: str


class DedupeInfo(TypedDict):
    """Deduplication result — set by dedupe_hash / dedupe_resolve."""

    hash: str | None
    status: Literal["pending", "keep", "delete", "error"]
    reason: NotRequired[str]


class RenameInfo(TypedDict):
    """Rename result — set by the rename stage."""

    status: Literal["processed", "error"]
    targetPath: NotRequired[str]
    reason: NotRequired[str]


class ApplyInfo(TypedDict):
    """Apply result — set by the apply stage."""

    status: Literal["embedded", "copied", "error"]
    targetPath: NotRequired[str]
    reason: NotRequired[str]


class TagInfo(TypedDict):
    """Zero-shot classification tag — set by catalog/classify."""

    name: str
    score: float


class ManifestEntry(TypedDict):
    """A single file tracked through the pipeline.

    Required fields (mediaPath, source) are set at entry creation (link stage
    for takeout, scan for plain archives). All other fields are added by downstream stages and marked
    NotRequired. Fields are ordered by pipeline stage:

      link → dedupe → reconcile → geocode → catalog → rename → apply
    """

    # link: absolute path to the media file
    mediaPath: str
    # link: source classification ("album" or "loose", with optional album name)
    source: SourceInfo
    # link: matched sidecar JSON file (path + match confidence), None if unmatched
    json: NotRequired[SidecarInfo | None]
    # dedupe: SHA-256 hash + keep/delete resolution
    dedupe: NotRequired[DedupeInfo]
    # reconcile: EXIF vs sidecar comparison — dates, GPS, and tags to write
    metadata: NotRequired[MetadataInfo]
    # geocode: reverse-geocoded GPS → city, region, country
    location: NotRequired[LocationInfo]
    # catalog/cluster: HDBSCAN cluster assignment (-1 = noise)
    cluster: NotRequired[int]
    # catalog/embed: whether embedding succeeded ("ok" or "failed")
    status: NotRequired[str]
    # catalog/cluster: whether this image represents its cluster centroid
    is_representative: NotRequired[bool]
    # catalog/classify: zero-shot CLIP classification tags with scores
    tags: NotRequired[list[TagInfo]]
    # catalog/caption: VLM-generated image description
    caption: NotRequired[str]
    # rename: computed target path relative to destination root
    rename: NotRequired[RenameInfo]
    # apply: file copy + metadata embedding result
    apply: NotRequired[ApplyInfo]


def can_keep(entry: dict) -> bool:
    """
    Returns True if the entry should be processed (not deleted or errored during dedupe).

    When dedupe was skipped, the dedupe key is absent, so the entry is kept.
    """
    dedupe = entry.get("dedupe")
    if dedupe is None:
        return True
    status = dedupe.get("status")
    return status != "delete" and status != "error"
