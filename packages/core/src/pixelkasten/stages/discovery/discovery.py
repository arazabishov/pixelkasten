"""
AI-powered album discovery.

embed → cluster → classify → [refine] → [caption] → propose

Filters the manifest for embeddable images internally. Files that cannot
be processed (e.g., videos) pass through unchanged — they stay in the
manifest but don't get cluster labels, captions, or album assignments.
"""

from collections.abc import Callable

from pixelkasten.manifest import Discovery, ManifestEntry, Status, Tag
from pixelkasten.stages.discovery.classify import (
    DEFAULT_LABEL_SETS,
    build_label_list,
    classify,
)
from pixelkasten.stages.discovery.cluster import (
    cluster_embeddings,
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

    # Map image_entries index → embedding row index.
    # Failed images don't have a row in the embeddings array, so we
    # skip them and track which entry index maps to which row.
    failed = set(failed_indices)
    entry_to_row: dict[int, int] = {}
    row = 0
    for i in range(len(image_paths)):
        if i not in failed:
            entry_to_row[i] = row
            row += 1

    # Populate discovery field on each image entry.
    reps_flat = {r for reps in representatives.values() for r in reps}
    for i, entry in enumerate(image_entries):
        if i in entry_to_row:
            embed_row = entry_to_row[i]
            entry.discovery = Discovery(
                status=Status.PROCESSED,
                cluster=int(labels[embed_row]),
                is_representative=embed_row in reps_flat,
                tags=[Tag(name=name, score=round(score, 3)) for name, score in all_tags[embed_row]],
            )
        else:
            entry.discovery = Discovery(status=Status.ERROR)

    # Resolve GPS → location names (used by refine and organize).
    from pixelkasten.stages.discovery.geocode import reverse_geocode

    reverse_geocode(manifest)

    # Refine (optional).
    if not discovery_opts.skip_refine:
        new_labels, _ = refine_clusters(image_entries, embeddings)
        for i, entry in enumerate(image_entries):
            if i in entry_to_row and entry.discovery and entry.discovery.status == Status.PROCESSED:
                entry.discovery.cluster = int(new_labels[entry_to_row[i]])
        # Recompute representatives after refinement.
        representatives = find_representatives(embeddings, new_labels)
        reps_flat = {r for reps in representatives.values() for r in reps}
        for i, entry in enumerate(image_entries):
            if i in entry_to_row and entry.discovery:
                entry.discovery.is_representative = entry_to_row[i] in reps_flat

    # Caption (optional).
    if not discovery_opts.skip_caption:
        from pixelkasten.stages.discovery.caption import caption_representatives

        n_reps = sum(
            1
            for entry in image_entries
            if entry.discovery
            and entry.discovery.is_representative
            and entry.discovery.status == Status.PROCESSED
        )
        with progress("Captioning images", n_reps) as tick:
            captions = caption_representatives(
                image_entries,
                discovery_opts.caption_model,
                "Describe this photo briefly.",
                on_progress=tick,
            )
        entries_by_path = {e.media_path: e for e in image_entries}
        for path, cap in captions.items():
            entry = entries_by_path.get(path)
            if entry and entry.discovery:
                entry.discovery.caption = cap

    # Propose albums (requires Ollama).
    with progress("Proposing albums", 1) as tick:
        propose_albums(image_entries, discovery_opts)
        if tick:
            tick(1)

    return manifest
