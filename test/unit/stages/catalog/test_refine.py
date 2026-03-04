"""Unit tests for the refine module — cluster refinement using EXIF timestamps."""

import numpy as np
import pytest
from datetime import datetime

from pixelkasten.stages.catalog.refine import (
    _parse_timestamp,
    _eject_metadataless,
    _split_by_temporal_gaps,
    _merge_similar_clusters,
    _infer_home_location,
    _absorb_noise_by_location,
    _absorb_noise_by_similarity,
    _renumber_labels,
    _temporally_close,
    _safe_min,
    _safe_max,
)


# ---------------------------------------------------------------------------
# _parse_timestamp
# ---------------------------------------------------------------------------


class TestParseTimestamp:
    def test_iso_format_returns_datetime(self):
        result = _parse_timestamp("2019-07-15T14:30:00")
        assert result == datetime(2019, 7, 15, 14, 30, 0)

    def test_none_returns_none(self):
        assert _parse_timestamp(None) is None

    def test_empty_string_returns_none(self):
        assert _parse_timestamp("") is None

    def test_garbage_returns_none(self):
        assert _parse_timestamp("not-a-date") is None

    def test_iso_with_timezone_suffix_is_stripped(self):
        # The function strips everything after 19 chars, so timezone info is ignored.
        result = _parse_timestamp("2019-07-15T14:30:00+02:00")
        assert result == datetime(2019, 7, 15, 14, 30, 0)


# ---------------------------------------------------------------------------
# _eject_metadataless
# ---------------------------------------------------------------------------


class TestEjectMetadataless:
    def test_ejects_no_exif_images_from_clusters(self):
        labels = np.array([0, 0, 1, -1])
        has_metadata = {0: True, 1: False, 2: True, 3: False}

        new_labels, count = _eject_metadataless(labels, has_metadata)

        # Index 1 had no EXIF and was in cluster 0, should be ejected to noise.
        assert new_labels[1] == -1
        assert count == 1

    def test_keeps_images_with_exif(self):
        labels = np.array([0, 0, 1])
        has_metadata = {0: True, 1: True, 2: True}

        new_labels, count = _eject_metadataless(labels, has_metadata)

        # All images have EXIF, none ejected.
        assert list(new_labels) == [0, 0, 1]
        assert count == 0

    def test_does_not_touch_noise_labels(self):
        labels = np.array([-1, -1])
        has_metadata = {0: False, 1: False}

        new_labels, count = _eject_metadataless(labels, has_metadata)

        # Already noise, should not be counted as ejected.
        assert list(new_labels) == [-1, -1]
        assert count == 0


# ---------------------------------------------------------------------------
# _split_by_temporal_gaps
# ---------------------------------------------------------------------------


class TestSplitByTemporalGaps:
    def test_splits_cluster_at_48h_gap(self):
        # Two images on day 1, two images on day 5 (gap > 48h).
        labels = np.array([0, 0, 0, 0])
        timestamps = {
            0: "2019-07-15T10:00:00",
            1: "2019-07-15T12:00:00",
            2: "2019-07-20T10:00:00",
            3: "2019-07-20T14:00:00",
        }

        new_labels, split_count = _split_by_temporal_gaps(
            labels, timestamps, gap_hours=48.0
        )

        # First two images stay in original cluster, last two get a new cluster.
        assert new_labels[0] == new_labels[1]
        assert new_labels[2] == new_labels[3]
        assert new_labels[0] != new_labels[2]
        assert split_count == 1

    def test_does_not_split_within_threshold(self):
        # All images within 24 hours.
        labels = np.array([0, 0, 0])
        timestamps = {
            0: "2019-07-15T10:00:00",
            1: "2019-07-15T18:00:00",
            2: "2019-07-16T08:00:00",
        }

        new_labels, split_count = _split_by_temporal_gaps(
            labels, timestamps, gap_hours=48.0
        )

        # All stay in same cluster.
        assert len(set(new_labels)) == 1
        assert split_count == 0

    def test_handles_cluster_with_no_timestamps(self):
        labels = np.array([0, 0])
        timestamps = {}  # No timestamps at all.

        new_labels, split_count = _split_by_temporal_gaps(
            labels, timestamps, gap_hours=48.0
        )

        # Nothing to split without timestamps.
        assert list(new_labels) == [0, 0]
        assert split_count == 0

    def test_creates_correct_sub_cluster_count(self):
        # Three temporal groups with gaps > 48h between each.
        labels = np.array([0, 0, 0, 0, 0, 0])
        timestamps = {
            0: "2019-07-01T10:00:00",
            1: "2019-07-01T12:00:00",
            2: "2019-07-10T10:00:00",
            3: "2019-07-10T12:00:00",
            4: "2019-07-20T10:00:00",
            5: "2019-07-20T12:00:00",
        }

        new_labels, split_count = _split_by_temporal_gaps(
            labels, timestamps, gap_hours=48.0
        )

        # Should produce 3 distinct clusters (2 splits).
        assert len(set(new_labels)) == 3
        assert split_count == 2


# ---------------------------------------------------------------------------
# _merge_similar_clusters
# ---------------------------------------------------------------------------


def _make_normalized_vec(base, dim=64):
    """Helper: create a normalized vector close to the base."""
    v = base.copy()
    v /= np.linalg.norm(v)
    return v


class TestMergeSimilarClusters:
    def test_merges_same_day_high_similarity_clusters(self):
        rng = np.random.RandomState(99)
        base = rng.randn(64).astype(np.float32)
        base /= np.linalg.norm(base)

        # Two clusters, both from same day, very similar embeddings.
        embeddings = np.array(
            [
                base + rng.randn(64) * 0.01,
                base + rng.randn(64) * 0.01,
                base + rng.randn(64) * 0.01,
                base + rng.randn(64) * 0.01,
            ],
            dtype=np.float32,
        )
        for i in range(len(embeddings)):
            embeddings[i] /= np.linalg.norm(embeddings[i])

        labels = np.array([0, 0, 1, 1])
        timestamps = {
            0: "2019-07-15T10:00:00",
            1: "2019-07-15T12:00:00",
            2: "2019-07-15T14:00:00",
            3: "2019-07-15T16:00:00",
        }

        new_labels, merge_count = _merge_similar_clusters(
            labels,
            embeddings,
            timestamps,
            similarity_threshold=0.5,
            time_threshold_hours=168.0,
        )

        # Both clusters should have been merged into one.
        assert len(set(new_labels)) == 1
        assert merge_count == 1

    def test_rejects_temporally_distant_clusters(self):
        rng = np.random.RandomState(99)
        base = rng.randn(64).astype(np.float32)
        base /= np.linalg.norm(base)

        embeddings = np.array(
            [
                base + rng.randn(64) * 0.01,
                base + rng.randn(64) * 0.01,
            ],
            dtype=np.float32,
        )
        for i in range(len(embeddings)):
            embeddings[i] /= np.linalg.norm(embeddings[i])

        labels = np.array([0, 1])
        # 6 months apart — way beyond any reasonable threshold.
        timestamps = {
            0: "2019-01-15T10:00:00",
            1: "2019-07-15T10:00:00",
        }

        new_labels, merge_count = _merge_similar_clusters(
            labels,
            embeddings,
            timestamps,
            similarity_threshold=0.5,
            time_threshold_hours=168.0,
        )

        # Should NOT merge despite high visual similarity.
        assert len(set(new_labels)) == 2
        assert merge_count == 0

    def test_uses_lower_threshold_for_same_location(self):
        # Construct two vectors with known cosine similarity ~0.4.
        # Start with a unit vector along dim 0, then rotate partially.
        base_a = np.zeros(64, dtype=np.float32)
        base_a[0] = 1.0

        # base_b = 0.4 * base_a + sqrt(1 - 0.4^2) * orthogonal_unit.
        # This gives cosine similarity of exactly 0.4.
        ortho = np.zeros(64, dtype=np.float32)
        ortho[1] = 1.0
        base_b = 0.4 * base_a + np.sqrt(1 - 0.4**2) * ortho
        base_b /= np.linalg.norm(base_b)

        sim = float(base_a @ base_b)
        assert 0.3 < sim < 0.5, f"Precondition: similarity should be ~0.4, got {sim}"

        embeddings = np.array([base_a, base_b], dtype=np.float32)
        labels = np.array([0, 1])
        timestamps = {
            0: "2019-07-15T10:00:00",
            1: "2019-07-16T10:00:00",
        }
        locations = {0: "California, US", 1: "California, US"}

        new_labels, merge_count = _merge_similar_clusters(
            labels,
            embeddings,
            timestamps,
            similarity_threshold=0.8,  # High threshold — would NOT merge normally.
            time_threshold_hours=168.0,
            locations=locations,
        )

        # Should merge because same location lowers threshold to 0.3,
        # and our similarity (~0.4) exceeds that.
        assert merge_count == 1
        assert len(set(new_labels)) == 1

    def test_handles_transitive_chain_merge(self):
        rng = np.random.RandomState(10)
        base = rng.randn(64).astype(np.float32)
        base /= np.linalg.norm(base)

        # Three clusters, all similar, all same day.
        embeddings = np.array(
            [
                base + rng.randn(64) * 0.01,
                base + rng.randn(64) * 0.01,
                base + rng.randn(64) * 0.01,
            ],
            dtype=np.float32,
        )
        for i in range(len(embeddings)):
            embeddings[i] /= np.linalg.norm(embeddings[i])

        labels = np.array([0, 1, 2])
        timestamps = {
            0: "2019-07-15T10:00:00",
            1: "2019-07-15T12:00:00",
            2: "2019-07-15T14:00:00",
        }

        new_labels, merge_count = _merge_similar_clusters(
            labels,
            embeddings,
            timestamps,
            similarity_threshold=0.5,
            time_threshold_hours=168.0,
        )

        # All three should merge into one cluster via transitive merges.
        assert len(set(new_labels)) == 1
        assert merge_count == 2


# ---------------------------------------------------------------------------
# _infer_home_location
# ---------------------------------------------------------------------------


class TestInferHomeLocation:
    def test_returns_most_frequent_region(self):
        locations = {
            0: "California, US",
            1: "California, US",
            2: "California, US",
            3: "California, US",
            4: "California, US",
            5: "Oslo, Norway",
        }
        assert _infer_home_location(locations) == "California, US"

    def test_returns_none_for_fewer_than_5_images(self):
        locations = {0: "Oslo, Norway", 1: "Oslo, Norway", 2: "Oslo, Norway"}
        assert _infer_home_location(locations) is None

    def test_returns_none_for_empty_dict(self):
        assert _infer_home_location({}) is None


# ---------------------------------------------------------------------------
# _absorb_noise_by_location
# ---------------------------------------------------------------------------


class TestAbsorbNoiseByLocation:
    def test_absorbs_travel_noise_into_matching_cluster(self):
        labels = np.array([0, 0, -1])
        timestamps = {
            0: "2019-07-15T10:00:00",
            1: "2019-07-15T14:00:00",
            2: "2019-07-15T12:00:00",  # Noise image, same day.
        }
        locations = {
            0: "Oslo, Norway",
            1: "Oslo, Norway",
            2: "Oslo, Norway",  # Same travel location.
        }

        new_labels, count = _absorb_noise_by_location(
            labels,
            timestamps,
            locations,
            home_location="California, US",
        )

        # Noise image should be absorbed into cluster 0.
        assert new_labels[2] == 0
        assert count == 1

    def test_skips_home_location(self):
        labels = np.array([0, 0, -1])
        timestamps = {
            0: "2019-07-15T10:00:00",
            1: "2019-07-15T14:00:00",
            2: "2019-07-15T12:00:00",
        }
        locations = {
            0: "California, US",
            1: "California, US",
            2: "California, US",
        }

        new_labels, count = _absorb_noise_by_location(
            labels,
            timestamps,
            locations,
            home_location="California, US",
        )

        # Home location should be skipped — image stays as noise.
        assert new_labels[2] == -1
        assert count == 0

    def test_skips_when_multiple_clusters_match(self):
        # Two clusters in the same location and date range — ambiguous.
        labels = np.array([0, 1, -1])
        timestamps = {
            0: "2019-07-15T10:00:00",
            1: "2019-07-15T14:00:00",
            2: "2019-07-15T12:00:00",
        }
        locations = {
            0: "Oslo, Norway",
            1: "Oslo, Norway",
            2: "Oslo, Norway",
        }

        new_labels, count = _absorb_noise_by_location(
            labels,
            timestamps,
            locations,
            home_location=None,
        )

        # Multiple candidates — should not absorb.
        assert new_labels[2] == -1
        assert count == 0


# ---------------------------------------------------------------------------
# _absorb_noise_by_similarity
# ---------------------------------------------------------------------------


class TestAbsorbNoiseBySimilarity:
    def test_absorbs_gps_less_noise_with_matching_time_and_high_similarity(self):
        rng = np.random.RandomState(42)
        base = rng.randn(64).astype(np.float32)
        base /= np.linalg.norm(base)

        # Cluster image and noise image have very similar embeddings.
        cluster_vec = base + rng.randn(64) * 0.01
        cluster_vec /= np.linalg.norm(cluster_vec)
        noise_vec = base + rng.randn(64) * 0.01
        noise_vec /= np.linalg.norm(noise_vec)

        embeddings = np.array([cluster_vec, noise_vec], dtype=np.float32)
        labels = np.array([0, -1])
        timestamps = {
            0: "2019-07-15T10:00:00",
            1: "2019-07-15T14:00:00",  # Same day, no GPS.
        }
        locations = {0: "Oslo, Norway"}  # Noise image has no location.

        new_labels, count = _absorb_noise_by_similarity(
            labels,
            embeddings,
            timestamps,
            locations,
            similarity_threshold=0.5,
        )

        # Noise image should be absorbed.
        assert new_labels[1] == 0
        assert count == 1

    def test_skips_noise_images_that_have_gps(self):
        rng = np.random.RandomState(42)
        base = rng.randn(64).astype(np.float32)
        base /= np.linalg.norm(base)

        embeddings = np.array([base, base.copy()], dtype=np.float32)
        labels = np.array([0, -1])
        timestamps = {0: "2019-07-15T10:00:00", 1: "2019-07-15T14:00:00"}
        # Noise image HAS a location — should be skipped by similarity absorber.
        locations = {0: "Oslo, Norway", 1: "Oslo, Norway"}

        new_labels, count = _absorb_noise_by_similarity(
            labels,
            embeddings,
            timestamps,
            locations,
            similarity_threshold=0.5,
        )

        # Image has GPS, so it should NOT be absorbed by similarity path.
        assert new_labels[1] == -1
        assert count == 0

    def test_skips_low_similarity(self):
        rng = np.random.RandomState(42)

        # Two very different vectors.
        vec_a = rng.randn(64).astype(np.float32)
        vec_a /= np.linalg.norm(vec_a)
        vec_b = rng.randn(64).astype(np.float32)
        vec_b /= np.linalg.norm(vec_b)

        embeddings = np.array([vec_a, vec_b], dtype=np.float32)
        labels = np.array([0, -1])
        timestamps = {0: "2019-07-15T10:00:00", 1: "2019-07-15T14:00:00"}
        locations = {0: "Oslo, Norway"}  # Noise image has no location.

        new_labels, count = _absorb_noise_by_similarity(
            labels,
            embeddings,
            timestamps,
            locations,
            similarity_threshold=0.9,  # Very high threshold.
        )

        # Low similarity — should not absorb.
        assert new_labels[1] == -1
        assert count == 0


# ---------------------------------------------------------------------------
# _renumber_labels
# ---------------------------------------------------------------------------


class TestRenumberLabels:
    def test_produces_contiguous_ids(self):
        labels = np.array([5, 5, 10, 10, -1, 20])

        new_labels = _renumber_labels(labels)

        # Should remap to 0, 1, 2 while preserving -1.
        assert set(new_labels[new_labels != -1]) == {0, 1, 2}
        assert new_labels[4] == -1

    def test_preserves_noise_label(self):
        labels = np.array([-1, 0, -1, 3])

        new_labels = _renumber_labels(labels)

        assert new_labels[0] == -1
        assert new_labels[2] == -1
        # Non-noise should be contiguous.
        non_noise = new_labels[new_labels != -1]
        assert list(sorted(set(non_noise))) == list(range(len(set(non_noise))))


# ---------------------------------------------------------------------------
# _temporally_close
# ---------------------------------------------------------------------------


class TestTemporallyClose:
    def test_overlapping_ranges(self):
        info_a = {"min_time": datetime(2019, 7, 15), "max_time": datetime(2019, 7, 20)}
        info_b = {"min_time": datetime(2019, 7, 18), "max_time": datetime(2019, 7, 25)}

        assert _temporally_close(info_a, info_b, threshold_seconds=0) is True

    def test_within_threshold(self):
        info_a = {"min_time": datetime(2019, 7, 15), "max_time": datetime(2019, 7, 16)}
        info_b = {"min_time": datetime(2019, 7, 17), "max_time": datetime(2019, 7, 18)}
        # Gap is 1 day = 86400s, threshold is 2 days = 172800s.
        assert _temporally_close(info_a, info_b, threshold_seconds=172800) is True

    def test_beyond_threshold(self):
        info_a = {"min_time": datetime(2019, 7, 15), "max_time": datetime(2019, 7, 16)}
        info_b = {"min_time": datetime(2019, 7, 25), "max_time": datetime(2019, 7, 26)}
        # Gap is 9 days, threshold is 2 days.
        assert _temporally_close(info_a, info_b, threshold_seconds=172800) is False

    def test_missing_timestamps(self):
        info_a = {"min_time": None, "max_time": None}
        info_b = {"min_time": datetime(2019, 7, 15), "max_time": datetime(2019, 7, 16)}

        assert _temporally_close(info_a, info_b, threshold_seconds=999999) is False


# ---------------------------------------------------------------------------
# _safe_min / _safe_max
# ---------------------------------------------------------------------------


class TestSafeMinMax:
    def test_safe_min_both_values(self):
        assert _safe_min(3, 5) == 3

    def test_safe_min_first_none(self):
        assert _safe_min(None, 5) == 5

    def test_safe_min_second_none(self):
        assert _safe_min(3, None) == 3

    def test_safe_min_both_none(self):
        assert _safe_min(None, None) is None

    def test_safe_max_both_values(self):
        assert _safe_max(3, 5) == 5

    def test_safe_max_first_none(self):
        assert _safe_max(None, 5) == 5

    def test_safe_max_second_none(self):
        assert _safe_max(3, None) == 3
