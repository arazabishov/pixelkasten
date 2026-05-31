"""Reject a library that would export ambiguously — the hard stop behind ``check``.

``check`` reports these same two problems (within-group proposal conflicts and
unsafe album names) so the agent can fix them via ``propose`` before exporting.
This stage is ``export``'s last-line defense if a library reaches it unchecked:
it inspects the grouped entries and raises, never touching state or disk. It runs
before ``plan`` so path computation can assume a group resolves to one safe album.
"""

from pixelkasten.commands.export.types import Export, Group
from pixelkasten.utils.album import check_album_conflicts, check_album_name


def validate(state: Export) -> None:
    """Raise on within-group ``proposed_album`` conflicts or unsafe album names."""
    groups = state.grouped()

    _reject_proposal_conflicts(groups)
    _reject_invalid_album_names(groups)


def _reject_proposal_conflicts(groups: list[Group]) -> None:
    """Raise if any group's members disagree on ``proposed_album``.

    A group exports to a single album, so its members must agree — ``check``
    surfaces these for the agent first; this is the stop if one slips through.
    """
    proposals_by_group: dict[str, set[str]] = {
        group.id: {e.record.proposed_album for e in group.entries if e.record.proposed_album}
        for group in groups
    }

    conflicts = check_album_conflicts(proposals_by_group)
    if not conflicts:
        return

    detail = "\n".join(f"  {group_id}: {proposals}" for group_id, proposals in conflicts)
    raise RuntimeError("proposed_album disagreement; resolve before exporting:\n" + detail)


def _reject_invalid_album_names(groups: list[Group]) -> None:
    """Raise if any group's resolved target album isn't a safe folder name."""
    invalid: set[str] = set()
    for group in groups:
        album = group.target_album()
        if album and not check_album_name(album):
            invalid.add(album)

    if not invalid:
        return

    detail = "\n".join(f"  {album!r}" for album in sorted(invalid))
    raise RuntimeError("invalid album name(s); resolve before exporting:\n" + detail)
