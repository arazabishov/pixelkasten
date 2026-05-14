"""
AI-powered album discovery.

embed → cluster → [refine] → [caption] → propose

Filters the manifest for embeddable images internally. Files that cannot
be processed (e.g., videos) pass through unchanged — they stay in the
manifest but don't get cluster labels, captions, or album assignments.
"""

from collections.abc import Callable

from pixelkasten.manifest import Discovery, ManifestEntry, Status
from pixelkasten.stages.discovery.cluster import (
    cluster_embeddings,
    find_representatives,
)
from pixelkasten.stages.discovery.embed import embed_images
from pixelkasten.stages.discovery.organize import propose_albums
from pixelkasten.stages.discovery.refine import infer_home_region, refine_clusters
from pixelkasten.handlers import is_image
from pixelkasten.configuration import Options


def run_discovery(
    manifest: list[ManifestEntry], options: Options, progress: Callable
) -> list[ManifestEntry]:
    """
    Run AI discovery stages: embed → cluster → refine → caption → propose.

    Mutates manifest entries' source field when albums are discovered.
    Non-image entries are ignored.
    """
    image_entries = [e for e in manifest if is_image(e.media_path)]
    image_paths = [e.media_path for e in image_entries]

    if not image_paths:
        return manifest

    if options.discovery is None:
        raise ValueError("discovery options are required for run_discovery")

    with progress("Embedding images", len(image_paths)) as tick:
        embeddings, failed_indices = embed_images(image_paths, options.discovery, on_progress=tick)

    # Cluster
    labels = cluster_embeddings(embeddings, options.discovery)

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

    # Populate cluster assignments.
    for i, entry in enumerate(embedded_entries):
        entry.discovery.cluster = int(labels[i])

    # Resolve GPS → location names (used by refine and organize).
    from pixelkasten.stages.discovery.geocode import reverse_geocode

    reverse_geocode(manifest)

    # Infer home region once — used by refine (noise absorption) and organize (album filtering).
    regions = [e.location.region for e in image_entries if e.location and e.location.region]
    home_region = infer_home_region(regions)

    # Refine (optional) — updates entry.discovery.cluster.
    if not options.discovery.skip_refine:
        refine_clusters(embedded_entries, embeddings, home_region=home_region)

    # Pick representatives — reads final cluster from entries, writes is_representative.
    find_representatives(embedded_entries, embeddings)

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
            caption_representatives(image_entries, options.discovery, on_progress=tick)

    # Propose albums (requires Ollama).
    with progress("Proposing albums", 1) as tick:
        propose_albums(image_entries, options.discovery, home_region=home_region)
        if tick:
            tick(1)

    return manifest
