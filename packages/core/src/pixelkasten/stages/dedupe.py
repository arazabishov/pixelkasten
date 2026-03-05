"""
Content-based deduplication via SHA-256 hashing.

Ported from packages/core/src/stages/dedupe.js.
"""

import hashlib
from collections.abc import Callable

from pixelkasten.options import PipelineOptions


def dedupe_hash(
    manifest: list[dict],
    on_progress: Callable[[int], None] | None = None,
) -> None:
    """
    Compute SHA-256 for each manifest entry.

    Mutates entries in-place, adding:
        entry["dedupe"] = {"hash": str, "status": "pending"}
    On error:
        entry["dedupe"] = {"hash": None, "status": "error", "reason": str}
    """
    for i, entry in enumerate(manifest):
        try:
            sha256 = _calculate_hash(entry["mediaPath"])
            entry["dedupe"] = {"hash": sha256, "status": "pending"}
        except Exception as e:
            entry["dedupe"] = {"hash": None, "status": "error", "reason": str(e)}
        if on_progress is not None:
            on_progress(i + 1)


def dedupe_resolve(manifest: list[dict], options: PipelineOptions) -> None:
    """
    Resolve duplicates: prefer album over loose (or vice versa), keep same-type dupes.

    Mutates entries in-place, setting dedupe.status to "keep" or "delete".

    Rules:
    - Unique files (one entry per hash): always "keep"
    - Mixed types (has preferred AND has other): keep preferred, delete others
    - Same type (all album or all loose): keep all

    options:
        prefer: "album" | "loose" (default: "album")
    """
    prefer = options.prefer

    # Group by hash, skip entries with None hash (errors)
    groups: dict[str, list[dict]] = {}
    for entry in manifest:
        h = entry.get("dedupe", {}).get("hash")
        if h:
            groups.setdefault(h, []).append(entry)

    for duplicates in groups.values():
        if len(duplicates) == 1:
            duplicates[0]["dedupe"]["status"] = "keep"
        else:
            has_preferred = any(e["source"]["type"] == prefer for e in duplicates)
            has_other = any(e["source"]["type"] != prefer for e in duplicates)

            if has_preferred and has_other:
                for entry in duplicates:
                    entry["dedupe"]["status"] = (
                        "keep" if entry["source"]["type"] == prefer else "delete"
                    )
            else:
                # All same type: keep all
                for entry in duplicates:
                    entry["dedupe"]["status"] = "keep"

    _check_invariants(manifest)


def _calculate_hash(file_path: str) -> str:
    """Read file in chunks and return hex SHA-256 digest."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _check_invariants(manifest: list[dict]) -> None:
    """Verify all dedupe statuses are valid."""
    valid = {"keep", "delete", "error"}
    for entry in manifest:
        status = entry.get("dedupe", {}).get("status")
        if status not in valid:
            raise ValueError(
                f'Invalid dedupe status "{status}" for {entry.get("mediaPath", "unknown")}'
            )
