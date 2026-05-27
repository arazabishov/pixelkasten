"""
Ingest command — normalize a source into a working library.

The command runs a linear pipeline of stages:

    scan → link → dedupe → reconcile → group → emit

Each stage enriches an in-memory manifest; only ``emit`` (and ``reconcile``,
read-only) touches the filesystem. ``ingest`` composes them and returns
an ``IngestResult`` covering every stage.

The user-facing command name is ``pixelkasten import``; the Python module is
``ingest`` because ``import`` is a reserved keyword.
"""

from collections.abc import Callable
from dataclasses import dataclass

from pixelkasten.commands.ingest.stages.dedupe import dedupe_hash, dedupe_resolve
from pixelkasten.commands.ingest.stages.emit import emit
from pixelkasten.commands.ingest.stages.group import group
from pixelkasten.commands.ingest.stages.link import link
from pixelkasten.commands.ingest.stages.reconcile import reconcile
from pixelkasten.commands.ingest.stages.report import report
from pixelkasten.commands.ingest.stages.scan import scan
from pixelkasten.configuration import IngestOptions
from pixelkasten.manifest import ManifestEntry


@dataclass
class IngestResult:
    """Manifest plus pre-link state that is not derivable from the manifest alone."""

    manifest: list[ManifestEntry]
    raw_collections: dict
    link_stats: dict


def ingest(options: IngestOptions, progress: Callable) -> IngestResult:
    """Run the ingest pipeline; return an ``IngestResult`` covering every stage."""

    # Walk the source and partition files into media / Takeout sidecars / album markers.
    raw_collections = scan(options.source)

    # Match each media file to its Google Takeout sidecar (archive mode short-circuits).
    link_result = link(raw_collections, options)
    manifest, link_stats = link_result["manifest"], link_result["stats"]

    if not options.skip_dedupe:
        # SHA-256 hash every file, then resolve duplicates per --prefer (Takeout) or lex-smallest (archive).
        with progress("Hashing files", len(manifest)) as tick:
            dedupe_hash(manifest, on_progress=tick)
        dedupe_resolve(manifest, options)

    # Read disk EXIF, queue write_tags for any metadata only the sidecar has.
    count = sum(1 for e in manifest if e.can_keep())
    with progress("Reading metadata", count) as tick:
        reconcile(manifest, options, on_progress=tick)

    # Assign a shared group_id to logical asset groups (Live Photo siblings, edited variants).
    group(manifest, options)

    if not options.dry_run:
        # Copy files to the destination, write per-asset records, apply queued EXIF tags.
        count = sum(1 for e in manifest if e.can_keep())
        with progress("Emitting working library", count) as tick:
            emit(manifest, options, on_progress=tick)

        # Per-file CSV summary of what happened to each entry.
        report(manifest, options)

    return IngestResult(
        manifest=manifest,
        raw_collections=raw_collections,
        link_stats=link_stats,
    )
