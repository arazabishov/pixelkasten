"""
Unified pipeline orchestrator.

Linear flow:
  scan → link → dedupe → reconcile → group → emit

Link matches sidecars automatically when present. emit writes GUID-named
copies and per-asset sidecars into <destination>/.pixelkasten/.
"""

from collections.abc import Callable

from pixelkasten.configuration import Hooks, Options
from pixelkasten.manifest import ManifestEntry
from pixelkasten.stages.report import report
from pixelkasten.stages.emit import emit
from pixelkasten.stages.dedupe import dedupe_hash, dedupe_resolve
from pixelkasten.stages.group import group
from pixelkasten.stages.link import link
from pixelkasten.stages.reconcile import reconcile
from pixelkasten.stages.scan import scan


def run_pipeline(options: Options, hooks: Hooks, progress: Callable) -> list[ManifestEntry]:
    """
    Unified pipeline: linear flow of stages.

    Returns the manifest after all stages have run.
    """

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

    if options.write_manifest:
        from pixelkasten.tools.serialize import write_manifest

        write_manifest(manifest, options)

    return manifest
