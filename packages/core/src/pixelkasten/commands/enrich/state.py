"""Mutable state shared by enrich stages."""

from dataclasses import dataclass, field


@dataclass
class EnrichState:
    """Run state and final summary for the `enrich` command."""

    # total records discovered in the working library
    records_total: int = 0

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

    # top-level visible files skipped because enrich does not support their format
    unsupported_media: list[str] = field(default_factory=list)

    # absolute paths of images that failed to embed (corrupt, decode error)
    images_failed: list[str] = field(default_factory=list)

    # absolute paths of videos that failed to embed (ffmpeg / CLIP failure)
    videos_failed: list[str] = field(default_factory=list)
