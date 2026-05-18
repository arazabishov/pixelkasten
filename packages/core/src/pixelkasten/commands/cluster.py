"""
HDBSCAN over a scoped slice of ``embeddings.npy``.

The agent uses ``cluster`` to group a candidate set of photos (e.g., all
photos within a region or a date range) without applying clustering to the
whole library at once. The function takes the explicit list of paths and
returns a label -> list-of-paths map. Paths not present in
``embeddings.paths.json`` are warned about on stderr and dropped from the
result.
"""

import os
import sys

from pixelkasten.utils.embeddings import load_embeddings


def cluster(paths: list[str], library: str, min_cluster_size: int) -> dict[int, list[str]]:
    """
    Run HDBSCAN on the embeddings for ``paths``. Returns {label: [path, ...]}.

    Uses cosine distance. Rows are assumed L2-normalized (writers in
    utils/clip.py and commands/enrich.py uphold this); cosine distance
    reduces to 1 - dot_product, consistent with how ``similar`` scores results.

    Both images and videos are eligible — each video is represented as the
    L2-normalized mean of its sampled-frame embeddings, so videos appear
    in the result alongside images.

    The cluster label ``-1`` is HDBSCAN's noise bucket — paths that didn't
    cluster with anything else. Other labels are arbitrary non-negative
    integers without semantic meaning.
    """
    if min_cluster_size < 2:
        raise ValueError("min_cluster_size must be >= 2")
    if not paths:
        return {}

    matrix, all_paths = load_embeddings(library)
    index_by_name = {name: i for i, name in enumerate(all_paths)}

    requested_rows: list[int] = []
    matched_paths: list[str] = []
    for p in paths:
        name = os.path.basename(p)
        idx = index_by_name.get(name)
        if idx is None:
            print(f"cluster: {p} has no embedding; skipping.", file=sys.stderr)
            continue
        requested_rows.append(idx)
        matched_paths.append(p)

    if not matched_paths:
        return {}

    submatrix = matrix[requested_rows]

    from sklearn.cluster import HDBSCAN

    labels = HDBSCAN(min_cluster_size=min_cluster_size, metric="cosine").fit_predict(submatrix)

    grouped: dict[int, list[str]] = {}
    for label, p in zip(labels, matched_paths):
        grouped.setdefault(int(label), []).append(p)
    return grouped
