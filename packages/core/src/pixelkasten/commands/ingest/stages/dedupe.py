"""
Content-based deduplication via SHA-256 hashing.

Ported from packages/core/src/stages/dedupe.js.
"""

import hashlib
from collections.abc import Callable

from pixelkasten.configuration import IngestOptions
from pixelkasten.commands.ingest.types import Dedupe, DedupeResult, IngestEntry
from pixelkasten.types import Status
from pixelkasten.utils.progress import noop_progress


def dedupe_hash(manifest: list[IngestEntry], progress: Callable = noop_progress) -> None:
    """
    Compute SHA-256 for each manifest entry.

    Mutates entries in-place, setting entry.dedupe with hash and PENDING status.
    On error, sets entry.dedupe with ERROR status.
    """
    with progress("Hashing files", len(manifest)) as tick:
        for i, entry in enumerate(manifest):
            try:
                sha256 = _calculate_hash(entry.media_path)
                entry.dedupe = Dedupe(status=Status.PENDING, hash=sha256)
            except Exception as e:
                entry.dedupe = Dedupe(status=Status.ERROR, error=str(e))
            tick(i + 1)


def dedupe_resolve(manifest: list[IngestEntry], options: IngestOptions) -> None:
    """
    Resolve duplicates by hash. Works the same for Takeout and archive
    input — both populate ``source.type`` (album / loose), so a single
    rule covers both:

      - Unique files: KEEP.
      - Mixed source types within a duplicate group: keep the side that
        matches ``--prefer``, delete the others.
      - Uniform group (all album, or all loose): keep all. For Takeout this
        preserves cross-album membership; for archive it preserves
        cross-folder organization (and rarely retains a stray same-folder
        duplicate at the source root).

    Mutates entries in-place, setting dedupe.status and dedupe.result.
    """
    # Group by hash, skipping errored entries.
    groups: dict[str, list[tuple[IngestEntry, Dedupe]]] = {}
    for entry in manifest:
        if entry.dedupe is None or entry.dedupe.hash is None:
            continue
        groups.setdefault(entry.dedupe.hash, []).append((entry, entry.dedupe))

    _resolve(groups, options.prefer)
    _check_invariants(manifest)


def _resolve(
    groups: dict[str, list[tuple[IngestEntry, Dedupe]]],
    prefer: str,
) -> None:
    for duplicates in groups.values():
        if len(duplicates) == 1:
            _, dedupe = duplicates[0]
            dedupe.status = Status.PROCESSED
            dedupe.result = DedupeResult.KEEP
            continue

        # At least one duplicate matches the user's --prefer (e.g. "album").
        has_preferred = any(e.source.type == prefer for e, _ in duplicates)

        # At least one duplicate does NOT match --prefer (e.g. is "loose").
        has_other = any(e.source.type != prefer for e, _ in duplicates)

        for entry, dedupe in duplicates:
            dedupe.status = Status.PROCESSED

            # If the group has both preferred and non-preferred copies, --prefer
            # decides: keep matches, delete the rest. If the group is uniform
            # (all album, or all loose), there's nothing to choose between —
            # keep everything; the user wants every copy of this content.
            if has_preferred and has_other:
                dedupe.result = (
                    DedupeResult.KEEP if entry.source.type == prefer else DedupeResult.DELETE
                )
            else:
                dedupe.result = DedupeResult.KEEP


def _calculate_hash(file_path: str) -> str:
    """Read file in chunks and return hex SHA-256 digest."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def _check_invariants(manifest: list[IngestEntry]) -> None:
    """Verify all dedupe entries have a valid result or error status."""
    for entry in manifest:
        if entry.dedupe is None:
            continue
        if entry.dedupe.status == Status.ERROR:
            continue
        if entry.dedupe.result is None:
            raise ValueError(f"Dedupe result not set for {entry.media_path}")
