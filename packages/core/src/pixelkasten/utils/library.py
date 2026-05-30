"""Shared working-library reader: pair each media file with its record.

Both `enrich` and `export` consume the working library the same way — one
deterministic pass where each supported media file's record path is derived
from its filename (unlike ingest's scan+link, which partitions a messy source
and fuzzily matches Google sidecars). Returns a plain dict (like `read_record`
/ `read_sidecar`); each command's `read` stage maps it onto its own entry type.
"""

import os

from pixelkasten.configuration import RECORD_SUFFIX
from pixelkasten.handlers import SUPPORTED_EXTENSIONS
from pixelkasten.utils.record import record_path, records_dir


def read_library(library: str) -> dict:
    """Walk the library, pairing each supported media file with its record.

    One deterministic pass — a media file's record path is mechanically derived
    from its filename. Returns a dict with:
      - ``entries``: matched ``(media, record)`` path pairs
      - ``unmatched_media``: supported media with no record
      - ``unmatched_records``: records with no media at the library root
      - ``unsupported_media``: visible files whose format isn't supported
    """
    rdir = records_dir(library)
    if not os.path.isdir(rdir):
        raise FileNotFoundError(f"Working library records not found: {rdir}")

    # All record files up front, so we can flag the ones no media file claims.
    records_remaining = {
        os.path.join(rdir, name)
        for name in os.listdir(rdir)
        if name.endswith(RECORD_SUFFIX) and os.path.isfile(os.path.join(rdir, name))
    }

    entries: list[tuple[str, str]] = []
    unmatched_media: list[str] = []
    unsupported_media: list[str] = []

    # Sort so embeddings.paths.json append order is stable across runs/filesystems.
    for filename in sorted(os.listdir(library)):
        full_path = os.path.join(library, filename)
        # Skip dotfiles: macOS writes AppleDouble `._IMG.heic` resource forks on
        # FAT/SMB/USB — same extension, but a 4 KB metadata blob, not media.
        if not os.path.isfile(full_path) or filename.startswith("."):
            continue
        if os.path.splitext(filename)[1].lower() not in SUPPORTED_EXTENSIONS:
            unsupported_media.append(full_path)
            continue
        record_file = record_path(library, filename)
        if record_file in records_remaining:
            records_remaining.discard(record_file)
            entries.append((full_path, record_file))
        else:
            unmatched_media.append(full_path)

    return {
        "entries": entries,
        "unmatched_media": unmatched_media,
        "unmatched_records": sorted(records_remaining),
        "unsupported_media": unsupported_media,
    }
