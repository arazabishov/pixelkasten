"""
Shared loader for ``embeddings.npy`` + ``embeddings.paths.json``.

Consolidates the helper that both ``similar`` and ``cluster`` use to read
the embeddings store; keeps the L2-normalization invariant documented in
exactly one place.
"""

import json
import os

import numpy as np

from pixelkasten.layout import embeddings_npy_path, embeddings_paths_json_path


def load_embeddings(library: str) -> tuple[np.ndarray, list[str]]:
    """Load embeddings.npy + paths.json. Rows are assumed L2-normalized
    (writers in utils/clip_embed.py and commands/enrich.py uphold this);
    cosine similarity downstream reduces to a plain dot product."""
    npy_file = embeddings_npy_path(library)
    paths_file = embeddings_paths_json_path(library)
    if not os.path.exists(npy_file) or not os.path.exists(paths_file):
        raise RuntimeError(f"No embeddings in {library}; run `pixelkasten enrich` first.")
    matrix = np.load(npy_file)
    with open(paths_file) as f:
        paths = json.load(f)
    if matrix.shape[0] != len(paths):
        raise RuntimeError(
            f"Embeddings file shape ({matrix.shape[0]}) doesn't match paths list ({len(paths)})."
        )
    return matrix, paths
