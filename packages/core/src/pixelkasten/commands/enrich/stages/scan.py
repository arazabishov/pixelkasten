"""Discover working-library records and media for enrich."""

import os

from pixelkasten.configuration import RECORD_SUFFIX
from pixelkasten.handlers import is_image, is_video
from pixelkasten.utils.record import records_dir


def scan(library: str) -> dict[str, list[str]]:
    """Discover records and top-level media in a working library."""
    if not os.path.isdir(library):
        raise FileNotFoundError(f"Library directory not found: {library}")

    rdir = records_dir(library)
    if not os.path.isdir(rdir):
        raise FileNotFoundError(f"Working library records not found: {rdir}")

    media, unsupported = _read_media(library)

    return {
        "records": _read_records(rdir),
        "media": media,
        "unsupported": unsupported,
    }


def _read_records(rdir: str) -> list[str]:
    """Record files in the working library."""
    records: list[str] = []

    # Sort so geocoding order is stable across runs.
    for name in sorted(os.listdir(rdir)):
        if name.endswith(RECORD_SUFFIX):
            records.append(os.path.join(rdir, name))
    return records


def _read_media(library: str) -> tuple[list[str], list[str]]:
    """Top-level supported and unsupported media files in the working library."""
    media: list[str] = []
    unsupported: list[str] = []

    # Sort so embeddings.paths.json is stable across runs.
    for name in sorted(os.listdir(library)):
        path = os.path.join(library, name)
        is_file = os.path.isfile(path)
        is_supported = is_image(name) or is_video(name)
        is_visible = not name.startswith(".")

        if is_visible and is_file and is_supported:
            media.append(path)
        elif is_visible and is_file:
            unsupported.append(path)
    return media, unsupported
