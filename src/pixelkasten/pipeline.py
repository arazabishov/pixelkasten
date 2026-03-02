"""
Unified pipeline orchestrator — supports both takeout and archive modes.

Linear flow with conditional stages:
  scan → [takeout: link → reconcile] → dedupe → [catalog] → rename → apply

Mode is set explicitly via options["mode"] ("takeout" or "archive").
The --catalog flag enables AI album discovery.
Workspace caching (-w) persists init data + embeddings between runs.
"""

import json
from contextlib import contextmanager
from pathlib import Path

from pixelkasten.core.manifest import can_keep
from pixelkasten.core.report import report
from pixelkasten.stages.apply import apply
from pixelkasten.stages.dedupe import dedupe_hash, dedupe_resolve
from pixelkasten.stages.link import link
from pixelkasten.stages.reconcile import reconcile
from pixelkasten.stages.rename import rename
from pixelkasten.stages.scan import scan


def run_pipeline(
    options: dict,
    hooks: dict | None = None,
) -> list[dict]:
    """
    Unified pipeline: linear flow with conditional stages based on mode.

    Args:
        options: Pipeline configuration with keys:
            source (str): source directory path (required)
            destination (str): destination directory (required unless dry_run)
            mode (str): "takeout" (default) or "archive"
            catalog (bool): enable AI album discovery (propose stage)
            workspace (str|Path|None): workspace directory for caching
            rescan (bool): invalidate cached workspace, re-scan source
            skip_dedupe (bool): skip SHA-256 deduplication
            skip_embed (bool): skip metadata embedding (takeout only)
            skip_rename (bool): skip rename stage
            skip_caption (bool): skip VLM captioning (catalog only)
            skip_refine (bool): skip temporal cluster refinement (catalog only)
            dry_run (bool): compute plan without applying
            prefer (str): "album" or "loose" for dedupe preference
            fuzzy (bool): enable fuzzy matching in link stage
            fuzzy_threshold (int): minimum name length for fuzzy matching
        hooks: Optional callbacks fired after each stage.

    Returns:
        The manifest (list of dicts) after all stages have run.
    """
    hooks = hooks or {}
    mode = options.get("mode", "takeout")
    workspace = Path(options["workspace"]) if options.get("workspace") else None
    progress = options.get("progress")

    # Try loading from workspace cache
    manifest = None
    if workspace and not options.get("rescan"):
        manifest = _load_workspace_manifest(workspace)

    if manifest is None:
        # Scan (always full scan, both modes)
        raw_collections = scan(options["source"])
        _call_hook(hooks, "on_scan", raw_collections, options["source"])

        if mode == "takeout":
            # Takeout: link sidecars + reconcile metadata
            result = link(raw_collections, options)
            _call_hook(hooks, "on_link", result)
            manifest = result["manifest"]

            if not options.get("skip_embed") or not options.get("skip_rename"):
                with _progress_ctx(
                    progress, "Reading metadata", len(manifest)
                ) as on_progress:
                    reconcile(manifest, options, on_progress=on_progress)
                _call_hook(hooks, "on_reconcile", manifest)
        else:
            # Archive: build manifest from media files, read EXIF
            manifest = _build_archive_manifest(raw_collections, hooks)

        # Save to workspace cache
        if workspace:
            _save_workspace_manifest(workspace, manifest)

    # Shared stages: dedupe → catalog → rename → apply
    if not options.get("skip_dedupe"):
        with _progress_ctx(progress, "Hashing files", len(manifest)) as on_progress:
            dedupe_hash(manifest, on_progress=on_progress)
        dedupe_resolve(manifest, options)
        _call_hook(hooks, "on_dedupe", manifest)

    if options.get("catalog"):
        from pixelkasten.stages.catalog import run_catalog

        manifest = run_catalog(manifest, options, workspace=workspace)

    if not options.get("skip_rename"):
        rename(manifest, options)
        _call_hook(hooks, "on_rename", manifest)

    if not options.get("dry_run"):
        n_keepers = sum(1 for e in manifest if can_keep(e))
        with _progress_ctx(progress, "Applying changes", n_keepers) as on_progress:
            apply(manifest, options, on_progress=on_progress)
        _call_hook(hooks, "on_apply", manifest)
        report(manifest, options)

    _call_hook(hooks, "on_errors", manifest)

    return manifest


# ---------------------------------------------------------------------------
# Archive manifest builder
# ---------------------------------------------------------------------------


def _build_archive_manifest(
    raw_collections: dict,
    hooks: dict,
) -> list[dict]:
    """
    Build a manifest from scan results without sidecar processing.

    Reads EXIF directly from media files and populates metadata.dates.
    No sidecar matching or metadata embedding.
    """
    from pixelkasten.core.exiftool import read_exif

    media_paths = raw_collections["files_media"]

    manifest: list[dict] = []
    for path in media_paths:
        manifest.append(
            {
                "mediaPath": path,
                "source": {"type": "loose"},
            }
        )

    if manifest:
        exif_data = read_exif([Path(e["mediaPath"]) for e in manifest])

        for entry in manifest:
            exif = exif_data.get(entry["mediaPath"], {})
            dates = []
            if exif.get("timestamp"):
                dates.append(exif["timestamp"])
            entry["metadata"] = {
                "status": "noop",
                "writeTags": [],
                "dates": dates,
            }
            if exif.get("gps"):
                entry["exif"] = {"gps": exif["gps"]}
            if exif.get("timestamp"):
                entry["exif"] = entry.get("exif", {})
                entry["exif"]["timestamp"] = exif["timestamp"]

    _call_hook(hooks, "on_reconcile", manifest)
    return manifest


# ---------------------------------------------------------------------------
# Workspace caching
# ---------------------------------------------------------------------------


def _load_workspace_manifest(workspace: Path) -> list[dict] | None:
    """Load cached manifest from workspace, or None if not found."""
    manifest_path = workspace / "manifest.json"
    if manifest_path.exists():
        with open(manifest_path) as f:
            return json.load(f)
    return None


def _save_workspace_manifest(workspace: Path, manifest: list[dict]) -> None:
    """Save manifest to workspace."""
    workspace.mkdir(parents=True, exist_ok=True)
    manifest_path = workspace / "manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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
