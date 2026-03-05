"""
Unified pipeline orchestrator — supports both takeout and archive modes.

Linear flow with conditional stages:
  scan → link → dedupe → reconcile → geocode → [catalog] → rename → apply

The --takeout flag enables sidecar matching, --catalog enables AI album discovery.
"""

from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path

from pixelkasten.options import PipelineOptions
from pixelkasten.stages.geocode import reverse_geocode
from pixelkasten.core.manifest import can_keep
from pixelkasten.core.report import report
from pixelkasten.stages.apply import apply
from pixelkasten.stages.dedupe import dedupe_hash, dedupe_resolve
from pixelkasten.stages.link import link
from pixelkasten.stages.reconcile import reconcile
from pixelkasten.stages.rename import rename
from pixelkasten.stages.scan import scan


def run_pipeline(
    options: PipelineOptions,
    hooks: dict | None = None,
    progress: Callable | None = None,
) -> list[dict]:
    """
    Unified pipeline: linear flow with conditional stages.

    Returns the manifest (list of dicts) after all stages have run.
    """
    hooks = hooks or {}

    manifest = _init_manifest(options, hooks, progress)

    if options.catalog:
        from pixelkasten.stages.catalog import run_catalog

        manifest = run_catalog(manifest, options, progress=progress)

    if not options.skip_rename:
        rename(manifest)
        _call_hook(hooks, "on_rename", manifest)

    if not options.dry_run:
        n_keepers = sum(1 for e in manifest if can_keep(e))
        with _progress_ctx(progress, "Applying changes", n_keepers) as on_progress:
            apply(manifest, options, on_progress=on_progress)
        _call_hook(hooks, "on_apply", manifest)
        report(manifest, options)

    _call_hook(hooks, "on_errors", manifest)

    return manifest


def _init_manifest(
    options: PipelineOptions,
    hooks: dict,
    progress: Callable | None,
) -> list[dict]:
    """Build the manifest from source files."""
    raw_collections = scan(options.source)
    _call_hook(hooks, "on_scan", raw_collections, options.source)

    if options.takeout:
        result = link(raw_collections, options)
        _call_hook(hooks, "on_link", result)
        manifest = result["manifest"]
    else:
        manifest = [
            {"mediaPath": p, "source": {"type": "loose"}}
            for p in raw_collections["files_media"]
        ]

    # Dedupe runs before reconcile so reconcile can skip deleted entries
    # via can_keep(). Dedupe only needs mediaPath + source.type (from link).
    if not options.skip_dedupe:
        with _progress_ctx(progress, "Hashing files", len(manifest)) as on_progress:
            dedupe_hash(manifest, on_progress=on_progress)
        dedupe_resolve(manifest, options)
        _call_hook(hooks, "on_dedupe", manifest)

    if not options.skip_embed or not options.skip_rename:
        with _progress_ctx(progress, "Reading metadata", len(manifest)) as on_progress:
            reconcile(manifest, options, on_progress=on_progress)
        _call_hook(hooks, "on_reconcile", manifest)

    reverse_geocode(manifest)

    return manifest


def _call_hook(hooks: dict, name: str, *args) -> None:
    """Call a hook if it exists."""
    hook = hooks.get(name)
    if hook:
        hook(*args)


def _progress_ctx(factory, label: str, total: int):
    """Create a progress context from a factory, or a noop if factory is None."""
    if factory:
        return factory(label, total)
    return _noop_ctx()


@contextmanager
def _noop_ctx():
    """Context manager that yields None (used when no progress factory is provided)."""
    yield None
