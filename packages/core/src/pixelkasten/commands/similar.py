"""
k-NN over the working library's embeddings.

``similar`` accepts a query path inside the working library and returns the
top-K nearest neighbors by cosine similarity. Embeddings are L2-normalized
at write time so cosine reduces to a dot product.

Both images and videos are eligible — each video is represented as the
L2-normalized mean of its sampled-frame embeddings, so videos can appear
in the top-K alongside images. If a query JPG doesn't surface a video
nearby, that's a content-similarity signal, not a capability gap.
"""

import os

import numpy as np

from pixelkasten.stores.embeddings import read_embeddings


def similar(query_path: str, library: str, k: int) -> list[dict]:
    """
    Return up to ``k`` nearest neighbors of ``query_path`` in ``library`` (by cosine).

    The query must already be in ``library``'s embeddings — call ``enrich``
    after importing it if not. Each item is ``{"path": <absolute path>,
    "score": <float>}`` sorted by score descending; the query itself is
    excluded.
    """
    if k < 1:
        raise ValueError("k must be >= 1")

    matrix, paths = read_embeddings(library)
    if matrix.size == 0:
        raise RuntimeError(f"No embeddings in {library}; run `pixelkasten enrich` first.")

    query_name = os.path.basename(query_path)
    if query_name not in paths:
        raise RuntimeError(
            f"{query_path} has no embedding in {library}; "
            "run `pixelkasten enrich` after importing it."
        )
    query_index = paths.index(query_name)
    query_vec = matrix[query_index]

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
