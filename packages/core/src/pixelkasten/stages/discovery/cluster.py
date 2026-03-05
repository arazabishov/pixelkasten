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


def cluster_embeddings(
    embeddings: np.ndarray,
    min_cluster_size: int = 5,
    min_samples: int | None = None,
) -> np.ndarray:
    """
    Cluster image embeddings using HDBSCAN.

    Args:
        embeddings: A numpy array of shape (N, D) where N is the number of
            images and D is the embedding dimension (768 for CLIP ViT-L/14).
        min_cluster_size: The smallest number of images that can form a
            cluster. Smaller values create more fine-grained clusters.
            - 5 is a reasonable default for small libraries (<1k images).
            - 10-20 for medium libraries (1k-10k images).
            - 20-50 for large libraries (10k+ images).
        min_samples: Controls how conservative the clustering is. Higher
            values make it harder for a point to be a core point, resulting
            in more noise points. Defaults to min_cluster_size if not set.

    Returns:
        A numpy array of shape (N,) with integer cluster labels. Each image
        gets a label >= 0 (its cluster ID) or -1 (noise / unclustered).
    """
    # HDBSCAN with cosine metric is natural for CLIP embeddings because
    # they're L2-normalized — cosine distance captures semantic similarity
    # better than Euclidean distance in high-dimensional spaces.
    # sklearn stubs say str for copy, but runtime only accepts bool
    clusterer = HDBSCAN(
        min_cluster_size=min_cluster_size,
        min_samples=min_samples,
        metric="cosine",
        copy=True,  # pyright: ignore[reportArgumentType]
    )

    labels = clusterer.fit_predict(embeddings)
    return labels


def find_representatives(
    embeddings: np.ndarray,
    labels: np.ndarray,
    n_per_cluster: int = 3,
) -> dict[int, list[int]]:
    """
    Find representative images for each cluster.

    A "representative" is an image that's close to the cluster's centroid —
    the average of all embeddings in the cluster. The image closest to the
    centroid is the most "typical" member of the group.

    We return multiple representatives per cluster (not just the centroid)
    to capture some diversity within the group. This is useful for Phase 2
    (VLM captioning) — captioning a few diverse examples gives a richer
    description than captioning only the most typical image.

    Args:
        embeddings: The full embedding matrix, shape (N, D).
        labels: Cluster labels from cluster_embeddings(), shape (N,).
        n_per_cluster: How many representatives to select per cluster.

    Returns:
        A dict mapping cluster_id → list of indices into the original
        embeddings array. Noise points (label = -1) are excluded.
    """
    representatives = {}
    unique_labels = set(labels)

    for label in unique_labels:
        # Skip noise points — they don't belong to any cluster.
        if label == -1:
            continue

        # Find all indices belonging to this cluster.
        mask = labels == label
        cluster_indices = np.where(mask)[0]
        cluster_vecs = embeddings[cluster_indices]

        # Compute the centroid: the element-wise average of all vectors
        # in the cluster. This represents the "center" of the group.
        centroid = cluster_vecs.mean(axis=0)

        # L2-normalize the centroid so we can use dot product as similarity.
        centroid = centroid / np.linalg.norm(centroid)

        # Compute cosine similarity between each cluster member and the
        # centroid. Since both are normalized, this is just a dot product.
        # Higher score = more similar to the centroid = more "typical."
        similarities = cluster_vecs @ centroid

        # Pick the top-N most typical members.
        n = min(n_per_cluster, len(cluster_indices))
        top_local_indices = np.argsort(similarities)[-n:][::-1]

        # Map back from local cluster indices to global indices.
        representatives[int(label)] = cluster_indices[top_local_indices].tolist()

    return representatives


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
