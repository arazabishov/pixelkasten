"""Album-name validation and proposed_album conflict detection.

Shared by three consumers, so the rules live in one place: ``propose`` rejects
an unsafe name at proposal time, ``check`` surfaces problems for the agent, and
``export`` refuses to run while a group's members disagree. Pure functions over
plain data — no command types, no disk I/O.
"""

import re

# Path separators and control chars can't appear in a single folder name.
_INVALID_NAME_CHARS = re.compile(r"[/\\\x00-\x1f]")


def check_album_name(name: str) -> bool:
    """True if ``name`` is non-empty and safe to use as a single folder name."""
    if not name.strip():
        return False
    return _INVALID_NAME_CHARS.search(name) is None


def check_album_conflicts(proposals_by_group: dict[str, set[str]]) -> list[tuple[str, list[str]]]:
    """Groups whose members carry two or more distinct ``proposed_album`` values.

    A group exports to a single album, so its members only need to *agree* — a
    partial proposal (some members null) resolves fine. Returns ``(group_id,
    sorted_proposals)`` for each conflicting group.
    """
    conflicts: list[tuple[str, list[str]]] = []
    for group_id, proposals in proposals_by_group.items():
        if len(proposals) > 1:
            conflicts.append((group_id, sorted(proposals)))
    return conflicts
