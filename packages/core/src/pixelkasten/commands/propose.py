"""
Write ``proposed_album`` to a file's record and to all group siblings.

The agent calls ``propose(path, "Album name")`` after deciding where a
photo belongs. The tool reads the file's record, finds every record under
the same ``group_id``, and updates ``proposed_album`` on each. Idempotent
— re-running with the same album is a no-op. Passing ``album=None``
removes the field (--clear).
"""

import os

from pixelkasten.utils.album import check_album_name
from pixelkasten.stores.record import Record, read_record, write_record
from pixelkasten.stores.record import record_path, records_dir, records_dir_home
from pixelkasten.configuration import RECORD_SUFFIX


def propose(path: str, album: str | None) -> list[str]:
    """
    Set ``proposed_album`` on the file's record and on every group sibling.

    Returns the list of record paths updated.
    """
    if album is not None:
        _check_album_name(album)

    library = records_dir_home(path)

    own_record_path = record_path(library, os.path.basename(path))
    own_record = read_record(own_record_path)

    group_id = own_record.group_id
    if not group_id:
        raise RuntimeError(
            f"Record at {own_record_path} has no group_id; "
            "was the working library produced by an older `import` run?"
        )

    sibling_records = _siblings_by_group(library, group_id)

    # paths of records updated by this call
    updated: list[str] = []
    for sibling in sibling_records:
        sibling.proposed_album = album
        write_record(sibling)
        updated.append(sibling.path)
    return updated


def _check_album_name(album: str) -> None:
    if album.lower() == "null":
        raise ValueError("'null' is reserved; use --clear to remove proposed_album.")
    if not check_album_name(album):
        raise ValueError(f"Invalid album name {album!r}: non-empty, no separators/control chars.")


def _siblings_by_group(library: str, group_id: str) -> list[Record]:
    """Return every record in ``library`` whose group_id matches."""
    rdir = records_dir(library)
    record_paths = [
        os.path.join(rdir, n) for n in sorted(os.listdir(rdir)) if n.endswith(RECORD_SUFFIX)
    ]
    records = [read_record(p) for p in record_paths]
    return [r for r in records if r.group_id == group_id]
