"""
AI-powered album discovery.

embed → cluster → classify → [refine] → [caption] → propose

Filters the manifest for embeddable images internally. Files that cannot
be processed (e.g., videos) pass through unchanged — they stay in the
manifest but don't get cluster labels, captions, or album assignments.
"""

from collections.abc import Callable

from pixelkasten.manifest import Discovery, ManifestEntry, Status, Tag
from pixelkasten.stages.discovery.caption import caption_representatives
from pixelkasten.stages.discovery.classify import (
    DEFAULT_LABEL_SETS,
    build_label_list,
    classify,
)
from pixelkasten.stages.discovery.cluster import (
    cluster_embeddings,
    cluster_summary,
    find_representatives,
)
from pixelkasten.stages.discovery.embed import embed_images, embed_texts, load_model
from pixelkasten.stages.discovery.organize import propose_albums
from pixelkasten.stages.discovery.refine import refine_clusters
from pixelkasten.handlers import is_image
from pixelkasten.configuration import Options


def run_discovery(
    manifest: list[ManifestEntry], options: Options, progress: Callable
) -> list[ManifestEntry]:
    """
    Run AI discovery stages: embed → cluster → classify → refine → caption → propose.

    Mutates manifest entries' source field when albums are discovered.
    Non-image entries are ignored.
    """
    image_entries = [e for e in manifest if is_image(e.media_path)]
    image_paths = [e.media_path for e in image_entries]

    if not image_paths:
        return manifest

    if options.discovery is None:
        raise ValueError("discovery options are required for run_discovery")
    discovery_opts = options.discovery

    model, preprocess, tokenizer, device = load_model(model_name=discovery_opts.clip_model)

    with progress("Embedding images", len(image_paths)) as tick:
        embeddings, failed_indices = embed_images(
            model,
            preprocess,
            image_paths,
            device,
            batch_size=discovery_opts.batch_size,
            on_progress=tick,
        )

    # Cluster
    labels = cluster_embeddings(embeddings, min_cluster_size=discovery_opts.min_cluster_size)
    representatives = find_representatives(embeddings, labels)

    # Classify
    prefixed_names, raw_labels = build_label_list(DEFAULT_LABEL_SETS)
    label_embeddings = embed_texts(model, tokenizer, raw_labels, device)
    all_tags = classify(
        embeddings, label_embeddings, prefixed_names, threshold=discovery_opts.classify_threshold
    )

    # Populate discovery field on each image entry
    ok_indices = [i for i in range(len(image_paths)) if i not in failed_indices]
    reps_flat = {r for reps in representatives.values() for r in reps}
    for i, entry in enumerate(image_entries):
        if i < len(ok_indices):
            entry.discovery = Discovery(
                status=Status.PROCESSED,
                cluster=int(labels[ok_indices[i]]),
                is_representative=ok_indices[i] in reps_flat,
                tags=[
                    Tag(name=name, score=round(score, 3)) for name, score in all_tags[ok_indices[i]]
                ],
            )
        else:
            entry.discovery = Discovery(status=Status.ERROR)

    summary = cluster_summary(labels)
    discovery_manifest = {
        "entries": image_entries,
        "clusters": {str(k): {"size": v} for k, v in summary.get("cluster_sizes", {}).items()},
    }

    # Resolve GPS → location names (used by refine and organize)
    from pixelkasten.stages.discovery.geocode import reverse_geocode

    reverse_geocode(manifest)

    # Refine (optional)
    if not discovery_opts.skip_refine:
        new_labels, _ = refine_clusters(discovery_manifest, embeddings)
        for i, entry in enumerate(image_entries):
            if (
                entry.discovery
                and i < len(new_labels)
                and entry.discovery.status == Status.PROCESSED
            ):
                entry.discovery.cluster = int(new_labels[i])
        representatives = find_representatives(embeddings, new_labels)
        summary = cluster_summary(new_labels)
        discovery_manifest["clusters"] = {
            str(k): {"size": v} for k, v in summary.get("cluster_sizes", {}).items()
        }

    # Caption (optional)
    if not discovery_opts.skip_caption:
        n_reps = sum(
            1
            for entry in image_entries
            if entry.discovery
            and entry.discovery.is_representative
            and entry.discovery.status == Status.PROCESSED
        )
        with progress("Captioning images", n_reps) as tick:
            captions = caption_representatives(
                discovery_manifest,
                discovery_opts.caption_model,
                "Describe this photo briefly.",
                on_progress=tick,
            )
        for path, cap in captions.items():
            for entry in image_entries:
                if entry.media_path == path and entry.discovery:
                    entry.discovery.caption = cap

    # Propose albums (requires Ollama)
    with progress("Proposing albums", 1) as tick:
        propose_albums(discovery_manifest, discovery_opts)
        if tick:
            tick(1)

    return manifest
