"""
Takeout pipeline orchestrator — runs all stages in sequence.

Ported from packages/core/src/pipeline.js. Runs the Google Takeout
processing pipeline: scan → link → dedupe → reconcile → rename → apply.
"""

from pixelkasten.core.report import report
from pixelkasten.stages.apply import apply
from pixelkasten.stages.dedupe import dedupe_hash, dedupe_resolve
from pixelkasten.stages.link import link
from pixelkasten.stages.reconcile import reconcile
from pixelkasten.stages.rename import rename
from pixelkasten.stages.scan import scan_takeout


def run_takeout_pipeline(
    options: dict,
    hooks: dict | None = None,
) -> list[dict]:
    """
    Run the takeout pipeline: scan → link → dedupe → reconcile → rename → apply.

    Args:
        options: Pipeline configuration with keys:
            source (str): source directory path (required)
            destination (str): destination directory (required unless dry_run)
            skip_dedupe (bool): skip deduplication
            skip_embed (bool): skip metadata embedding
            skip_rename (bool): skip rename stage
            dry_run (bool): compute plan without applying
            prefer (str): "album" or "loose" for dedupe preference
            fuzzy (bool): enable fuzzy matching in link stage
            fuzzy_threshold (int): minimum name length for fuzzy matching
        hooks: Optional callbacks fired after each stage:
            on_scan(raw_collections, source_path)
            on_link(result)
            on_dedupe(manifest)
            on_reconcile(manifest)
            on_rename(manifest)
            on_apply(manifest)

    Returns:
        The manifest (list of dicts) after all stages have run.
    """
    hooks = hooks or {}

    # Phase 1: scan files
    raw_collections = scan_takeout(options["source"])
    _call_hook(hooks, "on_scan", raw_collections, options["source"])

    # Phase 2: link media to sidecar files
    result = link(raw_collections, options)
    _call_hook(hooks, "on_link", result)

    manifest = result["manifest"]

    if not options.get("skip_dedupe"):
        # Phase 3: calculate hash values for media files
        dedupe_hash(manifest)

        # Phase 4: use hashes to dedupe files
        dedupe_resolve(manifest, options)
        _call_hook(hooks, "on_dedupe", manifest)

    if not options.get("skip_embed") or not options.get("skip_rename"):
        # Phase 5: resolve disk and sidecar metadata
        reconcile(manifest, options)
        _call_hook(hooks, "on_reconcile", manifest)

    if not options.get("skip_rename"):
        # Phase 6: compute target paths for renaming
        rename(manifest, options)
        _call_hook(hooks, "on_rename", manifest)

    if not options.get("dry_run"):
        # Phase 7: apply changes to disk
        apply(manifest, options)
        _call_hook(hooks, "on_apply", manifest)

        # Write per-file CSV report to destination
        report(manifest, options)

    return manifest


def _call_hook(hooks: dict, name: str, *args) -> None:
    """Call a hook if it exists."""
    hook = hooks.get(name)
    if hook:
        hook(*args)
