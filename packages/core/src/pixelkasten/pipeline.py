"""
Unified pipeline orchestrator — supports both takeout and archive modes.

Linear flow with conditional stages:
  scan → link → dedupe → reconcile → geocode → [catalog] → rename → apply

The --takeout flag enables sidecar matching, --catalog enables AI album discovery.
"""

from collections.abc import Callable

from pixelkasten.configuration import Hooks, Options
from pixelkasten.core.manifest import can_keep
from pixelkasten.core.report import report
from pixelkasten.core.types import ManifestEntry, Source
from pixelkasten.stages.apply import apply
from pixelkasten.stages.dedupe import dedupe_hash, dedupe_resolve
from pixelkasten.stages.geocode import reverse_geocode
from pixelkasten.stages.link import link
from pixelkasten.stages.reconcile import reconcile
from pixelkasten.stages.rename import rename
from pixelkasten.stages.scan import scan

Manifest = list[ManifestEntry]


def run_pipeline(options: Options, hooks: Hooks, progress: Callable) -> Manifest:
    """
    Unified pipeline: linear flow with conditional stages.

    Returns the manifest after all stages have run.
    """

    manifest = _init_manifest(options, hooks, progress)

    if options.catalog:
        from pixelkasten.stages.catalog import run_catalog

        manifest = run_catalog(manifest, options, progress=progress)

    if not options.skip_rename:
        rename(manifest)
        hooks.on_rename(manifest)

    if not options.dry_run:
        count = sum(1 for e in manifest if can_keep(e))
        with progress("Applying changes", count) as tick:
            apply(manifest, options, on_progress=tick)
        hooks.on_apply(manifest)
        report(manifest, options)

    hooks.on_errors(manifest)

    return manifest


def _init_manifest(options: Options, hooks: Hooks, progress: Callable) -> Manifest:
    """Build the manifest from source files."""

    raw_collections = scan(options.source)
    hooks.on_scan(raw_collections, options.source)

    if options.takeout:
        result = link(raw_collections, options)
        hooks.on_link(result)

        manifest = result["manifest"]
    else:
        manifest = [
            ManifestEntry(media_path=p, source=Source(type="loose"))
            for p in raw_collections["files_media"]
        ]

    # Dedupe runs before reconcile so reconcile can skip deleted entries
    # via can_keep(). Dedupe only needs media_path + source.type (from link).
    if not options.skip_dedupe:
        with progress("Hashing files", len(manifest)) as tick:
            dedupe_hash(manifest, on_progress=tick)
        dedupe_resolve(manifest, options)
        hooks.on_dedupe(manifest)

    if not options.skip_embed or not options.skip_rename:
        with progress("Reading metadata", len(manifest)) as tick:
            reconcile(manifest, options, on_progress=tick)
        hooks.on_reconcile(manifest)

    reverse_geocode(manifest)

    return manifest
