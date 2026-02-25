"""
Manifest I/O — read and write pipeline results to disk.

The manifest is the central data structure that flows through the pipeline,
similar to how the Node.js pipeline uses a manifest array enriched by each
stage. Here, the manifest is a JSON file containing per-image metadata:

- file path
- cluster assignment
- classification tags and scores
- representative status (is this image a cluster representative?)

Embeddings are stored separately in a .npy file (numpy's binary format)
because they're large (768 floats per image × thousands of images) and
don't need to be human-readable. The manifest JSON references the .npy
file so downstream tools can load embeddings if needed (e.g., for
similarity search or re-clustering with different parameters).
"""

import json
import numpy as np
from pathlib import Path


def write_manifest(
    output_dir: Path,
    image_paths: list[Path],
    embeddings: np.ndarray,
    labels: np.ndarray,
    classifications: list[list[tuple[str, float]]],
    representatives: dict[int, list[int]],
    failed_indices: list[int],
) -> Path:
    """
    Write pipeline results to disk.

    Creates two files in output_dir:
    - manifest.json: Per-image metadata (human-readable).
    - embeddings.npy: Raw embedding vectors (binary, for reuse).

    Args:
        output_dir: Directory to write files into. Created if it doesn't exist.
        image_paths: Original list of image paths that were scanned.
        embeddings: The (N, D) embedding matrix from embed_images().
            N may be less than len(image_paths) if some images failed.
        labels: Cluster labels from cluster_embeddings(), shape (N,).
        classifications: Per-image tag lists from classify().
        representatives: Dict of cluster_id → list of representative indices.
        failed_indices: Indices of images that failed to embed.

    Returns:
        Path to the written manifest.json file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # Build a set of representative indices for quick lookup.
    representative_set = set()
    for indices in representatives.values():
        representative_set.update(indices)

    # Build the manifest entries. We need to track two index spaces:
    # - "path_index": position in the original image_paths list.
    # - "embed_index": position in the embeddings array (skips failed images).
    #
    # Failed images are excluded from embeddings, so embed_index advances
    # only for successfully embedded images.
    failed_set = set(failed_indices)
    entries = []
    embed_index = 0

    for path_index, path in enumerate(image_paths):
        if path_index in failed_set:
            # Record the failure so the user knows which files were skipped.
            entries.append({
                "path": str(path),
                "status": "failed",
                "cluster": None,
                "tags": [],
                "is_representative": False,
            })
            continue

        # Build tag list: each tag is {name, score} for readability.
        tags = [
            {"name": name, "score": round(score, 4)}
            for name, score in classifications[embed_index]
        ]

        entries.append({
            "path": str(path),
            "status": "ok",
            "cluster": int(labels[embed_index]),
            "tags": tags,
            "is_representative": embed_index in representative_set,
        })

        embed_index += 1

    manifest = {
        "version": 1,
        "embeddings_file": "embeddings.npy",
        "total_images": len(image_paths),
        "embedded": len(image_paths) - len(failed_indices),
        "failed": len(failed_indices),
        "entries": entries,
    }

    manifest_path = output_dir / "manifest.json"
    embeddings_path = output_dir / "embeddings.npy"

    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    # Save embeddings in numpy's binary format. This is much more compact
    # than JSON and can be loaded back with np.load() for downstream use
    # (re-clustering, similarity search, etc.).
    if embeddings.size > 0:
        np.save(embeddings_path, embeddings)

    return manifest_path


def read_manifest(manifest_path: Path) -> dict:
    """
    Read a manifest.json file back into memory.

    Returns the parsed JSON as a dict. Use this to inspect results or
    feed the manifest into downstream tools (Phase 2 captioning, agent
    organization, etc.).
    """
    with open(manifest_path) as f:
        return json.load(f)


def load_embeddings(manifest_path: Path) -> np.ndarray:
    """
    Load the embeddings.npy file referenced by a manifest.

    Returns the (N, D) numpy array of embedding vectors.
    """
    manifest = read_manifest(manifest_path)
    embeddings_path = manifest_path.parent / manifest["embeddings_file"]
    return np.load(embeddings_path)
