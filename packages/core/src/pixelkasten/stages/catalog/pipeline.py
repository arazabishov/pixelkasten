"""
Catalog pipeline — AI-powered album discovery.

embed → cluster → classify → [refine] → [caption] → propose

Filters the manifest for embeddable images internally. Files the catalog
cannot process (e.g., videos) pass through unchanged — they stay in the
manifest but don't get cluster labels, captions, or album assignments.
"""

from contextlib import contextmanager
from pathlib import Path

from pixelkasten.core.types import Catalog, ManifestEntry, Status, Tag
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
from pixelkasten.handlers import is_image
from pixelkasten.options import PipelineOptions


def run_catalog(
    manifest: list[ManifestEntry],
    options: PipelineOptions,
    progress=None,
) -> list[ManifestEntry]:
    """
    Run AI catalog stages: embed → cluster → classify → refine → caption → propose.

    Mutates manifest in-place, adding cluster labels, captions, and album
    assignments to embeddable image entries. Non-image entries are ignored.
    """
    # Filter to embeddable images — catalog ignores videos etc.
    image_entries = [e for e in manifest if is_image(Path(e.media_path))]
    image_paths = [Path(e.media_path) for e in image_entries]

    if not image_paths:
        return manifest

    # Load CLIP model once — used for both embedding and classification.
    if options.catalog is None:
        raise ValueError("catalog options are required for run_catalog")
    catalog_options = options.catalog

    model, preprocess, tokenizer, device = load_model(model_name=catalog_options.clip_model)

    with _progress_ctx(progress, "Embedding images", len(image_paths)) as on_progress:
        embeddings, failed_indices = embed_images(
            model,
            preprocess,
            image_paths,
            device,
            batch_size=catalog_options.batch_size,
            on_progress=on_progress,
        )

    # Cluster
    labels = cluster_embeddings(embeddings, min_cluster_size=catalog_options.min_cluster_size)
    representatives = find_representatives(embeddings, labels)

    # Classify
    prefixed_names, raw_labels = build_label_list(DEFAULT_LABEL_SETS)
    label_embeddings = embed_texts(model, tokenizer, raw_labels, device)
    all_tags = classify(
        embeddings, label_embeddings, prefixed_names, threshold=catalog_options.classify_threshold
    )

    # Write cluster info + tags onto manifest entries
    ok_indices = [i for i in range(len(image_paths)) if i not in failed_indices]
    reps_flat = {r for reps in representatives.values() for r in reps}
    for i, entry in enumerate(image_entries):
        if i < len(ok_indices):
            entry.catalog = Catalog(
                status=Status.PROCESSED,
                cluster=int(labels[ok_indices[i]]),
                is_representative=ok_indices[i] in reps_flat,
                tags=[
                    Tag(name=name, score=round(score, 3)) for name, score in all_tags[ok_indices[i]]
                ],
            )
        else:
            entry.catalog = Catalog(status=Status.ERROR)

    # Build manifest dict for refine/caption/propose
    summary = cluster_summary(labels)
    manifest_dict = {
        "entries": manifest,
        "clusters": {str(k): {"size": v} for k, v in summary.get("cluster_sizes", {}).items()},
    }

    # Refine (optional)
    if not catalog_options.skip_refine:
        new_labels, _ = refine_clusters(manifest_dict, embeddings)
        for i, entry in enumerate(image_entries):
            if i < len(new_labels) and entry.catalog:
                entry.catalog.cluster = int(new_labels[i])
        representatives = find_representatives(embeddings, new_labels)
        # Rebuild clusters dict so caption/propose see post-refine clusters
        summary = cluster_summary(new_labels)
        manifest_dict["clusters"] = {
            str(k): {"size": v} for k, v in summary.get("cluster_sizes", {}).items()
        }

    # Caption (optional)
    if not catalog_options.skip_caption:
        n_reps = sum(
            1
            for e in manifest
            if e.catalog and e.catalog.is_representative and e.catalog.status == Status.PROCESSED
        )
        with _progress_ctx(progress, "Captioning images", n_reps) as on_progress:
            captions = caption_representatives(
                manifest_dict,
                catalog_options.caption_model,
                "Describe this photo briefly.",
                on_progress=on_progress,
            )
        for path, cap in captions.items():
            for entry in manifest:
                if entry.media_path == path:
                    entry.catalog.caption = cap

    # Propose albums (requires Ollama)
    with _progress_ctx(progress, "Proposing albums", 1) as on_progress:
        propose_albums(manifest_dict, catalog_options)
        if on_progress:
            on_progress(1)

    return manifest


def _progress_ctx(factory, label: str, total: int):
    """Create a progress context from a factory, or a noop if factory is None."""
    if factory:
        return factory(label, total)
    return _noop_ctx()


@contextmanager
def _noop_ctx():
    """Context manager that yields None."""
    yield None
