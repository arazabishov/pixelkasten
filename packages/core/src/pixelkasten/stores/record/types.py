"""The Record model — typed view of a ``.pk.json`` record.

Split from ``record.py`` so a module that needs only the type can import it
without pulling in the file I/O.

``Record`` is the single source of truth for an asset's persisted state.
``to_dict`` serializes the model directly (no shadow copy of the raw JSON),
so setting an attribute is all a writer needs. The import-time core
(``dates``, ``geo``, ``album``, ``group_id``) is always emitted; the
enrichment fields are omitted until set, preserving the schema's "fields can
be absent" contract that consumers rely on.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class Record:
    """Typed view of a ``.pk.json`` record — the asset's persisted state."""

    # absolute path of the .pk.json file this record reads from / writes to
    path: str

    # ordered ISO dates; may be empty or include filesystem-date fallbacks
    dates: list[str] = field(default_factory=list)

    # signed decimal latitude/longitude/altitude, or None
    geo: dict[str, float] | None = None

    # Takeout album or immediate archive parent folder name; None for loose files
    album: str | None = None

    # uuid4 hex shared by every file of one logical asset
    group_id: str | None = None

    # reverse-geocoded city/region/country, set by enrich
    location: dict[str, str] | None = None

    # one-line VLM description, set by caption
    caption: str | None = None

    # album the agent chose, set by propose
    proposed_album: str | None = None

    @classmethod
    def from_dict(cls, path: str, raw: dict[str, Any]) -> Record:
        return cls(
            path=path,
            dates=list(raw.get("dates") or []),
            geo=raw.get("geo"),
            album=raw.get("album"),
            group_id=raw.get("group_id"),
            location=raw.get("location"),
            caption=raw.get("caption"),
            proposed_album=raw.get("proposed_album"),
        )

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "dates": self.dates,
            "geo": self.geo,
            "album": self.album,
            "group_id": self.group_id,
        }

        if self.location is not None:
            data["location"] = self.location
        if self.caption is not None:
            data["caption"] = self.caption
        if self.proposed_album is not None:
            data["proposed_album"] = self.proposed_album

        return data

    def require_group_id(self) -> str:
        """Return ``group_id``, raising when it's absent.

        Every record `import` emits carries a ``group_id`` (the group stage
        assigns one to each keeper, even singletons). The field is only ever
        ``None`` for a malformed or pre-1.0 record — so consumers that bucket
        by group fail loudly here rather than silently fabricating a key.
        """
        if not self.group_id:
            raise RuntimeError(f"Record at {self.path} has no group_id (malformed or pre-1.0)")
        return self.group_id

    def first_date(self) -> datetime:
        """Return the primary recorded date, raising when it is missing or invalid.

        Import can leave ``dates`` empty when no usable native metadata,
        sidecar, or filesystem date is available. Export requires a primary
        date for naming, so missing dates fail loudly rather than creating
        an undated fallback. Filesystem dates are not confirmed capture dates.
        """
        if not self.dates:
            raise RuntimeError(f"Record at {self.path} has no dates")
        return datetime.fromisoformat(self.dates[0])
