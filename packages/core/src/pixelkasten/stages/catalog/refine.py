"""
Cluster refinement — Phase 2b of the AI pipeline.

After HDBSCAN groups images by visual similarity (Phase 1) and EXIF
timestamps are read (enrich), this module refines the clusters:

1. **Eject** images with no EXIF metadata from clusters — these were
   placed purely by visual similarity and are the most error-prone.

2. **Split** clusters that span different time periods. If a cluster has
   a temporal gap > 48 hours between consecutive photos, it likely
   contains images from different events that just look similar.

3. **Merge** clusters that are temporally close and visually similar.
   If two clusters are from the same day and their centroids have high
   cosine similarity, they're likely the same event that HDBSCAN over-split.

4. **Absorb** noise images into clusters when they share a non-home
   location and overlapping dates. Travel photos that HDBSCAN missed
   (e.g., a food photo in San Francisco) get placed into the right trip
   album. Home-location images are not absorbed since location alone is
   too ambiguous.
"""

import numpy as np
from datetime import datetime


def refine_clusters(
    manifest: dict,
    embeddings: np.ndarray,
    split_gap_hours: float = 48.0,
    merge_similarity: float = 0.5,
    merge_time_hours: float = 168.0,
) -> tuple[np.ndarray, dict]:
    """
    Refine cluster assignments using EXIF timestamps and embedding similarity.

    1. Eject images with no EXIF metadata from clusters.
    2. Split clusters with temporal gaps > split_gap_hours.
    3. Merge clusters that are temporally close (< merge_time_hours)
       AND have centroid cosine similarity > merge_similarity.
       Clusters that share a location (city) get a lower similarity
       threshold (0.3) since same-city + same-week is a strong signal.
    4. Absorb noise images into clusters when they share a non-home
       location and overlapping dates.

    Args:
        manifest: Parsed manifest dict (must have EXIF data from enrich step).
        embeddings: The (N, D) embedding matrix from embeddings.npy.
        split_gap_hours: Minimum hours gap to trigger a cluster split.
        merge_similarity: Minimum centroid cosine similarity to merge clusters.
        merge_time_hours: Maximum hours apart for clusters to be merge candidates.

    Returns:
        Tuple of (new_labels, stats) where:
        - new_labels: np.ndarray of shape (N,) with refined cluster IDs.
        - stats: dict with counts for each operation.
    """
    # Build mappings from embed_index → metadata.
    # Failed entries don't appear in embeddings, so embed_index skips them.
    #
    # Timestamps come from metadata.dates (populated by reconcile).
    # Locations come from entry["location"]["region"] (populated by reverse_geocode).
    from pixelkasten.core.types import Status

    timestamps = {}
    regions = {}
    has_metadata = {}
    embed_index = 0
    for entry in manifest["entries"]:
        if not entry.catalog or entry.catalog.status != Status.PROCESSED:
            continue
        dates = entry.metadata.dates if entry.metadata else []
        has_metadata[embed_index] = bool(dates)
        if dates:
            timestamps[embed_index] = dates[0]
        if entry.location and entry.location.region:
            regions[embed_index] = entry.location.region
        embed_index += 1

    # Extract current labels from manifest.
    labels = _extract_labels(manifest)

    # Step 1: Eject images with no EXIF metadata from clusters.
    labels, n_ejected = _eject_metadataless(labels, has_metadata)

    # Step 2: Split clusters with temporal gaps.
    labels, n_splits = _split_by_temporal_gaps(labels, timestamps, split_gap_hours)

    # Step 3: Merge temporally close, visually similar clusters.
    labels, n_merges = _merge_similar_clusters(
        labels,
        embeddings,
        timestamps,
        merge_similarity,
        merge_time_hours,
        locations=regions,
    )

    # Step 4: Absorb noise images into clusters by time + non-home region.
    home_region = _infer_home_location(regions)
    labels, n_absorbed_loc = _absorb_noise_by_location(
        labels,
        timestamps,
        regions,
        home_region,
    )

    # Step 5: Absorb GPS-less noise images by time + visual similarity.
    # Images with timestamps but no GPS can't be matched by location.
    # If their timestamp falls within a cluster's date range AND they're
    # visually similar to the cluster centroid, absorb them.
    labels, n_absorbed_vis = _absorb_noise_by_similarity(
        labels,
        embeddings,
        timestamps,
        regions,
    )

    # Re-number labels to be contiguous (0, 1, 2, ...) with -1 preserved.
    labels = _renumber_labels(labels)

    stats = {
        "ejected": n_ejected,
        "splits": n_splits,
        "merges": n_merges,
        "absorbed_by_location": n_absorbed_loc,
        "absorbed_by_similarity": n_absorbed_vis,
        "home_location": home_region,
    }

    return labels, stats


def _extract_labels(manifest: dict) -> np.ndarray:
    """Extract cluster labels from manifest entries into an array matching embeddings shape."""
    from pixelkasten.core.types import Status

    labels = []
    for entry in manifest["entries"]:
        if not entry.catalog or entry.catalog.status != Status.PROCESSED:
            continue
        cluster = entry.catalog.cluster
        labels.append(cluster if cluster is not None else -1)
    return np.array(labels, dtype=int)


def _eject_metadataless(
    labels: np.ndarray,
    has_metadata: dict[int, bool],
) -> tuple[np.ndarray, int]:
    """
    Eject images with no metadata from clusters.

    Images without any date metadata were placed in clusters purely by
    visual similarity. These are the most error-prone assignments (e.g.,
    a WhatsApp portrait ending up in a Golden Gate Bridge album). Move
    them to noise (-1).

    Returns (new_labels, eject_count).
    """
    new_labels = labels.copy()
    eject_count = 0

    for idx in range(len(new_labels)):
        if new_labels[idx] == -1:
            continue
        if not has_metadata.get(idx, False):
            new_labels[idx] = -1
            eject_count += 1

    return new_labels, eject_count


def _infer_home_location(locations: dict[int, str]) -> str | None:
    """
    Infer the user's home location from the most frequent city in the library.

    The home location is used to avoid absorbing noise images into clusters
    just because they share the same city. Travel photos (rare locations)
    are strong signals; home photos (frequent location) are not.

    Returns the most common location name, or None if no GPS data.
    """
    if not locations:
        return None

    from collections import Counter

    counts = Counter(locations.values())
    most_common = counts.most_common(1)[0]

    # Only consider it "home" if it appears significantly more than others.
    # If the top location has fewer than 5 images, there's no clear home.
    if most_common[1] < 5:
        return None

    return most_common[0]


def _absorb_noise_by_location(
    labels: np.ndarray,
    timestamps: dict[int, str],
    locations: dict[int, str],
    home_location: str | None,
) -> tuple[np.ndarray, int]:
    """
    Absorb noise images into clusters when they share a non-home location
    and overlapping dates.

    For each noise image that has both a timestamp and a non-home location,
    find clusters whose date range overlaps and that share the same location.
    If exactly one cluster matches, absorb the image into it.

    This catches travel photos that HDBSCAN missed visually (e.g., a food
    photo taken in San Francisco during a Golden Gate Bridge trip).

    Returns (new_labels, absorb_count).
    """
    new_labels = labels.copy()
    absorb_count = 0

    # Build per-cluster info: date range and locations.
    cluster_info = {}
    for idx in range(len(new_labels)):
        cid = new_labels[idx]
        if cid == -1:
            continue

        if cid not in cluster_info:
            cluster_info[cid] = {
                "min_time": None,
                "max_time": None,
                "locations": set(),
            }

        dt = _parse_timestamp(timestamps.get(idx))
        if dt is not None:
            if cluster_info[cid]["min_time"] is None or dt < cluster_info[cid]["min_time"]:
                cluster_info[cid]["min_time"] = dt
            if cluster_info[cid]["max_time"] is None or dt > cluster_info[cid]["max_time"]:
                cluster_info[cid]["max_time"] = dt

        loc = locations.get(idx)
        if loc:
            cluster_info[cid]["locations"].add(loc)

    # Scan noise images for absorption candidates.
    for idx in range(len(new_labels)):
        if new_labels[idx] != -1:
            continue

        ts = timestamps.get(idx)
        loc = locations.get(idx)

        # Need both timestamp and location to absorb.
        if not ts or not loc:
            continue

        # Skip home location — too ambiguous.
        if home_location and loc == home_location:
            continue

        dt = _parse_timestamp(ts)
        if dt is None:
            continue

        # Find clusters that match on location and date range.
        candidates = []
        for cid, info in cluster_info.items():
            if loc not in info["locations"]:
                continue
            if info["min_time"] is None:
                continue
            # Check if the image's date falls within the cluster's range
            # (with a 24-hour buffer on each side).
            buffer = 24 * 3600
            min_dt = info["min_time"]
            max_dt = info["max_time"]
            img_ts = dt.timestamp()
            if (min_dt.timestamp() - buffer) <= img_ts <= (max_dt.timestamp() + buffer):
                candidates.append(cid)

        # Only absorb if exactly one cluster matches (unambiguous).
        if len(candidates) == 1:
            new_labels[idx] = candidates[0]
            # Update cluster info with the new image's data.
            cid = candidates[0]
            if dt < cluster_info[cid]["min_time"]:
                cluster_info[cid]["min_time"] = dt
            if dt > cluster_info[cid]["max_time"]:
                cluster_info[cid]["max_time"] = dt
            absorb_count += 1

    return new_labels, absorb_count


def _absorb_noise_by_similarity(
    labels: np.ndarray,
    embeddings: np.ndarray,
    timestamps: dict[int, str],
    locations: dict[int, str],
    similarity_threshold: float = 0.5,
) -> tuple[np.ndarray, int]:
    """
    Absorb GPS-less noise images into clusters by time + visual similarity.

    For noise images that have a timestamp but NO GPS data, check if their
    timestamp falls within a cluster's date range. If it does, compute
    cosine similarity to the cluster centroid. If similarity exceeds the
    threshold, absorb the image.

    This catches trip photos from cameras without GPS (e.g., DSC photos
    taken during a San Francisco trip but without geotagging).

    Only absorbs if exactly one cluster matches (unambiguous).

    Returns (new_labels, absorb_count).
    """
    new_labels = labels.copy()
    absorb_count = 0

    # Build per-cluster info: date range and centroid.
    cluster_info = {}
    for cid in set(new_labels):
        if cid == -1:
            continue

        mask = new_labels == cid
        indices = np.where(mask)[0]
        cluster_vecs = embeddings[indices]

        centroid = _normalized_centroid(cluster_vecs)

        dts = []
        for idx in indices:
            dt = _parse_timestamp(timestamps.get(int(idx)))
            if dt is not None:
                dts.append(dt)

        cluster_info[cid] = {
            "centroid": centroid,
            "min_time": min(dts) if dts else None,
            "max_time": max(dts) if dts else None,
        }

    # Scan noise images: only those with timestamp but NO location.
    for idx in range(len(new_labels)):
        if new_labels[idx] != -1:
            continue

        ts = timestamps.get(idx)
        loc = locations.get(idx)

        # Only target images with timestamp but no GPS.
        if not ts or loc:
            continue

        dt = _parse_timestamp(ts)
        if dt is None:
            continue

        # Find clusters whose date range covers this timestamp.
        candidates = []
        buffer = 24 * 3600
        for cid, info in cluster_info.items():
            if info["min_time"] is None:
                continue
            img_ts = dt.timestamp()
            if (
                (info["min_time"].timestamp() - buffer)
                <= img_ts
                <= (info["max_time"].timestamp() + buffer)
            ):
                # Check visual similarity.
                similarity = float(embeddings[idx] @ info["centroid"])
                if similarity >= similarity_threshold:
                    candidates.append((cid, similarity))

        # Only absorb if exactly one cluster matches.
        if len(candidates) == 1:
            cid = candidates[0][0]
            new_labels[idx] = cid
            absorb_count += 1

    return new_labels, absorb_count


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
    locations: dict[int, str] | None = None,
) -> tuple[np.ndarray, int]:
    """
    Merge clusters that are temporally close and visually similar.

    For each pair of clusters, checks if their date ranges are within
    time_threshold_hours of each other AND their centroid cosine similarity
    exceeds similarity_threshold. If both conditions are met, merges them.

    Clusters that share a location (city name) get a lower similarity
    threshold (0.3 instead of the configured value), since same-city +
    same-week is a strong signal that they're the same trip/event.

    Returns (new_labels, merge_count).
    """
    locations = locations or {}
    # Lower similarity threshold when clusters share a location.
    location_similarity_threshold = min(similarity_threshold, 0.3)

    new_labels = labels.copy()
    merge_count = 0
    time_threshold_seconds = time_threshold_hours * 3600

    # Build per-cluster info: centroid, time range, and location names.
    cluster_info = {}
    unique_clusters = [c for c in set(new_labels) if c != -1]

    for cluster_id in unique_clusters:
        mask = new_labels == cluster_id
        indices = np.where(mask)[0]
        cluster_vecs = embeddings[indices]

        # Compute L2-normalized centroid.
        centroid = _normalized_centroid(cluster_vecs)

        # Collect timestamps for this cluster.
        dts = []
        for idx in indices:
            dt = _parse_timestamp(timestamps.get(int(idx)))
            if dt is not None:
                dts.append(dt)

        # Collect unique location names for this cluster.
        loc_names = set()
        for idx in indices:
            loc = locations.get(int(idx))
            if loc:
                loc_names.add(loc)

        cluster_info[cluster_id] = {
            "centroid": centroid,
            "min_time": min(dts) if dts else None,
            "max_time": max(dts) if dts else None,
            "locations": loc_names,
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
            for id_b in current_ids[i + 1 :]:
                if id_b not in cluster_info:
                    continue

                info_a = cluster_info[id_a]
                info_b = cluster_info[id_b]

                # Check temporal proximity.
                if not _temporally_close(info_a, info_b, time_threshold_seconds):
                    continue

                # Determine the effective similarity threshold.
                # If clusters share a location, use the lower threshold.
                shares_location = bool(info_a["locations"] & info_b["locations"])
                effective_threshold = (
                    location_similarity_threshold if shares_location else similarity_threshold
                )

                # Check visual similarity.
                similarity = float(info_a["centroid"] @ info_b["centroid"])
                if similarity < effective_threshold:
                    continue

                # Merge: reassign id_b → id_a.
                new_labels[new_labels == id_b] = id_a

                # Recompute centroid for the merged cluster.
                mask = new_labels == id_a
                new_centroid = _normalized_centroid(embeddings[mask])

                # Update cluster info.
                cluster_info[id_a] = {
                    "centroid": new_centroid,
                    "min_time": _safe_min(info_a["min_time"], info_b["min_time"]),
                    "max_time": _safe_max(info_a["max_time"], info_b["max_time"]),
                    "locations": info_a["locations"] | info_b["locations"],
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


def _normalized_centroid(vecs):
    """Compute the L2-normalized centroid of a set of vectors."""
    centroid = vecs.mean(axis=0)
    norm = np.linalg.norm(centroid)
    return centroid / norm if norm > 0 else centroid


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
