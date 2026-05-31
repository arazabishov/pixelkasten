"""Typed results of the working-library walk.

Split from ``library.py`` so a module that needs only these shapes can import
them without pulling in the walk and its handler dependencies.
"""

from dataclasses import dataclass, field

from pixelkasten.stores.record.types import Record


@dataclass
class LibraryEntry:
    """A supported media file paired with its parsed record."""

    # top-level media file in the working library
    media: str

    # parsed .pk.json record for the media file
    record: Record


@dataclass
class Library:
    """The working-library walk, including paired entries and pairing gaps."""

    # media files paired with their parsed records
    entries: list[LibraryEntry] = field(default_factory=list)

    # supported media with no matching record
    unmatched_media: list[str] = field(default_factory=list)

    # parsed records with no media at the library root
    unmatched_records: list[Record] = field(default_factory=list)

    # visible files whose format isn't supported
    unsupported_media: list[str] = field(default_factory=list)
