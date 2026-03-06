"""
Content-based deduplication via SHA-256 hashing.

Ported from packages/core/src/stages/dedupe.js.
"""

import hashlib
from collections.abc import Callable

from pixelkasten.manifest import Dedupe, DedupeResult, ManifestEntry, Status
from pixelkasten.configuration import Options


def dedupe_hash(
    manifest: list[ManifestEntry],
    on_progress: Callable[[int], None] | None = None,
) -> None:
    """
    Compute SHA-256 for each manifest entry.

    Mutates entries in-place, setting entry.dedupe with hash and PENDING status.
    On error, sets entry.dedupe with ERROR status.
    """
    for i, entry in enumerate(manifest):
        try:
            sha256 = _calculate_hash(entry.media_path)
            entry.dedupe = Dedupe(status=Status.PENDING, hash=sha256)
        except Exception as e:
            entry.dedupe = Dedupe(status=Status.ERROR, error=str(e))
        if on_progress is not None:
            on_progress(i + 1)


def dedupe_resolve(manifest: list[ManifestEntry], options: Options) -> None:
    """
    Resolve duplicates: prefer album over loose (or vice versa), keep same-type dupes.

    Mutates entries in-place, setting dedupe.result to KEEP or DELETE.

    Rules:
    - Unique files (one entry per hash): always KEEP
    - Mixed types (has preferred AND has other): keep preferred, delete others
    - Same type (all album or all loose): keep all
    """
    prefer = options.prefer

    # Group by hash, skip entries with None hash (errors).
    # Storing (entry, dedupe) tuples so pyright knows dedupe is non-None downstream.
    groups: dict[str, list[tuple[ManifestEntry, Dedupe]]] = {}
    for entry in manifest:
        if entry.dedupe is None or entry.dedupe.hash is None:
            continue
        groups.setdefault(entry.dedupe.hash, []).append((entry, entry.dedupe))

    for duplicates in groups.values():
        if len(duplicates) == 1:
            _, dedupe = duplicates[0]
            dedupe.status = Status.PROCESSED
            dedupe.result = DedupeResult.KEEP
        else:
            has_preferred = any(e.source.type == prefer for e, _ in duplicates)
            has_other = any(e.source.type != prefer for e, _ in duplicates)

            for entry, dedupe in duplicates:
                dedupe.status = Status.PROCESSED
                if has_preferred and has_other:
                    dedupe.result = (
                        DedupeResult.KEEP if entry.source.type == prefer else DedupeResult.DELETE
                    )
                else:
                    dedupe.result = DedupeResult.KEEP

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


def _check_invariants(manifest: list[ManifestEntry]) -> None:
    """Verify all dedupe entries have a valid result or error status."""
    for entry in manifest:
        if entry.dedupe is None:
            continue
        if entry.dedupe.status == Status.ERROR:
            continue
        if entry.dedupe.result is None:
            raise ValueError(f"Dedupe result not set for {entry.media_path}")
