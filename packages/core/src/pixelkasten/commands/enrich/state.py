"""Mutable state shared by enrich stages."""

from dataclasses import dataclass, field


@dataclass
class EnrichEntry:
    """One working-library media file paired with its record."""

    # top-level media file in the working library
    media: str

    # matching .pk.json record for the media file
    record: str


@dataclass
class EnrichState:
    """Run state and final summary for the `enrich` command."""

    # paired (media, record) entries that the stages will process
    entries: list[EnrichEntry] = field(default_factory=list)

    # supported media files skipped because their record is missing
    missing_records: list[str] = field(default_factory=list)

    # records with no matching media file at the library root
    orphan_records: list[str] = field(default_factory=list)

    # top-level visible files skipped because enrich does not support their format
    unsupported_media: list[str] = field(default_factory=list)

    # records that gained a `location` field this run
    locations_added: int = 0

    # records skipped because `location` was already set
    locations_already_set: int = 0

    # images that gained an embedding this run
    images_embedded: int = 0

    # videos that gained an embedding this run
    videos_embedded: int = 0

    # images skipped because their filename is already in embeddings.paths.json
    images_already_embedded: int = 0

    # videos skipped because their filename is already in embeddings.paths.json
    videos_already_embedded: int = 0

    # absolute paths of images that failed to embed (corrupt, decode error)
    images_failed: list[str] = field(default_factory=list)

    # absolute paths of videos that failed to embed (ffmpeg / CLIP failure)
    videos_failed: list[str] = field(default_factory=list)

    @property
    def entries_total(self) -> int:
        """Number of paired (media, record) entries enrich will process."""
        return len(self.entries)
