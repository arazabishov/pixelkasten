"""
CLIP embeddings store — path helpers and the shared loader.

The on-disk artifacts (``embeddings.npy`` + ``embeddings.paths.json``)
live inside each working library's records directory. This module owns
both the path-building helpers that locate them and the loader that
``similar`` and ``cluster`` use to read them. The L2-normalization
invariant is documented here in exactly one place.
"""

import json
import os

import numpy as np

from pixelkasten.configuration import EMBEDDINGS_NPY, EMBEDDINGS_PATHS_JSON, RECORDS_DIR


def embeddings_npy_path(library: str) -> str:
    return os.path.join(library, RECORDS_DIR, EMBEDDINGS_NPY)


def embeddings_paths_json_path(library: str) -> str:
    return os.path.join(library, RECORDS_DIR, EMBEDDINGS_PATHS_JSON)


def load_embeddings(library: str) -> tuple[np.ndarray, list[str]]:
    """Load embeddings.npy + paths.json. Rows are assumed L2-normalized
    (writers in utils/clip.py and commands/enrich.py uphold this);
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
