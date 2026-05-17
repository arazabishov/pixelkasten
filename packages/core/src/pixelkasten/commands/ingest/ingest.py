"""
Ingest command — normalize a source into a working library.

The command runs a linear pipeline of stages:

    scan → link → dedupe → reconcile → group → emit

Each stage enriches an in-memory manifest; only ``emit`` (and ``reconcile``,
read-only) touches the filesystem. ``ingest`` composes them and returns
an ``IngestResult`` covering every stage.

The CLI command name is ``pixelkasten import``; the Python module is
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
from pixelkasten.configuration import Options
from pixelkasten.manifest import ManifestEntry


@dataclass
class IngestResult:
    """Everything an ingest run produces, packaged for the renderer.

    The manifest carries the post-pipeline state of every entry (dedupe,
    metadata, group_id, emit outcome). ``raw_collections`` and ``link_stats``
    aren't derivable from the manifest alone — they capture pre-link
    counts and the set of unmatched files — so they're kept on the side.
    """

    manifest: list[ManifestEntry]
    raw_collections: dict
    link_stats: dict
    source: str
    dry_run: bool


def ingest(options: Options, progress: Callable) -> IngestResult:
    """Run the ingest pipeline; return an ``IngestResult`` covering every stage."""

    raw_collections = scan(options.source)

    link_result = link(raw_collections, options)
    manifest = link_result["manifest"]
    link_stats = link_result["stats"]

    if not options.skip_dedupe:
        with progress("Hashing files", len(manifest)) as tick:
            dedupe_hash(manifest, on_progress=tick)
        dedupe_resolve(manifest, options)

    count = sum(1 for e in manifest if e.can_keep())
    with progress("Reading metadata", count) as tick:
        reconcile(manifest, options, on_progress=tick)

    group(manifest, options)

    if not options.dry_run:
        count = sum(1 for e in manifest if e.can_keep())
        with progress("Emitting working library", count) as tick:
            emit(manifest, options, on_progress=tick)
        report(manifest, options)

    return IngestResult(
        manifest=manifest,
        raw_collections=raw_collections,
        link_stats=link_stats,
        source=options.source,
        dry_run=options.dry_run,
    )
