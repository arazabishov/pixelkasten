"""
Import command — pipeline orchestrator.

Linear flow:
  scan → link → dedupe → reconcile → group → emit

Link matches Google Takeout sidecars automatically when present. emit writes
GUID-named copies and per-asset records into <destination>/.pixelkasten/.
"""

from collections.abc import Callable
from dataclasses import dataclass

from pixelkasten.configuration import Options
from pixelkasten.manifest import ManifestEntry
from pixelkasten.commands.import_.report import report
from pixelkasten.commands.import_.emit import emit
from pixelkasten.commands.import_.dedupe import dedupe_hash, dedupe_resolve
from pixelkasten.commands.import_.group import group
from pixelkasten.commands.import_.link import link
from pixelkasten.commands.import_.reconcile import reconcile
from pixelkasten.commands.import_.scan import scan


@dataclass
class ImportResult:
    """Everything an import run produces, packaged for the renderer.

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


def run_import(options: Options, progress: Callable) -> ImportResult:
    """Run the import pipeline; return an ``ImportResult`` covering every stage."""

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

    return ImportResult(
        manifest=manifest,
        raw_collections=raw_collections,
        link_stats=link_stats,
        source=options.source,
        dry_run=options.dry_run,
    )
