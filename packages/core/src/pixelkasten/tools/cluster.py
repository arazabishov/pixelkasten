"""
HDBSCAN over a scoped slice of `embeddings.npy`.

The agent uses `cluster` to group a candidate set of photos (e.g., all photos
within a region or a date range) without applying clustering to the whole
library at once. The function takes the explicit list of paths and returns a
label -> list-of-paths map. Paths not present in `embeddings.paths.json` are
warned about on stderr and dropped from the result.
"""

import json
import os
import sys

import numpy as np

SIDECAR_DIR = ".pixelkasten"
EMBEDDINGS_NPY = "embeddings.npy"
EMBEDDINGS_PATHS_JSON = "embeddings.paths.json"


def cluster(paths: list[str], library: str, min_cluster_size: int) -> dict[int, list[str]]:
    """
    Run HDBSCAN on the embeddings for `paths`. Returns {label: [path, ...]}.

    The cluster label `-1` is HDBSCAN's noise bucket; other labels are
    arbitrary non-negative integers without semantic meaning.
    """
    if min_cluster_size < 2:
        raise ValueError("min_cluster_size must be >= 2")
    if not paths:
        return {}

    matrix, all_paths = _load_embeddings(library)
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


def _load_embeddings(library: str) -> tuple[np.ndarray, list[str]]:
    npy_file = os.path.join(library, SIDECAR_DIR, EMBEDDINGS_NPY)
    paths_file = os.path.join(library, SIDECAR_DIR, EMBEDDINGS_PATHS_JSON)
    if not os.path.exists(npy_file) or not os.path.exists(paths_file):
        raise RuntimeError(f"No embeddings in {library}; run `pixelkasten enrich` first.")
    matrix = np.load(npy_file)
    with open(paths_file) as f:
        paths = json.load(f)
    return matrix, paths
