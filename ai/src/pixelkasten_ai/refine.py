"""
Cluster refinement — improve cluster quality using EXIF timestamps.

After HDBSCAN groups images by visual similarity (Phase 1) and EXIF
timestamps are read (enrich), this module refines the clusters:

1. **Split** clusters that span different time periods. If a cluster has
   a temporal gap > 48 hours between consecutive photos, it likely
   contains images from different events that just look similar.

2. **Merge** clusters that are temporally close and visually similar.
   If two clusters are from the same day and their centroids have high
   cosine similarity, they're likely the same event that HDBSCAN over-split.

This addresses two real-world quality issues:
- "Beach in Turkey 2017" grouped with "Beach in Greece 2023" (needs split)
- "Go-Karting Adventure" and "Indoor Go-Karting" as separate albums (needs merge)
"""

import numpy as np
from datetime import datetime


def refine_clusters(
    manifest: dict,
    embeddings: np.ndarray,
    split_gap_hours: float = 48.0,
    merge_similarity: float = 0.5,
    merge_time_hours: float = 24.0,
) -> tuple[np.ndarray, dict]:
    """
    Refine cluster assignments using EXIF timestamps and embedding similarity.

    1. Split clusters with temporal gaps > split_gap_hours.
    2. Merge clusters that are temporally close (< merge_time_hours)
       AND have centroid cosine similarity > merge_similarity.

    Args:
        manifest: Parsed manifest dict (must have EXIF data from enrich step).
        embeddings: The (N, D) embedding matrix from embeddings.npy.
        split_gap_hours: Minimum hours gap to trigger a cluster split.
        merge_similarity: Minimum centroid cosine similarity to merge clusters.
        merge_time_hours: Maximum hours apart for clusters to be merge candidates.

    Returns:
        Tuple of (new_labels, stats) where:
        - new_labels: np.ndarray of shape (N,) with refined cluster IDs.
        - stats: dict with "splits" and "merges" counts.
    """
    # Build a mapping from embed_index → timestamp for all ok-status entries.
    # This mirrors the two-index-space logic in manifest.py: failed entries
    # don't appear in embeddings, so embed_index skips them.
    timestamps = {}
    embed_index = 0
    for entry in manifest["entries"]:
        if entry.get("status") != "ok":
            continue
        exif = entry.get("exif")
        if exif and exif.get("timestamp"):
            timestamps[embed_index] = exif["timestamp"]
        embed_index += 1

    # Extract current labels from manifest.
    labels = _extract_labels(manifest)

    # Step 1: Split clusters with temporal gaps.
    labels, n_splits = _split_by_temporal_gaps(labels, timestamps, split_gap_hours)

    # Step 2: Merge temporally close, visually similar clusters.
    labels, n_merges = _merge_similar_clusters(
        labels, embeddings, timestamps, merge_similarity, merge_time_hours,
    )

    # Re-number labels to be contiguous (0, 1, 2, ...) with -1 preserved.
    labels = _renumber_labels(labels)

    stats = {
        "splits": n_splits,
        "merges": n_merges,
    }

    return labels, stats


def _extract_labels(manifest: dict) -> np.ndarray:
    """Extract cluster labels from manifest entries into an array matching embeddings shape."""
    labels = []
    for entry in manifest["entries"]:
        if entry.get("status") != "ok":
            continue
        cluster = entry.get("cluster")
        labels.append(cluster if cluster is not None else -1)
    return np.array(labels, dtype=int)


def _parse_timestamp(ts: str | None) -> datetime | None:
    """Parse an ISO 8601 timestamp string to datetime. Returns None on failure."""
    if not ts:
        return None
    try:
        # Handle "YYYY-MM-DDTHH:MM:SS" with optional timezone.
        # Strip timezone for naive comparison (we only care about gaps).
        clean = ts[:19]
        return datetime.strptime(clean, "%Y-%m-%dT%H:%M:%S")
    except (ValueError, IndexError):
        return None


def _split_by_temporal_gaps(
    labels: np.ndarray,
    timestamps: dict[int, str],
    gap_hours: float,
) -> tuple[np.ndarray, int]:
    """
    Split clusters at temporal gaps.

    For each cluster, sorts its members by timestamp and looks for gaps
    larger than gap_hours. Each gap creates a new sub-cluster.

    Returns (new_labels, split_count).
    """
    new_labels = labels.copy()
    next_id = labels.max() + 1 if len(labels) > 0 else 0
    split_count = 0

    unique_clusters = set(labels)
    for cluster_id in unique_clusters:
        if cluster_id == -1:
            continue

        # Get indices and their timestamps for this cluster.
        mask = labels == cluster_id
        indices = np.where(mask)[0]

        # Collect (index, parsed_datetime) pairs, skip entries without timestamps.
        timed = []
        for idx in indices:
            ts = timestamps.get(int(idx))
            dt = _parse_timestamp(ts)
            if dt is not None:
                timed.append((int(idx), dt))

        # If fewer than 2 entries have timestamps, can't detect gaps.
        if len(timed) < 2:
            continue

        # Sort by timestamp.
        timed.sort(key=lambda x: x[1])

        # Find gap positions.
        gap_seconds = gap_hours * 3600
        split_points = []
        for i in range(1, len(timed)):
            delta = (timed[i][1] - timed[i - 1][1]).total_seconds()
            if delta > gap_seconds:
                split_points.append(i)

        if not split_points:
            continue

        # Split: first segment keeps the original cluster_id, subsequent
        # segments get new IDs. Images without timestamps stay with the
        # original cluster.
        segments = []
        prev = 0
        for sp in split_points:
            segments.append([t[0] for t in timed[prev:sp]])
            prev = sp
        segments.append([t[0] for t in timed[prev:]])

        # First segment keeps original ID. Rest get new IDs.
        for segment in segments[1:]:
            for idx in segment:
                new_labels[idx] = next_id
            next_id += 1
            split_count += 1

    return new_labels, split_count


def _merge_similar_clusters(
    labels: np.ndarray,
    embeddings: np.ndarray,
    timestamps: dict[int, str],
    similarity_threshold: float,
    time_threshold_hours: float,
) -> tuple[np.ndarray, int]:
    """
    Merge clusters that are temporally close and visually similar.

    For each pair of clusters, checks if their date ranges are within
    time_threshold_hours of each other AND their centroid cosine similarity
    exceeds similarity_threshold. If both conditions are met, merges them.

    Returns (new_labels, merge_count).
    """
    new_labels = labels.copy()
    merge_count = 0
    time_threshold_seconds = time_threshold_hours * 3600

    # Build per-cluster info: centroid and time range.
    cluster_info = {}
    unique_clusters = [c for c in set(new_labels) if c != -1]

    for cluster_id in unique_clusters:
        mask = new_labels == cluster_id
        indices = np.where(mask)[0]
        cluster_vecs = embeddings[indices]

        # Compute L2-normalized centroid.
        centroid = cluster_vecs.mean(axis=0)
        norm = np.linalg.norm(centroid)
        if norm > 0:
            centroid = centroid / norm

        # Collect timestamps for this cluster.
        dts = []
        for idx in indices:
            dt = _parse_timestamp(timestamps.get(int(idx)))
            if dt is not None:
                dts.append(dt)

        cluster_info[cluster_id] = {
            "centroid": centroid,
            "min_time": min(dts) if dts else None,
            "max_time": max(dts) if dts else None,
        }

    # Check all pairs for merge candidates. Use a union-find approach:
    # iteratively merge until no more merges are possible.
    merged = True
    while merged:
        merged = False
        current_ids = sorted([c for c in set(new_labels) if c != -1])

        for i, id_a in enumerate(current_ids):
            if id_a not in cluster_info:
                continue
            for id_b in current_ids[i + 1:]:
                if id_b not in cluster_info:
                    continue

                info_a = cluster_info[id_a]
                info_b = cluster_info[id_b]

                # Check temporal proximity.
                if not _temporally_close(info_a, info_b, time_threshold_seconds):
                    continue

                # Check visual similarity.
                similarity = float(info_a["centroid"] @ info_b["centroid"])
                if similarity < similarity_threshold:
                    continue

                # Merge: reassign id_b → id_a.
                new_labels[new_labels == id_b] = id_a

                # Recompute centroid for the merged cluster.
                mask = new_labels == id_a
                merged_vecs = embeddings[mask]
                new_centroid = merged_vecs.mean(axis=0)
                norm = np.linalg.norm(new_centroid)
                if norm > 0:
                    new_centroid = new_centroid / norm

                # Update cluster info.
                cluster_info[id_a] = {
                    "centroid": new_centroid,
                    "min_time": _safe_min(info_a["min_time"], info_b["min_time"]),
                    "max_time": _safe_max(info_a["max_time"], info_b["max_time"]),
                }
                del cluster_info[id_b]

                merge_count += 1
                merged = True
                break

            if merged:
                break

    return new_labels, merge_count


def _temporally_close(info_a: dict, info_b: dict, threshold_seconds: float) -> bool:
    """
    Check if two clusters are temporally close.

    Returns True if their date ranges overlap or are within threshold_seconds
    of each other. If either cluster has no timestamps, returns False (can't
    determine temporal proximity, so don't merge).
    """
    if info_a["min_time"] is None or info_b["min_time"] is None:
        return False

    # Check if ranges overlap.
    if info_a["min_time"] <= info_b["max_time"] and info_b["min_time"] <= info_a["max_time"]:
        return True

    # Check gap between ranges.
    if info_a["max_time"] < info_b["min_time"]:
        gap = (info_b["min_time"] - info_a["max_time"]).total_seconds()
    else:
        gap = (info_a["min_time"] - info_b["max_time"]).total_seconds()

    return gap <= threshold_seconds


def _safe_min(a, b):
    """Return the minimum of two values, handling None."""
    if a is None:
        return b
    if b is None:
        return a
    return min(a, b)


def _safe_max(a, b):
    """Return the maximum of two values, handling None."""
    if a is None:
        return b
    if b is None:
        return a
    return max(a, b)


def _renumber_labels(labels: np.ndarray) -> np.ndarray:
    """
    Renumber cluster labels to be contiguous (0, 1, 2, ...).

    Preserves -1 as noise. This makes the labels cleaner after
    splits and merges create gaps in the numbering.
    """
    new_labels = labels.copy()
    unique_ids = sorted(set(labels))

    next_id = 0
    for old_id in unique_ids:
        if old_id == -1:
            continue
        new_labels[labels == old_id] = next_id
        next_id += 1

    return new_labels
