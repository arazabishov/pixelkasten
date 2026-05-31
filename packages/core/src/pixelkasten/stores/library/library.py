"""Shared working-library reader: pair each media file with its record.

Both `enrich` and `export` consume the working library the same way — one
deterministic pass where each supported media file's record path is derived
from its filename (unlike ingest's scan+link, which partitions a messy source
and fuzzily matches Google sidecars). Reads each record once; each command maps
the shared library entries onto its own state type.
"""

import os

from pixelkasten.configuration import RECORD_SUFFIX
from pixelkasten.handlers import SUPPORTED_EXTENSIONS
from pixelkasten.stores.library.types import Library, LibraryEntry
from pixelkasten.stores.record import read_record, record_path, records_dir


def read_library(library: str) -> Library:
    """Walk the library, pairing each supported media file with its record.

    One deterministic pass — a media file's record path is mechanically derived
    from its filename. Returns:
      - ``entries``: matched media paths and parsed records
      - ``unmatched_media``: supported media with no record
      - ``unmatched_records``: parsed records with no media at the library root
      - ``unsupported_media``: visible files whose format isn't supported
    """
    rdir = records_dir(library)
    if not os.path.isdir(rdir):
        raise FileNotFoundError(f"Working library records not found: {rdir}")

    # All record files up front, so we can flag the ones no media file claims.
    records_remaining: set[str] = set()
    for name in os.listdir(rdir):
        path = os.path.join(rdir, name)
        if name.endswith(RECORD_SUFFIX) and os.path.isfile(path):
            records_remaining.add(path)

    entries: list[LibraryEntry] = []
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
            entries.append(LibraryEntry(full_path, read_record(record_file)))
        else:
            unmatched_media.append(full_path)

    unmatched_records = [read_record(record) for record in sorted(records_remaining)]
    return Library(
        entries=entries,
        unmatched_media=unmatched_media,
        unmatched_records=unmatched_records,
        unsupported_media=unsupported_media,
    )
