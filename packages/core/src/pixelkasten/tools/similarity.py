"""
k-NN over the working library's embeddings.

`similar` accepts a query path (a file inside the working library, or any
external file) and returns the top-K nearest neighbors by cosine similarity.
Embeddings are L2-normalized at write time so cosine reduces to a dot product.
"""

import json
import os

import numpy as np

SIDECAR_DIR = ".pixelkasten"
EMBEDDINGS_NPY = "embeddings.npy"
EMBEDDINGS_PATHS_JSON = "embeddings.paths.json"


def resolve_library(query_path: str) -> str:
    """Walk up from `query_path` until a directory containing `.pixelkasten/` is found."""
    current = os.path.abspath(query_path)
    if os.path.isfile(current):
        current = os.path.dirname(current)
    while True:
        if os.path.isdir(os.path.join(current, SIDECAR_DIR)):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            raise RuntimeError(
                f"No .pixelkasten/ found at or above {query_path}; pass --library explicitly."
            )
        current = parent


def similar(query_path: str, library: str, k: int) -> list[dict]:
    """
    Return up to `k` nearest neighbors of `query_path` in `library` (by cosine).

    Each item is `{"path": <absolute path>, "score": <float>}` sorted by
    score descending. The query itself is excluded when it's part of the
    library's embeddings.
    """
    if k < 1:
        raise ValueError("k must be >= 1")

    matrix, paths = _load_embeddings(library)
    if matrix.size == 0:
        raise RuntimeError(f"No embeddings in {library}; run `pixelkasten enrich` first.")

    query_name = os.path.basename(query_path)
    query_index = paths.index(query_name) if query_name in paths else None

    if query_index is not None:
        query_vec = matrix[query_index]
    else:
        query_vec = _embed_external(query_path)

    scores = matrix @ query_vec
    # argsort returns ascending; flip to descending.
    order = np.argsort(-scores)

    results: list[dict] = []
    for idx in order:
        if int(idx) == query_index:
            continue
        results.append(
            {"path": os.path.join(library, paths[int(idx)]), "score": float(scores[int(idx)])}
        )
        if len(results) >= k:
            break
    return results


def _load_embeddings(library: str) -> tuple[np.ndarray, list[str]]:
    npy_file = os.path.join(library, SIDECAR_DIR, EMBEDDINGS_NPY)
    paths_file = os.path.join(library, SIDECAR_DIR, EMBEDDINGS_PATHS_JSON)
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


def _embed_external(query_path: str) -> np.ndarray:
    """Embed an arbitrary file (not in the library) with the same CLIP model."""
    from PIL import Image

    from pixelkasten.tools.clip_embed import embed_images
    from pixelkasten.tools.pil_setup import ensure_pil_plugins

    ensure_pil_plugins()
    img = Image.open(query_path)
    matrix = embed_images([img])
    if matrix.size == 0:
        raise RuntimeError(f"Could not embed query {query_path}")
    return matrix[0]
