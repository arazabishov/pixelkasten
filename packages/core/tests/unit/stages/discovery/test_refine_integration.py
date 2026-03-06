"""
Integration tests for refine_clusters — the top-level function that
chains all five refinement steps together.

These tests use ManifestEntry objects (not raw dicts) and verify the
combined behavior of eject → split → merge → absorb.
"""

import numpy as np

from pixelkasten.manifest import (
    Discovery,
    Location,
    ManifestEntry,
    Metadata,
    Source,
    Status,
)
from pixelkasten.stages.discovery.refine import (
    refine_clusters,
    _build_cluster_info,
    _extract_entry_data,
    _find_temporal_candidates,
)


def _entry(
    cluster,
    dates=None,
    location=None,
):
    """Minimal entry for refine tests."""
    metadata = Metadata(status=Status.PROCESSED, dates=dates or []) if dates else None
    return ManifestEntry(
        media_path=f"/photos/img_{id(dates)}.jpg",
        source=Source(type="loose"),
        metadata=metadata,
        location=location,
        discovery=Discovery(status=Status.PROCESSED, cluster=cluster),
    )


class TestRefineClustersFull:
    def test_ejects_metadataless_and_renumbers(self):
        """Images without dates should be ejected to noise."""
        entries = [
            _entry(0, dates=["2019-07-15T10:00:00"]),
            _entry(0, dates=None),  # No metadata → eject
            _entry(0, dates=["2019-07-15T12:00:00"]),
        ]

        rng = np.random.RandomState(42)
        embeddings = rng.randn(3, 64).astype(np.float32)
        for i in range(3):
            embeddings[i] /= np.linalg.norm(embeddings[i])

        labels, stats = refine_clusters(entries, embeddings)

        # Entry 1 should be ejected to noise.
        assert labels[1] == -1
        assert stats["ejected"] == 1

        # Remaining entries stay clustered.
        assert labels[0] >= 0
        assert labels[2] >= 0

    def test_splits_cluster_at_temporal_gap(self):
        """A cluster spanning a >48h gap should be split."""
        entries = [
            _entry(0, dates=["2019-07-01T10:00:00"]),
            _entry(0, dates=["2019-07-01T12:00:00"]),
            _entry(0, dates=["2019-07-10T10:00:00"]),
            _entry(0, dates=["2019-07-10T12:00:00"]),
        ]

        rng = np.random.RandomState(42)
        embeddings = rng.randn(4, 64).astype(np.float32)
        for i in range(4):
            embeddings[i] /= np.linalg.norm(embeddings[i])

        labels, stats = refine_clusters(entries, embeddings)

        assert stats["splits"] >= 1
        # First two and last two should be in different clusters.
        assert labels[0] == labels[1]
        assert labels[2] == labels[3]
        assert labels[0] != labels[2]

    def test_preserves_noise_entries(self):
        """Noise entries should stay as noise throughout refinement."""
        entries = [
            _entry(0, dates=["2019-07-15T10:00:00"]),
            _entry(-1, dates=["2019-09-01T10:00:00"]),
        ]

        rng = np.random.RandomState(42)
        embeddings = rng.randn(2, 64).astype(np.float32)
        for i in range(2):
            embeddings[i] /= np.linalg.norm(embeddings[i])

        labels, _ = refine_clusters(entries, embeddings)

        # Noise stays noise (no matching cluster to absorb into).
        assert labels[1] == -1

    def test_skips_entries_without_discovery(self):
        """Entries without discovery status are excluded from refinement."""
        entry_with = ManifestEntry(
            media_path="/photos/a.jpg",
            source=Source(type="loose"),
            metadata=Metadata(status=Status.PROCESSED, dates=["2019-07-15T10:00:00"]),
            discovery=Discovery(status=Status.PROCESSED, cluster=0),
        )
        entry_without = ManifestEntry(
            media_path="/photos/b.mp4",
            source=Source(type="loose"),
        )

        embeddings = np.random.randn(1, 64).astype(np.float32)
        embeddings /= np.linalg.norm(embeddings, axis=1, keepdims=True)

        # Should not crash with mixed entries.
        labels, _ = refine_clusters([entry_with, entry_without], embeddings)

        # Only one entry in the embedding space.
        assert len(labels) == 1


class TestExtractEntryData:
    def test_extracts_timestamps_and_regions(self):
        oslo = Location(name="Oslo, Oslo, Norway", region="Oslo, Norway", country="Norway")
        entries = [
            _entry(0, dates=["2019-07-15T10:00:00"], location=oslo),
            _entry(1, dates=["2019-08-20T19:00:00"]),
        ]

        timestamps, regions, has_metadata, labels = _extract_entry_data(entries)

        assert timestamps == {0: "2019-07-15T10:00:00", 1: "2019-08-20T19:00:00"}
        assert regions == {0: "Oslo, Norway"}
        assert has_metadata == {0: True, 1: True}
        assert list(labels) == [0, 1]

    def test_entries_without_dates_have_false_metadata(self):
        entries = [_entry(0, dates=None)]

        _, _, has_metadata, _ = _extract_entry_data(entries)

        assert has_metadata[0] is False


class TestBuildClusterInfo:
    def test_computes_date_range_and_centroid(self):
        labels = np.array([0, 0, 1])
        timestamps = {0: "2019-07-15T10:00:00", 1: "2019-07-16T10:00:00", 2: "2019-08-01T10:00:00"}

        rng = np.random.RandomState(42)
        embeddings = rng.randn(3, 64).astype(np.float32)
        for i in range(3):
            embeddings[i] /= np.linalg.norm(embeddings[i])

        info = _build_cluster_info(labels, timestamps, embeddings)

        # Cluster 0 should have a 1-day date range.
        assert info[0]["min_time"].day == 15
        assert info[0]["max_time"].day == 16

        # Centroid should be a normalized vector.
        assert abs(np.linalg.norm(info[0]["centroid"]) - 1.0) < 1e-5

        # Cluster 1 should exist.
        assert 1 in info

        # Noise (-1) should not appear.
        assert -1 not in info

    def test_skips_centroid_when_no_embeddings(self):
        labels = np.array([0, 0])
        timestamps = {0: "2019-07-15T10:00:00", 1: "2019-07-16T10:00:00"}

        info = _build_cluster_info(labels, timestamps)

        assert "centroid" not in info[0]
        assert info[0]["min_time"] is not None


class TestFindTemporalCandidates:
    def test_finds_cluster_covering_timestamp(self):
        from datetime import datetime

        cluster_info = {
            0: {
                "min_time": datetime(2019, 7, 15),
                "max_time": datetime(2019, 7, 20),
                "locations": {"Oslo, Norway"},
            },
        }

        # Image taken on July 17 in Oslo.
        candidates = _find_temporal_candidates(
            datetime(2019, 7, 17),
            cluster_info,
            location="Oslo, Norway",
        )

        assert candidates == [0]

    def test_excludes_wrong_location(self):
        from datetime import datetime

        cluster_info = {
            0: {
                "min_time": datetime(2019, 7, 15),
                "max_time": datetime(2019, 7, 20),
                "locations": {"Oslo, Norway"},
            },
        }

        # Right time, wrong location.
        candidates = _find_temporal_candidates(
            datetime(2019, 7, 17),
            cluster_info,
            location="Berlin, Germany",
        )

        assert candidates == []

    def test_applies_24h_buffer(self):
        from datetime import datetime

        cluster_info = {
            0: {
                "min_time": datetime(2019, 7, 15, 12, 0),
                "max_time": datetime(2019, 7, 15, 18, 0),
            },
        }

        # Image taken 20 hours before cluster start — within 24h buffer.
        candidates = _find_temporal_candidates(
            datetime(2019, 7, 14, 16, 0),
            cluster_info,
        )

        assert candidates == [0]
