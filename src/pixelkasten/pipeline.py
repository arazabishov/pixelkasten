"""
Unified pipeline orchestrator — supports both takeout and archive modes.

Takeout mode: scan → link → reconcile → dedupe → rename → apply
Archive mode: scan → exif_read → dedupe → embed → cluster → classify →
              refine → caption → propose → rename → apply

Mode is set explicitly via options["mode"] ("takeout" or "archive").
The --catalog flag enables AI album discovery (propose stage).
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
from pixelkasten.stages.scan import scan_takeout


def run_pipeline(
    options: dict,
    hooks: dict | None = None,
) -> list[dict]:
    """
    Unified pipeline: run takeout or archive stages based on mode.

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
        if mode == "takeout":
            manifest = _run_takeout_init(options, hooks, progress)
        else:
            manifest = _run_archive_init(options, hooks)

        # Save to workspace cache
        if workspace:
            _save_workspace_manifest(workspace, manifest)

    # Shared stages: dedupe → rename → apply
    if not options.get("skip_dedupe"):
        with _progress_ctx(progress, "Hashing files", len(manifest)) as on_progress:
            dedupe_hash(manifest, on_progress=on_progress)
        dedupe_resolve(manifest, options)
        _call_hook(hooks, "on_dedupe", manifest)

    # Catalog stages (AI album discovery)
    if options.get("catalog"):
        manifest = _run_catalog_stages(manifest, options, hooks, workspace)

    if not options.get("skip_rename"):
        rename(manifest, options)
        _call_hook(hooks, "on_rename", manifest)

    if not options.get("dry_run"):
        n_keepers = sum(1 for e in manifest if can_keep(e))
        with _progress_ctx(progress, "Applying changes", n_keepers) as on_progress:
            apply(manifest, options, on_progress=on_progress)
        _call_hook(hooks, "on_apply", manifest)
        report(manifest, options)

    return manifest


def run_takeout_pipeline(
    options: dict,
    hooks: dict | None = None,
) -> list[dict]:
    """Convenience: run pipeline in takeout mode."""
    options = {**options, "mode": "takeout"}
    return run_pipeline(options, hooks)


# ---------------------------------------------------------------------------
# Init stages (mode-specific)
# ---------------------------------------------------------------------------


def _run_takeout_init(options: dict, hooks: dict, progress=None) -> list[dict]:
    """Takeout init: scan → link → reconcile."""
    raw_collections = scan_takeout(options["source"])
    _call_hook(hooks, "on_scan", raw_collections, options["source"])

    result = link(raw_collections, options)
    _call_hook(hooks, "on_link", result)

    manifest = result["manifest"]

    if not options.get("skip_embed") or not options.get("skip_rename"):
        with _progress_ctx(progress, "Reading metadata", len(manifest)) as on_progress:
            reconcile(manifest, options, on_progress=on_progress)
        _call_hook(hooks, "on_reconcile", manifest)

    return manifest


def _run_archive_init(options: dict, hooks: dict) -> list[dict]:
    """
    Archive init: scan → exif_read.

    Returns a manifest list of dicts with mediaPath, source, and metadata
    populated from EXIF. Albums are not yet assigned (that's the propose stage).
    """
    from pixelkasten.core.exif import read_exif
    from pixelkasten.stages.scan import scan

    image_paths = scan(Path(options["source"]))
    _call_hook(hooks, "on_scan", image_paths, options["source"])

    # Build manifest entries
    manifest = []
    for path in image_paths:
        manifest.append(
            {
                "mediaPath": str(path),
                "source": {"type": "loose"},
            }
        )

    # Read EXIF for all files
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
# Catalog stages (AI album discovery)
# ---------------------------------------------------------------------------


def _run_catalog_stages(
    manifest: list[dict],
    options: dict,
    hooks: dict,
    workspace: Path | None,
) -> list[dict]:
    """
    Run AI catalog stages: embed → cluster → classify → refine → caption → propose.

    Heavy dependencies (torch, sklearn, ollama) are deferred-imported here
    so they're only loaded when --catalog is used.
    """
    from pixelkasten.stages.classify import build_label_list, classify
    from pixelkasten.stages.cluster import (
        cluster_embeddings,
        cluster_summary,
        find_representatives,
    )
    from pixelkasten.stages.embed import embed_images, embed_texts, load_model
    from pixelkasten.stages.propose import propose_albums
    from pixelkasten.stages.scan import is_image

    # Filter to embeddable images
    image_entries = [e for e in manifest if is_image(Path(e["mediaPath"]))]
    image_paths = [Path(e["mediaPath"]) for e in image_entries]

    if not image_paths:
        return manifest

    # Try loading cached embeddings
    embeddings = None
    if workspace and not options.get("rescan"):
        embeddings = _load_workspace_embeddings(workspace)

    if embeddings is None:
        # Embed
        model_name = options.get("clip_model", "ViT-L-14")
        model, preprocess, tokenizer, device = load_model(model_name=model_name)

        embeddings, failed_indices = embed_images(
            model,
            preprocess,
            image_paths,
            device,
            batch_size=options.get("batch_size", 32),
        )

        # Save embeddings to workspace
        if workspace:
            _save_workspace_embeddings(workspace, embeddings)
    else:
        failed_indices = []

    # Cluster
    min_cluster_size = options.get("min_cluster_size", 5)
    labels = cluster_embeddings(embeddings, min_cluster_size=min_cluster_size)
    representatives = find_representatives(embeddings, labels)

    # Classify
    threshold = options.get("threshold", 0.15)
    model_name = options.get("clip_model", "ViT-L-14")
    model, preprocess, tokenizer, device = load_model(model_name=model_name)
    from pixelkasten.stages.classify import DEFAULT_LABEL_SETS

    prefixed_names, raw_labels = build_label_list(DEFAULT_LABEL_SETS)
    label_embeddings = embed_texts(model, tokenizer, raw_labels, device)
    classify(embeddings, label_embeddings, prefixed_names, threshold=threshold)

    # Write cluster info onto manifest entries
    ok_indices = [i for i in range(len(image_paths)) if i not in failed_indices]
    for idx, entry_idx in enumerate(range(len(image_entries))):
        if entry_idx < len(ok_indices):
            image_entries[entry_idx]["cluster"] = int(labels[ok_indices[entry_idx]])
            image_entries[entry_idx]["status"] = "ok"
            image_entries[entry_idx]["is_representative"] = ok_indices[entry_idx] in [
                r for reps in representatives.values() for r in reps
            ]
        else:
            image_entries[entry_idx]["status"] = "failed"

    # Build manifest dict for organize/propose (expects {"entries": [...], "clusters": {...}})
    summary = cluster_summary(labels)
    manifest_dict = {
        "entries": manifest,
        "clusters": {
            str(k): {"size": v} for k, v in summary.get("cluster_sizes", {}).items()
        },
    }

    # Refine (optional)
    if not options.get("skip_refine"):
        from pixelkasten.stages.refine import refine_clusters

        new_labels, _ = refine_clusters(manifest_dict, embeddings)
        # Update labels on entries
        for i, entry in enumerate(image_entries):
            if i < len(new_labels):
                entry["cluster"] = int(new_labels[i])
        representatives = find_representatives(embeddings, new_labels)

    # Caption (optional)
    if not options.get("skip_caption"):
        from pixelkasten.stages.caption import caption_representatives

        # Caption representatives (requires Ollama)
        caption_model = options.get("caption_model", "llava")
        captions = caption_representatives(
            manifest_dict,
            caption_model,
            "Describe this photo briefly.",
        )
        # Write captions onto entries
        for path, cap in captions.items():
            for entry in manifest:
                if entry["mediaPath"] == path:
                    entry["caption"] = cap

    # Propose albums (requires Ollama)
    propose_albums(manifest_dict, options)

    # Sync source info back from manifest_dict entries to manifest
    # (propose_albums mutates manifest_dict["entries"] which IS manifest)

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


def _load_workspace_embeddings(workspace: Path):
    """Load cached embeddings from workspace, or None if not found."""
    import numpy as np

    embeddings_path = workspace / "embeddings.npy"
    if embeddings_path.exists():
        return np.load(str(embeddings_path))
    return None


def _save_workspace_embeddings(workspace: Path, embeddings) -> None:
    """Save embeddings to workspace."""
    import numpy as np

    workspace.mkdir(parents=True, exist_ok=True)
    embeddings_path = workspace / "embeddings.npy"
    np.save(str(embeddings_path), embeddings)


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
