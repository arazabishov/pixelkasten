"""State types for the export command."""

from dataclasses import dataclass, field
from datetime import datetime

from pixelkasten.stores.record.types import Record


@dataclass
class ExportEntry:
    """One working-library media file paired with its record.

    `plan` reads typed fields from `record` and sets `target` (the relative
    destination path); `emit` copies `media` to `target`.
    """

    # top-level media file in the working library
    media: str

    # parsed .pk.json record for the media file
    record: Record

    # relative destination path, set by `plan` (None until planned)
    target: str | None = None


@dataclass
class Group:
    """One logical asset's files — an HEIC and its .mov / -edited variant share a
    group_id — that export into a single album together. Owns the derived
    properties `plan` and `validate` resolve from a group: its album and its date.
    """

    # the shared group_id its members carry
    id: str

    # the member files, each paired with its record
    entries: list[ExportEntry]

    def target_album(self) -> str | None:
        """proposed_album wins; otherwise the import-time album; otherwise None."""
        proposed = next(
            (e.record.proposed_album for e in self.entries if e.record.proposed_album), None
        )
        if proposed:
            return proposed
        return next((e.record.album for e in self.entries if e.record.album), None)

    def min_date(self) -> datetime:
        """Earliest primary date across all members; raises if any is undated."""
        return min(e.record.first_date() for e in self.entries)


@dataclass
class Export:
    """Paired entries from the `read` stage that `plan` and `emit` act on."""

    # media paired with a record — the entries `plan` and `emit` act on
    entries: list[ExportEntry] = field(default_factory=list)

    def grouped(self) -> list[Group]:
        """Bucket entries into groups by group_id, so a logical asset's files
        (image + video, edited variants) export to one album together."""
        buckets: dict[str, list[ExportEntry]] = {}
        for entry in self.entries:
            buckets.setdefault(entry.record.require_group_id(), []).append(entry)
        return [Group(id=group_id, entries=entries) for group_id, entries in buckets.items()]


@dataclass
class ExportResult:
    """What the run produced: the destination and the planned (or executed) copies.

    The (src, dst) operations are the source of truth; counts shown to the user
    are derived from them in `render_export` — mirroring how ingest's manifest
    and enrich's entries carry the data and the renderer derives the totals.
    """

    destination: str
    operations: list[tuple[str, str]]
