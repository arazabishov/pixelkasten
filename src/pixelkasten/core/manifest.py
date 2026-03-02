"""
Manifest helpers for the unified pipeline.
"""


def can_keep(entry: dict) -> bool:
    """
    Returns True if the entry should be processed (not deleted or errored during dedupe).

    When dedupe was skipped, the dedupe key is absent, so the entry is kept.
    """
    dedupe = entry.get("dedupe")
    if dedupe is None:
        return True
    status = dedupe.get("status")
    return status != "delete" and status != "error"
