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


def enrich_manifest(manifest_path: Path, captions: dict[str, str]) -> None:
    """
    Enrich an existing manifest with VLM captions and cluster summaries.

    Reads the manifest, adds a `caption` field to entries that were
    captioned, builds a top-level `clusters` summary aggregating captions
    and top tags per cluster, and writes the result back to disk.

    Args:
        manifest_path: Path to the manifest.json file.
        captions: Dict mapping image path → caption string,
            as returned by caption_representatives().
    """
    manifest = read_manifest(manifest_path)

    # Add captions to individual entries.
    for entry in manifest["entries"]:
        if entry["path"] in captions:
            entry["caption"] = captions[entry["path"]]

    # Update cluster summaries with captions. Preserve existing fields
    # (date_range, locations, cameras) that were set by enrich/refine.
    clusters = manifest.get("clusters", {})

    for key, cluster in clusters.items():
        # Rebuild captions and top_tags from entries (these change when
        # new captions are added), but keep other fields intact.
        cluster["captions"] = []
        cluster["top_tags"] = []
        cluster["size"] = 0

    for entry in manifest["entries"]:
        cluster_id = entry.get("cluster")
        if cluster_id is None or cluster_id == -1:
            continue

        key = str(cluster_id)
        if key not in clusters:
            clusters[key] = {
                "size": 0,
                "captions": [],
                "top_tags": [],
            }

        clusters[key]["size"] += 1

        if "caption" in entry:
            clusters[key]["captions"].append(entry["caption"])

        for tag in entry.get("tags", []):
            tag_name = tag["name"]
            if tag_name not in clusters[key]["top_tags"]:
                clusters[key]["top_tags"].append(tag_name)

    manifest["clusters"] = clusters

    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)


def enrich_manifest_exif(
    manifest_path: Path,
    exif_data: dict[str, dict],
    location_names: dict[str, str] | None = None,
) -> None:
    """
    Enrich an existing manifest with EXIF metadata and cluster date/location summaries.

    Reads the manifest, adds an `exif` field to entries that have EXIF data,
    enriches the `clusters` dict with date_range, locations, and cameras per
    cluster, and writes back to disk.

    Args:
        manifest_path: Path to manifest.json.
        exif_data: Dict mapping image path -> ExifData dict,
            as returned by read_exif_for_all().
        location_names: Optional dict mapping image path -> location name string
            (e.g., "San Francisco, California, US") from reverse geocoding.
    """
    location_names = location_names or {}
    manifest = read_manifest(manifest_path)

    # Add EXIF data and location names to individual entries.
    for entry in manifest["entries"]:
        if entry["path"] in exif_data:
            entry["exif"] = exif_data[entry["path"]]
        if entry["path"] in location_names:
            if "exif" not in entry:
                entry["exif"] = {}
            entry["exif"]["location_name"] = location_names[entry["path"]]

    # Enrich cluster summaries with date ranges, locations, and cameras.
    clusters = manifest.get("clusters", {})
    for key, cluster in clusters.items():
        timestamps = []
        locations = []
        cameras = []

        # Scan entries belonging to this cluster for EXIF data.
        for entry in manifest["entries"]:
            if str(entry.get("cluster")) != key:
                continue
            exif = entry.get("exif")
            if exif is None:
                continue

            if exif.get("timestamp"):
                timestamps.append(exif["timestamp"])
            if exif.get("gps"):
                # Deduplicate by rounding to 2 decimal places (~1km precision).
                rounded = (
                    round(exif["gps"]["latitude"], 2),
                    round(exif["gps"]["longitude"], 2),
                )
                if rounded not in [(loc["latitude"], loc["longitude"]) for loc in locations]:
                    locations.append({
                        "latitude": rounded[0],
                        "longitude": rounded[1],
                    })
            if exif.get("camera") and exif["camera"] not in cameras:
                cameras.append(exif["camera"])

        if timestamps:
            timestamps.sort()
            cluster["date_range"] = {
                "earliest": timestamps[0],
                "latest": timestamps[-1],
            }
        if locations:
            cluster["locations"] = locations
        if cameras:
            cluster["cameras"] = cameras

        # Collect unique location names for this cluster.
        cluster_location_names = []
        for entry in manifest["entries"]:
            if str(entry.get("cluster")) != key:
                continue
            loc_name = entry.get("exif", {}).get("location_name")
            if loc_name and loc_name not in cluster_location_names:
                cluster_location_names.append(loc_name)
        if cluster_location_names:
            cluster["location_names"] = cluster_location_names

    manifest["clusters"] = clusters

    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)


def update_manifest_clusters(
    manifest_path: Path,
    labels: "np.ndarray",
    representatives: dict[int, list[int]],
) -> None:
    """
    Overwrite cluster assignments and representatives in the manifest.

    Used after the refine step to update the manifest with new cluster
    IDs and re-selected representatives. Rebuilds the clusters summary
    (size, captions, top_tags, date_range, locations, cameras) from
    the updated assignments.

    Args:
        manifest_path: Path to manifest.json.
        labels: New cluster labels array, shape (N,) where N is the
            number of ok-status entries.
        representatives: New representative indices per cluster,
            as returned by find_representatives().
    """
    manifest = read_manifest(manifest_path)

    # Build a set of representative indices for quick lookup.
    representative_set = set()
    for indices in representatives.values():
        representative_set.update(indices)

    # Update entries with new cluster IDs and representative flags.
    embed_index = 0
    for entry in manifest["entries"]:
        if entry.get("status") != "ok":
            continue
        entry["cluster"] = int(labels[embed_index])
        entry["is_representative"] = embed_index in representative_set
        # Clear stale captions — representatives may have changed.
        if "caption" in entry and not entry["is_representative"]:
            del entry["caption"]
        embed_index += 1

    # Rebuild clusters summary from updated assignments.
    clusters: dict[str, dict] = {}
    for entry in manifest["entries"]:
        cluster_id = entry.get("cluster")
        if cluster_id is None or cluster_id == -1:
            continue

        key = str(cluster_id)
        if key not in clusters:
            clusters[key] = {
                "size": 0,
                "captions": [],
                "top_tags": [],
            }

        clusters[key]["size"] += 1

        if "caption" in entry:
            clusters[key]["captions"].append(entry["caption"])

        for tag in entry.get("tags", []):
            tag_name = tag["name"]
            if tag_name not in clusters[key]["top_tags"]:
                clusters[key]["top_tags"].append(tag_name)

        # EXIF enrichment for cluster summaries.
        exif = entry.get("exif")
        if exif:
            if exif.get("timestamp"):
                if "timestamps" not in clusters[key]:
                    clusters[key]["timestamps"] = []
                clusters[key]["timestamps"].append(exif["timestamp"])
            if exif.get("gps"):
                if "locations" not in clusters[key]:
                    clusters[key]["locations"] = []
                rounded = (
                    round(exif["gps"]["latitude"], 2),
                    round(exif["gps"]["longitude"], 2),
                )
                existing = [(loc["latitude"], loc["longitude"]) for loc in clusters[key]["locations"]]
                if rounded not in existing:
                    clusters[key]["locations"].append({
                        "latitude": rounded[0],
                        "longitude": rounded[1],
                    })
            if exif.get("camera"):
                if "cameras" not in clusters[key]:
                    clusters[key]["cameras"] = []
                if exif["camera"] not in clusters[key]["cameras"]:
                    clusters[key]["cameras"].append(exif["camera"])

    # Convert timestamp lists to date ranges and remove the temp field.
    for cluster in clusters.values():
        ts_list = cluster.pop("timestamps", [])
        if ts_list:
            ts_list.sort()
            cluster["date_range"] = {
                "earliest": ts_list[0],
                "latest": ts_list[-1],
            }

    manifest["clusters"] = clusters

    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)


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
