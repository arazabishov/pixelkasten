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

    model, preprocess, tokenizer, device = load_model(model_name=options.discovery.clip_model)

    with progress("Embedding images", len(image_paths)) as tick:
        embeddings, failed_indices = embed_images(
            model,
            preprocess,
            image_paths,
            device,
            batch_size=options.discovery.batch_size,
            on_progress=tick,
        )

    # Cluster
    labels = cluster_embeddings(embeddings, min_cluster_size=options.discovery.min_cluster_size)

    # Classify
    prefixed_names, raw_labels = build_label_list(DEFAULT_LABEL_SETS)
    label_embeddings = embed_texts(model, tokenizer, raw_labels, device)
    all_tags = classify(
        embeddings, label_embeddings, prefixed_names, threshold=options.discovery.classify_threshold
    )

    # Create Discovery objects early so downstream stages never see None.
    # embedded_entries[i] aligns with embeddings row i.
    failed = set(failed_indices)
    embedded_entries = []
    for i, entry in enumerate(image_entries):
        if i in failed:
            entry.discovery = Discovery(status=Status.ERROR)
        else:
            entry.discovery = Discovery(status=Status.PROCESSED)
            embedded_entries.append(entry)

    # Populate cluster and tags.
    for i, entry in enumerate(embedded_entries):
        entry.discovery.cluster = int(labels[i])
        entry.discovery.tags = [Tag(name=name, score=round(score, 3)) for name, score in all_tags[i]]

    # Resolve GPS → location names (used by refine and organize).
    from pixelkasten.stages.discovery.geocode import reverse_geocode

    reverse_geocode(manifest)

    # Refine (optional) — update labels before representative selection.
    if not options.discovery.skip_refine:
        labels, _ = refine_clusters(embedded_entries, embeddings)
        for i, entry in enumerate(embedded_entries):
            if entry.discovery is not None:
                entry.discovery.cluster = int(labels[i])

    # Representatives — computed once on final labels.
    representatives = find_representatives(embeddings, labels)
    reps_flat = {r for reps in representatives.values() for r in reps}
    for i, entry in enumerate(embedded_entries):
        if entry.discovery is not None:
            entry.discovery.is_representative = i in reps_flat

    # Caption (optional).
    if not options.discovery.skip_caption:
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
                options.discovery.caption_model,
                on_progress=tick,
            )
        entries_by_path = {e.media_path: e for e in image_entries}
        for path, cap in captions.items():
            entry = entries_by_path.get(path)
            if entry and entry.discovery:
                entry.discovery.caption = cap

    # Propose albums (requires Ollama).
    with progress("Proposing albums", 1) as tick:
        propose_albums(image_entries, options.discovery)
        if tick:
            tick(1)

    return manifest
