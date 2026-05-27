"""
CLIP embeddings store — path helpers and the shared loader.

The on-disk artifacts (``embeddings.npy`` + ``embeddings.paths.json``)
live inside each working library's records directory. This module owns
both the path-building helpers that locate them and the loader that
``similar`` and ``cluster`` use to require them. The L2-normalization
invariant is documented here in exactly one place.
"""

import json
import os
from typing import Literal, overload

import numpy as np

from pixelkasten.configuration import EMBEDDINGS_NPY, EMBEDDINGS_PATHS_JSON, RECORDS_DIR


def embeddings_npy_path(library: str) -> str:
    return os.path.join(library, RECORDS_DIR, EMBEDDINGS_NPY)


def embeddings_paths_json_path(library: str) -> str:
    return os.path.join(library, RECORDS_DIR, EMBEDDINGS_PATHS_JSON)


@overload
def load_embeddings(library: str, strict: Literal[True] = True) -> tuple[np.ndarray, list[str]]: ...


@overload
def load_embeddings(
    library: str, strict: Literal[False]
) -> tuple[np.ndarray | None, list[str]]: ...


def load_embeddings(library: str, strict: bool = True) -> tuple[np.ndarray | None, list[str]]:
    """Load embeddings, optionally allowing a missing store."""
    npy_file = embeddings_npy_path(library)
    paths_file = embeddings_paths_json_path(library)
    has_npy = os.path.exists(npy_file)
    has_paths = os.path.exists(paths_file)
    if not has_npy and not has_paths:
        if strict:
            raise RuntimeError(f"No embeddings in {library}; run `pixelkasten enrich` first.")
        return None, []
    if has_npy != has_paths:
        raise RuntimeError(
            f"Incomplete embeddings store in {library}; expected both "
            f"{EMBEDDINGS_NPY} and {EMBEDDINGS_PATHS_JSON}."
        )
    return _load_files(npy_file, paths_file)


def save_embeddings(library: str, matrix: np.ndarray, paths: list[str]) -> None:
    """Persist embeddings.npy and paths.json after checking row alignment."""
    if matrix.shape[0] != len(paths):
        raise RuntimeError(
            f"Embeddings row count ({matrix.shape[0]}) doesn't match paths list ({len(paths)})."
        )

    np.save(embeddings_npy_path(library), matrix)
    with open(embeddings_paths_json_path(library), "w") as f:
        json.dump(paths, f)


def _load_files(npy_file: str, paths_file: str) -> tuple[np.ndarray, list[str]]:
    """Load embeddings.npy + paths.json. Rows are assumed L2-normalized
    (writers in utils/clip.py and commands/enrich.py uphold this);
    cosine similarity downstream reduces to a plain dot product."""
    matrix = np.load(npy_file)
    with open(paths_file) as f:
        paths = json.load(f)
    if matrix.shape[0] != len(paths):
        raise RuntimeError(
            f"Embeddings file shape ({matrix.shape[0]}) doesn't match paths list ({len(paths)})."
        )
    return matrix, paths
