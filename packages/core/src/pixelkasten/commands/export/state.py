"""State types for the export command."""

from dataclasses import dataclass, field


@dataclass
class ExportEntry:
    """One working-library media file paired with its record.

    `read` sets the two paths; `plan` reads the record onto the middle fields
    (which drive the layout) and sets `target` (the relative destination path);
    `emit` copies `media` to `target`.
    """

    # top-level media file in the working library
    media: str

    # matching .pk.json record for the media file
    record: str

    # record fields the layout depends on, read onto the entry by `plan`
    dates: list[str] = field(default_factory=list)
    album: str | None = None
    proposed_album: str | None = None
    group_id: str | None = None

    # relative destination path, set by `plan` (None until planned)
    target: str | None = None


@dataclass
class ExportState:
    """Paired entries plus the files that didn't pair, from the `read` stage."""

    # media paired with a record — the entries `plan` and `emit` act on
    entries: list[ExportEntry] = field(default_factory=list)

    # supported media at the library root with no matching record
    unmatched_media: list[str] = field(default_factory=list)

    # records under .pixelkasten with no media at the library root
    unmatched_records: list[str] = field(default_factory=list)

    # visible files whose format has no handler
    unsupported_media: list[str] = field(default_factory=list)


@dataclass
class ExportResult:
    """What the run produced: the destination and the planned (or executed) copies.

    The (src, dst) operations are the source of truth; counts shown to the user
    are derived from them in `render_export` — mirroring how ingest's manifest
    and enrich's entries carry the data and the renderer derives the totals.
    """

    destination: str
    operations: list[tuple[str, str]]
