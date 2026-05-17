"""
Write ``proposed_album`` to a file's record and to all group siblings.

The agent calls ``propose(path, "Album name")`` after deciding where a
photo belongs. The tool reads the file's record, finds every record under
the same ``group_id``, and updates ``proposed_album`` on each. Idempotent
— re-running with the same album is a no-op. Passing ``album=None``
removes the field (--clear).
"""

import os

from pixelkasten.layout import read_record, record_path, records_dir, resolve_library, write_record
from pixelkasten.layout import RECORD_SUFFIX


def propose(path: str, album: str | None) -> list[str]:
    """
    Set ``proposed_album`` on the file's record and on every group sibling.

    Returns the list of record paths updated.
    """
    if album is not None:
        _validate_album_name(album)

    library = resolve_library(path)
    own_record_path = record_path(library, os.path.basename(path))
    own_data = read_record(own_record_path)
    group_id = own_data.get("group_id")
    if not group_id:
        raise RuntimeError(
            f"Record at {own_record_path} has no group_id; "
            "was the working library produced by an older `import` run?"
        )

    sibling_records = _siblings_by_group(library, group_id)

    updated: list[str] = []
    for sibling_path in sibling_records:
        data = read_record(sibling_path)
        if album is None:
            data.pop("proposed_album", None)
        else:
            data["proposed_album"] = album
        write_record(sibling_path, data)
        updated.append(sibling_path)
    return updated


def _validate_album_name(album: str) -> None:
    if not album.strip():
        raise ValueError("Album name must be non-empty.")
    if album.lower() == "null":
        raise ValueError("'null' is reserved; use --clear to remove proposed_album.")


def _siblings_by_group(library: str, group_id: str) -> list[str]:
    """Return paths of every record in ``library`` whose group_id matches."""
    rdir = records_dir(library)
    out: list[str] = []
    for name in sorted(os.listdir(rdir)):
        if not name.endswith(RECORD_SUFFIX):
            continue
        path = os.path.join(rdir, name)
        data = read_record(path)
        if data.get("group_id") == group_id:
            out.append(path)
    return out
