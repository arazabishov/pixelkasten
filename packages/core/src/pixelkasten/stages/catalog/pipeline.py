"""
Catalog pipeline — AI-powered album discovery.

embed → cluster → classify → [refine] → [caption] → propose

Filters the manifest for embeddable images internally. Files the catalog
cannot process (e.g., videos) pass through unchanged — they stay in the
manifest but don't get cluster labels, captions, or album assignments.
"""

from contextlib import contextmanager
from pathlib import Path

from pixelkasten.stages.catalog.caption import caption_representatives
from pixelkasten.stages.catalog.classify import (
    DEFAULT_LABEL_SETS,
    build_label_list,
    classify,
)
from pixelkasten.stages.catalog.cluster import (
    cluster_embeddings,
    cluster_summary,
    find_representatives,
)
from pixelkasten.stages.catalog.embed import embed_images, embed_texts, load_model
from pixelkasten.stages.catalog.organize import propose_albums
from pixelkasten.stages.catalog.refine import refine_clusters
from pixelkasten.core.handlers import is_image


def run_catalog(
    manifest: list[dict],
    options: dict,
    workspace: Path | None = None,
    progress=None,
) -> list[dict]:
    """
    Run AI catalog stages: embed → cluster → classify → refine → caption → propose.

    Mutates manifest in-place, adding cluster labels, captions, and album
    assignments to embeddable image entries. Non-image entries are ignored.

    Args:
        manifest: The pipeline manifest (list of entry dicts).
        options: Pipeline options. Relevant keys:
            clip_model (str): CLIP model name (default "ViT-L-14")
            batch_size (int): embedding batch size (default 32)
            min_cluster_size (int): HDBSCAN min cluster size (default 5)
            threshold (float): classification threshold (default 0.15)
            skip_refine (bool): skip temporal cluster refinement
            skip_caption (bool): skip VLM captioning
            caption_model (str): Ollama vision model (default "llava")
            rescan (bool): ignore cached embeddings
        workspace: Optional workspace directory for embedding cache.
        progress: Optional progress factory (label, total) -> context manager
            yielding an on_progress(completed) callback.

    Returns:
        The manifest (same list, mutated in-place).
    """
    # Filter to embeddable images — catalog ignores videos etc.
    image_entries = [e for e in manifest if is_image(Path(e["mediaPath"]))]
    image_paths = [Path(e["mediaPath"]) for e in image_entries]

    if not image_paths:
        return manifest

    # Load CLIP model once — used for both embedding and classification.
    model_name = options.get("clip_model", "ViT-L-14")
    model, preprocess, tokenizer, device = load_model(model_name=model_name)

    # Try loading cached embeddings
    embeddings = None
    if workspace and not options.get("rescan"):
        embeddings = _load_workspace_embeddings(workspace)

    if embeddings is None:
        with _progress_ctx(
            progress, "Embedding images", len(image_paths)
        ) as on_progress:
            embeddings, failed_indices = embed_images(
                model,
                preprocess,
                image_paths,
                device,
                batch_size=options.get("batch_size", 32),
                on_progress=on_progress,
            )

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
    prefixed_names, raw_labels = build_label_list(DEFAULT_LABEL_SETS)
    label_embeddings = embed_texts(model, tokenizer, raw_labels, device)
    all_tags = classify(
        embeddings, label_embeddings, prefixed_names, threshold=threshold
    )

    # Write cluster info + tags onto manifest entries
    ok_indices = [i for i in range(len(image_paths)) if i not in failed_indices]
    reps_flat = {r for reps in representatives.values() for r in reps}
    for i, entry in enumerate(image_entries):
        if i < len(ok_indices):
            entry["cluster"] = int(labels[ok_indices[i]])
            entry["status"] = "ok"
            entry["is_representative"] = ok_indices[i] in reps_flat
            entry["tags"] = [
                {"name": name, "score": round(score, 3)}
                for name, score in all_tags[ok_indices[i]]
            ]
        else:
            entry["status"] = "failed"

    # Build manifest dict for refine/caption/propose
    summary = cluster_summary(labels)
    manifest_dict = {
        "entries": manifest,
        "clusters": {
            str(k): {"size": v} for k, v in summary.get("cluster_sizes", {}).items()
        },
    }

    # Refine (optional)
    if not options.get("skip_refine"):
        new_labels, _ = refine_clusters(manifest_dict, embeddings)
        for i, entry in enumerate(image_entries):
            if i < len(new_labels):
                entry["cluster"] = int(new_labels[i])
        representatives = find_representatives(embeddings, new_labels)
        # Rebuild clusters dict so caption/propose see post-refine clusters
        summary = cluster_summary(new_labels)
        manifest_dict["clusters"] = {
            str(k): {"size": v} for k, v in summary.get("cluster_sizes", {}).items()
        }

    # Caption (optional)
    if not options.get("skip_caption"):
        caption_model = options.get("caption_model", "llava")
        n_reps = sum(
            1
            for e in manifest
            if e.get("is_representative") and e.get("status") == "ok"
        )
        with _progress_ctx(progress, "Captioning images", n_reps) as on_progress:
            captions = caption_representatives(
                manifest_dict,
                caption_model,
                "Describe this photo briefly.",
                on_progress=on_progress,
            )
        for path, cap in captions.items():
            for entry in manifest:
                if entry["mediaPath"] == path:
                    entry["caption"] = cap

    # Propose albums (requires Ollama)
    with _progress_ctx(progress, "Proposing albums", 1) as on_progress:
        propose_albums(manifest_dict, options)
        if on_progress:
            on_progress(1)

    return manifest


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


def _progress_ctx(factory, label: str, total: int):
    """Create a progress context from a factory, or a noop if factory is None."""
    if factory:
        return factory(label, total)
    return _noop_ctx()


@contextmanager
def _noop_ctx():
    """Context manager that yields None."""
    yield None
