"""Walk a working library and partition every file by type."""

import os

from pixelkasten.configuration import RECORD_SUFFIX
from pixelkasten.handlers import ALL_KNOWN_MEDIA_EXTENSIONS
from pixelkasten.utils.record import records_dir


def scan(library: str) -> dict:
    """Walk the working library; partition every file by type.

    Returns three flat lists:
      files_media         - known media files at the library root
      files_records       - .pk.json files in .pixelkasten/
      files_other_ignored - visible files at the root that are not media
    """
    rdir = records_dir(library)
    if not os.path.isdir(rdir):
        raise FileNotFoundError(f"Working library records not found: {rdir}")

    files_media: list[str] = []
    files_records: list[str] = []
    files_other_ignored: list[str] = []

    # Sort so downstream geocoding and embeddings.paths.json order is stable across runs.
    for filename in sorted(os.listdir(library)):
        full_path = os.path.join(library, filename)
        ext = os.path.splitext(filename)[1].lower()

        # Skip dotfiles to avoid AppleDouble resource forks: macOS writes a `._IMG.heic`
        # next to every `IMG.heic` on FAT/SMB/USB. Same extension, same `isfile`, but it's
        # a 4 KB metadata blob that would corrupt the embedding store if treated as media.
        is_visible_file = os.path.isfile(full_path) and not filename.startswith(".")
        if is_visible_file and ext in ALL_KNOWN_MEDIA_EXTENSIONS:
            files_media.append(full_path)
        elif is_visible_file:
            files_other_ignored.append(full_path)

    # Records share .pixelkasten/ with embeddings.npy, embeddings.paths.json, and
    # report.csv, so filter by record suffix rather than enumerating the directory.
    for filename in sorted(os.listdir(rdir)):
        full_path = os.path.join(rdir, filename)
        if os.path.isfile(full_path) and filename.endswith(RECORD_SUFFIX):
            files_records.append(full_path)

    return {
        "files_media": files_media,
        "files_records": files_records,
        "files_other_ignored": files_other_ignored,
    }
