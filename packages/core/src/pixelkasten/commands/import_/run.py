"""
Import command — pipeline orchestrator.

Linear flow:
  scan → link → dedupe → reconcile → group → emit

Link matches Google Takeout sidecars automatically when present. emit writes
GUID-named copies and per-asset records into <destination>/.pixelkasten/.
"""

from collections.abc import Callable

from pixelkasten.configuration import Hooks, Options
from pixelkasten.manifest import ManifestEntry
from pixelkasten.commands.import_.report import report
from pixelkasten.commands.import_.emit import emit
from pixelkasten.commands.import_.dedupe import dedupe_hash, dedupe_resolve
from pixelkasten.commands.import_.group import group
from pixelkasten.commands.import_.link import link
from pixelkasten.commands.import_.reconcile import reconcile
from pixelkasten.commands.import_.scan import scan


def run_import(options: Options, hooks: Hooks, progress: Callable) -> list[ManifestEntry]:
    """Run the import pipeline; return the manifest after every stage."""

    raw_collections = scan(options.source)
    hooks.on_scan(raw_collections, options.source)

    result = link(raw_collections, options)
    hooks.on_link(result)

    manifest = result["manifest"]

    if not options.skip_dedupe:
        with progress("Hashing files", len(manifest)) as tick:
            dedupe_hash(manifest, on_progress=tick)
        dedupe_resolve(manifest, options)
        hooks.on_dedupe(manifest)

    count = sum(1 for e in manifest if e.can_keep())
    with progress("Reading metadata", count) as tick:
        reconcile(manifest, options, on_progress=tick)
    hooks.on_reconcile(manifest)

    group(manifest, options)

    if not options.dry_run:
        count = sum(1 for e in manifest if e.can_keep())
        with progress("Emitting working library", count) as tick:
            emit(manifest, options, on_progress=tick)
        hooks.on_apply(manifest)
        report(manifest, options)

    hooks.on_errors(manifest)

    return manifest
