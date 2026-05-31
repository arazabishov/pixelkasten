"""
Check a working library is ready to export.

The agent runs ``check`` after organizing to confirm the library has no
integrity problems that would make ``export`` ambiguous or fail. Two classes
of problem are reported:

  - proposed_album disagreement within a group: a group's files all export to
    one album, so their proposed_album values must agree.
  - an invalid album name: a target album name that isn't a safe folder name.

``export`` runs the same conflict check and refuses to run while conflicts
remain, so ``check`` is the agent's chance to find and fix them first (via
``propose``) before exporting.
"""

from pixelkasten.utils.album import check_album_conflicts, check_album_name
from pixelkasten.stores.library import read_library
from pixelkasten.stores.record.types import Record


def check(library: str) -> dict:
    """Report proposed_album conflicts and invalid names across the library."""
    raw_library = read_library(library)
    records = [entry.record for entry in raw_library.entries]
    records.extend(raw_library.unmatched_records)

    records_by_group: dict[str, list[Record]] = {}
    for record in records:
        records_by_group.setdefault(record.group_id or "", []).append(record)

    proposals_by_group: dict[str, set[str]] = {}
    for group_id, group in records_by_group.items():
        proposals_by_group[group_id] = {
            record.proposed_album for record in group if record.proposed_album
        }

    conflicts = check_album_conflicts(proposals_by_group)
    invalid = _invalid_target_album_names(records_by_group, proposals_by_group)

    return {
        "ok": not conflicts and not invalid,
        "conflicts": [
            {"group_id": group_id, "proposals": proposals} for group_id, proposals in conflicts
        ],
        "invalid_album_names": invalid,
    }


def _invalid_target_album_names(
    records_by_group: dict[str, list[Record]],
    proposals_by_group: dict[str, set[str]],
) -> list[str]:
    invalid: set[str] = set()
    for group_id, group in records_by_group.items():
        proposals = proposals_by_group[group_id]
        if proposals:
            invalid.update(name for name in proposals if not check_album_name(name))
            continue

        album = next((record.album for record in group if record.album), None)
        if album and not check_album_name(album):
            invalid.add(album)
    return sorted(invalid)
