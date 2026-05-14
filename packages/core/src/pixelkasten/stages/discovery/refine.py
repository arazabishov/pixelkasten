"""
Cluster refinement — improve HDBSCAN groupings using temporal and geographic signals.

After HDBSCAN groups images by visual similarity and EXIF timestamps are read
(reconcile), this module refines the clusters in five steps:

1. **Eject** images with no EXIF metadata from clusters — these were placed
   purely by visual similarity and are the most error-prone.

2. **Split** clusters that span different time periods. If a cluster has
   a temporal gap > 48 hours between consecutive photos, it likely
   contains images from different events that just look similar.

3. **Merge** clusters that are temporally close and visually similar.
   If two clusters are from the same week and their centroids have high
   cosine similarity, they're likely the same event that HDBSCAN over-split.

4. **Absorb noise by location** — noise images with a non-home GPS location
   and a timestamp overlapping a cluster's date range get absorbed.

5. **Absorb noise by similarity** — GPS-less noise images with a timestamp
   overlapping a cluster's date range and high visual similarity get absorbed.
"""

import numpy as np
from datetime import datetime

from pixelkasten.manifest import ManifestEntry, Status


def refine_clusters(
    entries: list[ManifestEntry],
    embeddings: np.ndarray,
    split_gap_hours: float = 48.0,
    merge_similarity: float = 0.5,
    merge_time_hours: float = 168.0,
    home_region: str | None = None,
) -> dict:
    """
    Refine cluster assignments using EXIF timestamps and embedding similarity.

    Operates on the embedding-index space: only entries with
    discovery.status == PROCESSED get a row in the labels/embeddings arrays.
    Mutates entry.discovery.cluster with the refined assignments.
    """
    timestamps, regions, has_metadata, labels = _extract_entry_data(entries)

    labels, n_ejected = _eject_metadataless(labels, has_metadata)
    labels, n_splits = _split_by_temporal_gaps(labels, timestamps, split_gap_hours)
    labels, n_merges = _merge_similar_clusters(
        labels,
        embeddings,
        timestamps,
        merge_similarity,
        merge_time_hours,
        regions,
    )

    labels, n_absorbed_loc = _absorb_noise_by_location(labels, timestamps, regions, home_region)
    labels, n_absorbed_vis = _absorb_noise_by_similarity(
        labels,
        embeddings,
        timestamps,
        regions,
    )

    labels = _renumber_labels(labels)

    # Write refined assignments back. Aligned with the PROCESSED subset that
    # _extract_entry_data filtered on.
    processed_entries = [
        e for e in entries if e.discovery and e.discovery.status == Status.PROCESSED
    ]
    for i, entry in enumerate(processed_entries):
        assert entry.discovery is not None
        entry.discovery.cluster = int(labels[i])

    return {
        "ejected": n_ejected,
        "splits": n_splits,
        "merges": n_merges,
        "absorbed_by_location": n_absorbed_loc,
        "absorbed_by_similarity": n_absorbed_vis,
        "home_location": home_region,
    }


def _extract_entry_data(
    entries: list[ManifestEntry],
) -> tuple[dict[int, str], dict[int, str], dict[int, bool], np.ndarray]:
    """
    Walk entries once and build the per-embedding-index lookup dicts
    that all refinement steps need.

    Returns (timestamps, regions, has_metadata, labels).
    """
    timestamps: dict[int, str] = {}
    regions: dict[int, str] = {}
    has_metadata: dict[int, bool] = {}
    label_list: list[int] = []

    processed = [e for e in entries if e.discovery and e.discovery.status == Status.PROCESSED]

    for embed_index, entry in enumerate(processed):
        dates = entry.metadata.dates if entry.metadata else []
        has_metadata[embed_index] = bool(dates)
        if dates:
            timestamps[embed_index] = dates[0]
        if entry.location and entry.location.region:
            regions[embed_index] = entry.location.region

        assert entry.discovery is not None
        cluster = entry.discovery.cluster if entry.discovery.cluster is not None else -1
        label_list.append(cluster)

    return timestamps, regions, has_metadata, np.array(label_list, dtype=int)


def _build_cluster_info(
    labels: np.ndarray,
    timestamps: dict[int, str],
    embeddings: np.ndarray | None = None,
    regions: dict[int, str] | None = None,
) -> dict[int, dict]:
    """
    Build per-cluster summary: date range, centroid, and locations.

    Only computes centroid when embeddings is provided, and only
    collects locations when regions is provided.
    """
    info: dict[int, dict] = {}

    cluster_ids = [c for c in set(labels) if c != -1]
    for cid in cluster_ids:
        mask = labels == cid
        indices = np.where(mask)[0]

        dts = []
        locs: set[str] = set()
        for idx in indices:
            dt = _parse_timestamp(timestamps.get(int(idx)))
            if dt is not None:
                dts.append(dt)
            if regions is not None:
                loc = regions.get(int(idx))
                if loc:
                    locs.add(loc)

        entry: dict = {
            "min_time": min(dts) if dts else None,
            "max_time": max(dts) if dts else None,
        }

        if embeddings is not None:
            entry["centroid"] = _normalized_centroid(embeddings[indices])
        if regions is not None:
            entry["locations"] = locs

        info[cid] = entry

    return info


def _eject_metadataless(
    labels: np.ndarray, has_metadata: dict[int, bool]
) -> tuple[np.ndarray, int]:
    """
    Move images with no date metadata from clusters to noise (-1).

    Images without any date metadata were placed in clusters purely by
    visual similarity — the most error-prone assignments.
    """
    new_labels = labels.copy()
    eject_count = 0

    for idx in range(len(new_labels)):
        if new_labels[idx] != -1 and not has_metadata.get(idx, False):
            new_labels[idx] = -1
            eject_count += 1

    return new_labels, eject_count


def _split_by_temporal_gaps(
    labels: np.ndarray, timestamps: dict[int, str], gap_hours: float
) -> tuple[np.ndarray, int]:
    """
    Split clusters at temporal gaps larger than gap_hours.

    For each cluster, sorts members by timestamp and creates a new
    sub-cluster after each gap. Images without timestamps stay with
    the original cluster.
    """
    new_labels = labels.copy()
    next_id = labels.max() + 1 if len(labels) > 0 else 0
    split_count = 0
    gap_seconds = gap_hours * 3600

    cluster_ids = [c for c in set(labels) if c != -1]
    for cluster_id in cluster_ids:
        split_points, timed = _find_split_points(labels, cluster_id, timestamps, gap_seconds)
        if not split_points:
            pass
        else:
            segments = _chop_segments(timed, split_points)
            # First segment keeps original ID, rest get new IDs.
            for segment in segments[1:]:
                for idx in segment:
                    new_labels[idx] = next_id
                next_id += 1
                split_count += 1

    return new_labels, split_count


def _find_split_points(
    labels: np.ndarray, cluster_id: int, timestamps: dict[int, str], gap_seconds: float
) -> tuple[list[int], list[tuple[int, datetime]]]:
    """Find temporal gap positions within a cluster. Returns (split_points, sorted_timed)."""
    indices = np.where(labels == cluster_id)[0]
    timed = [
        (int(idx), dt)
        for idx in indices
        if (dt := _parse_timestamp(timestamps.get(int(idx)))) is not None
    ]

    if len(timed) < 2:
        return [], timed

    timed.sort(key=lambda x: x[1])
    split_points = [
        i
        for i in range(1, len(timed))
        if (timed[i][1] - timed[i - 1][1]).total_seconds() > gap_seconds
    ]
    return split_points, timed


def _chop_segments(timed: list[tuple[int, datetime]], split_points: list[int]) -> list[list[int]]:
    """Chop a sorted (index, datetime) list into segments at the given positions."""
    segments = []
    prev = 0
    for sp in split_points:
        segments.append([t[0] for t in timed[prev:sp]])
        prev = sp
    segments.append([t[0] for t in timed[prev:]])
    return segments


def _merge_similar_clusters(
    labels: np.ndarray,
    embeddings: np.ndarray,
    timestamps: dict[int, str],
    similarity_threshold: float,
    time_threshold_hours: float,
    locations: dict[int, str] | None = None,
) -> tuple[np.ndarray, int]:
    """
    Merge clusters that are temporally close AND visually similar.

    Clusters sharing a location get a lower similarity threshold (0.3)
    since same-city + same-week is a strong signal.
    Uses a union-find loop: iterates until no more merges are possible.
    """
    locations = locations or {}
    location_threshold = min(similarity_threshold, 0.3)
    new_labels = labels.copy()
    merge_count = 0
    time_threshold_secs = time_threshold_hours * 3600

    cluster_info = _build_cluster_info(new_labels, timestamps, embeddings, locations)

    merged = True
    while merged:
        merged = False
        current_ids = sorted(c for c in set(new_labels) if c != -1)

        for i, id_a in enumerate(current_ids):
            if id_a not in cluster_info:
                break
            for id_b in current_ids[i + 1 :]:
                if id_b not in cluster_info:
                    break

                merged = _try_merge(
                    id_a,
                    id_b,
                    new_labels,
                    embeddings,
                    cluster_info,
                    time_threshold_secs,
                    similarity_threshold,
                    location_threshold,
                )
                if merged:
                    merge_count += 1
                    break

            if merged:
                break

    return new_labels, merge_count


def _try_merge(
    id_a: int,
    id_b: int,
    labels: np.ndarray,
    embeddings: np.ndarray,
    cluster_info: dict[int, dict],
    time_threshold_secs: float,
    similarity_threshold: float,
    location_threshold: float,
) -> bool:
    """
    Try to merge cluster id_b into id_a. Mutates labels and cluster_info
    if the merge succeeds. Returns True if merged.
    """
    info_a = cluster_info[id_a]
    info_b = cluster_info[id_b]

    if not _temporally_close(info_a, info_b, time_threshold_secs):
        return False

    shares_location = bool(info_a["locations"] & info_b["locations"])
    threshold = location_threshold if shares_location else similarity_threshold

    similarity = float(info_a["centroid"] @ info_b["centroid"])
    if similarity < threshold:
        return False

    # Merge id_b into id_a.
    labels[labels == id_b] = id_a

    cluster_info[id_a] = {
        "centroid": _normalized_centroid(embeddings[labels == id_a]),
        "min_time": _safe_min(info_a["min_time"], info_b["min_time"]),
        "max_time": _safe_max(info_a["max_time"], info_b["max_time"]),
        "locations": info_a["locations"] | info_b["locations"],
    }
    del cluster_info[id_b]

    return True


def _absorb_noise_by_location(
    labels: np.ndarray,
    timestamps: dict[int, str],
    locations: dict[int, str],
    home_location: str | None,
) -> tuple[np.ndarray, int]:
    """
    Absorb noise images into clusters when they share a non-home location
    and overlapping dates. Only absorbs when exactly one cluster matches.
    """
    new_labels = labels.copy()
    absorb_count = 0
    cluster_info = _build_cluster_info(new_labels, timestamps, regions=locations)

    # Pre-filter: noise images with parseable timestamp + non-home location.
    noise_candidates = [
        (idx, dt)
        for idx in range(len(new_labels))
        if new_labels[idx] == -1
        and idx in timestamps
        and idx in locations
        and (not home_location or locations[idx] != home_location)
        and (dt := _parse_timestamp(timestamps[idx])) is not None
    ]

    for idx, dt in noise_candidates:
        candidates = _find_temporal_candidates(dt, cluster_info, location=locations[idx])
        if len(candidates) == 1:
            cid = candidates[0]
            new_labels[idx] = cid
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
    Absorb GPS-less noise images by time + visual similarity.

    Targets noise images that have a timestamp but NO GPS data. If their
    timestamp falls within a cluster's date range and they're visually
    similar to the centroid, absorb them (if exactly one cluster matches).
    """
    new_labels = labels.copy()
    absorb_count = 0
    cluster_info = _build_cluster_info(new_labels, timestamps, embeddings)

    # Pre-filter: noise images with parseable timestamp but no GPS.
    noise_candidates = [
        (idx, dt)
        for idx in range(len(new_labels))
        if new_labels[idx] == -1
        and idx in timestamps
        and idx not in locations
        and (dt := _parse_timestamp(timestamps[idx])) is not None
    ]

    for idx, dt in noise_candidates:
        similar = [
            cid
            for cid in _find_temporal_candidates(dt, cluster_info)
            if float(embeddings[idx] @ cluster_info[cid]["centroid"]) >= similarity_threshold
        ]
        if len(similar) == 1:
            new_labels[idx] = similar[0]
            absorb_count += 1

    return new_labels, absorb_count


def _find_temporal_candidates(
    dt: datetime, cluster_info: dict[int, dict], location: str | None = None
) -> list[int]:
    """
    Find clusters whose date range (with 24h buffer) covers dt.

    When location is provided, also requires the cluster to contain
    that location.
    """
    buffer = 24 * 3600
    img_ts = dt.timestamp()

    return [
        cid
        for cid, info in cluster_info.items()
        if info["min_time"] is not None
        and (not location or location in info.get("locations", set()))
        and (info["min_time"].timestamp() - buffer)
        <= img_ts
        <= (info["max_time"].timestamp() + buffer)
    ]


def infer_home_region(regions: list[str]) -> str | None:
    """
    Infer the user's home region from the most frequent region.

    Returns the most common region if it appears 5+ times, else None.
    """
    if not regions:
        return None

    from collections import Counter

    counts = Counter(regions)
    most_common, count = counts.most_common(1)[0]

    if count < 5:
        return None

    return most_common


def _parse_timestamp(ts: str | None) -> datetime | None:
    """Parse an ISO 8601 timestamp string to datetime. Returns None on failure."""
    if not ts:
        return None
    try:
        return datetime.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S")
    except (ValueError, IndexError):
        return None


def _temporally_close(info_a: dict, info_b: dict, threshold_seconds: float) -> bool:
    """
    Check if two clusters are temporally close.

    Returns True if their date ranges overlap or are within threshold_seconds
    of each other. Returns False if either has no timestamps.
    """
    if info_a["min_time"] is None or info_b["min_time"] is None:
        return False

    # Overlapping ranges.
    if info_a["min_time"] <= info_b["max_time"] and info_b["min_time"] <= info_a["max_time"]:
        return True

    # Gap between ranges.
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
    """Renumber cluster labels to be contiguous (0, 1, 2, ...), preserving -1."""
    new_labels = labels.copy()
    next_id = 0
    for old_id in sorted(c for c in set(labels) if c != -1):
        new_labels[labels == old_id] = next_id
        next_id += 1
    return new_labels
