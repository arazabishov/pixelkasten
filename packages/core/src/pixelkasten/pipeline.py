"""
Unified pipeline orchestrator.

Linear flow with conditional stages:
  scan → link → dedupe → reconcile → [discover] → rename → apply

Link matches sidecars automatically when present, --discover enables AI album discovery.
"""

from collections.abc import Callable

from pixelkasten.configuration import Hooks, Options
from pixelkasten.manifest import ManifestEntry
from pixelkasten.stages.report import report
from pixelkasten.stages.apply import apply
from pixelkasten.stages.dedupe import dedupe_hash, dedupe_resolve
from pixelkasten.stages.link import link
from pixelkasten.stages.reconcile import reconcile
from pixelkasten.stages.rename import rename
from pixelkasten.stages.scan import scan


def run_pipeline(options: Options, hooks: Hooks, progress: Callable) -> list[ManifestEntry]:
    """
    Unified pipeline: linear flow with conditional stages.

    Returns the manifest after all stages have run.
    """

    raw_collections = scan(options.source)
    hooks.on_scan(raw_collections, options.source)

    result = link(raw_collections, options)
    hooks.on_link(result)

    manifest = result["manifest"]

    # Dedupe runs before reconcile so it can skip deleted entries
    if not options.skip_dedupe:
        with progress("Hashing files", len(manifest)) as tick:
            dedupe_hash(manifest, on_progress=tick)
        dedupe_resolve(manifest, options)
        hooks.on_dedupe(manifest)

    # Rename needs disk timestamps to build date-based paths
    if not options.skip_embed or not options.skip_rename:
        count = sum(1 for e in manifest if e.can_keep())
        with progress("Reading metadata", count) as tick:
            reconcile(manifest, options, on_progress=tick)
        hooks.on_reconcile(manifest)

    # Deferred import — discovery pulls in torch/CLIP which are optional deps
    if options.discovery:
        from pixelkasten.stages.discovery import run_discovery

        manifest = run_discovery(manifest, options, progress=progress)

    if not options.skip_rename:
        rename(manifest)
        hooks.on_rename(manifest)

    if not options.dry_run:
        count = sum(1 for e in manifest if e.can_keep())
        with progress("Applying changes", count) as tick:
            apply(manifest, options, on_progress=tick)
        hooks.on_apply(manifest)
        report(manifest, options)

    hooks.on_errors(manifest)

    return manifest
