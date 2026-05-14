"""
Clustering — group similar images together based on their embeddings.

# Why clustering?

After generating CLIP embeddings (embed.py), we have a 768-dimensional
vector for each image. Images of similar content have similar vectors.
Clustering algorithms find these natural groupings automatically.

# Why HDBSCAN?

There are many clustering algorithms. The two most common are:

- **k-means**: You specify the number of clusters upfront (k=10, k=50, etc.)
  and the algorithm partitions all data into exactly that many groups. Simple
  and fast, but you need to know how many groups to expect.

- **HDBSCAN** (Hierarchical Density-Based Spatial Clustering of Applications
  with Noise): Discovers the number of clusters automatically based on the
  density of the data. It also identifies "noise" — points that don't belong
  to any cluster (label = -1). This is better for photo libraries because you
  don't know how many distinct events or scenes exist in advance.

We use HDBSCAN as the default because it requires fewer assumptions. The key
parameter is `min_cluster_size` — the smallest group of images that counts as
a cluster. Setting this too low creates many tiny clusters; too high and small
events get absorbed into larger groups or marked as noise.

# Representatives

After clustering, we select "representative" images from each cluster — the
images that are most typical of the group. These are used in Phase 2 (VLM
captioning) so we only need to caption a small fraction of the library.
"""

import numpy as np
from sklearn.cluster import HDBSCAN

from pixelkasten.configuration import DiscoveryOptions
from pixelkasten.manifest import ManifestEntry


def cluster_embeddings(
    embeddings: np.ndarray,
    options: DiscoveryOptions,
) -> np.ndarray:
    """
    Cluster image embeddings using HDBSCAN with cosine distance.

    Reads `min_cluster_size` from options. Returns an (N,) array of
    integer labels — each image gets a cluster ID >= 0 or -1 (noise).

    Cosine distance is natural for CLIP embeddings: they're L2-normalized,
    and cosine similarity captures semantic similarity better than
    Euclidean distance in high-dimensional spaces.
    """
    # sklearn stubs say str for copy, but runtime only accepts bool
    clusterer = HDBSCAN(
        min_cluster_size=options.min_cluster_size,
        metric="cosine",
        copy=True,  # pyright: ignore[reportArgumentType]
    )

    labels = clusterer.fit_predict(embeddings)
    return labels


def find_representatives(
    entries: list[ManifestEntry],
    embeddings: np.ndarray,
    n_per_cluster: int = 3,
) -> None:
    """
    Select top-N representative entries per cluster.

    A "representative" is an image close to its cluster's centroid — the
    most "typical" member. We select multiple per cluster to give VLM
    captioning a few diverse examples rather than only the most typical one.

    Reads cluster assignments from entry.discovery.cluster and writes
    entry.discovery.is_representative. Entries aligned by position with
    rows in `embeddings`.
    """
    labels = np.array(
        [
            e.discovery.cluster if e.discovery and e.discovery.cluster is not None else -1
            for e in entries
        ]
    )

    rep_indices: set[int] = set()
    for label in set(labels.tolist()):
        # Skip noise points — they don't belong to any cluster.
        if label == -1:
            continue

        cluster_indices = np.where(labels == label)[0]
        cluster_vecs = embeddings[cluster_indices]

        # Centroid: element-wise mean, L2-normalized so dot product is cosine similarity.
        centroid = cluster_vecs.mean(axis=0)
        centroid = centroid / np.linalg.norm(centroid)

        # Top-N most similar to centroid.
        similarities = cluster_vecs @ centroid
        n = min(n_per_cluster, len(cluster_indices))
        top_local = np.argsort(similarities)[-n:][::-1]
        rep_indices.update(cluster_indices[top_local].tolist())

    for i, entry in enumerate(entries):
        if entry.discovery is not None:
            entry.discovery.is_representative = i in rep_indices


def cluster_summary(labels: np.ndarray) -> dict:
    """
    Produce a summary of clustering results.

    Returns:
        A dict with:
        - n_clusters: Number of clusters found (excluding noise).
        - n_noise: Number of unclustered images.
        - cluster_sizes: Dict of cluster_id → member count.
    """
    unique, counts = np.unique(labels, return_counts=True)
    cluster_sizes = {}
    n_noise = 0

    for label, count in zip(unique, counts):
        if label == -1:
            n_noise = int(count)
        else:
            cluster_sizes[int(label)] = int(count)

    return {
        "n_clusters": len(cluster_sizes),
        "n_noise": n_noise,
        "cluster_sizes": cluster_sizes,
    }
