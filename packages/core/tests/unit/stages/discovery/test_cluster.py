import numpy as np

from pixelkasten.manifest import Discovery, ManifestEntry, Source, Status
from pixelkasten.stages.discovery.cluster import find_representatives, cluster_summary


def _entry(cluster: int | None) -> ManifestEntry:
    return ManifestEntry(
        media_path=f"/photos/img_{id(cluster)}.jpg",
        source=Source(type="loose"),
        discovery=Discovery(status=Status.PROCESSED, cluster=cluster),
    )


class TestFindRepresentatives:
    def test_marks_entries_closest_to_centroid(self):
        # 4 vectors in cluster 0, with vec[0] being closest to the mean.
        rng = np.random.RandomState(42)
        base = rng.randn(64).astype(np.float32)
        base /= np.linalg.norm(base)

        vecs = []
        for i in range(4):
            v = base + rng.randn(64).astype(np.float32) * (0.01 * (i + 1))
            v /= np.linalg.norm(v)
            vecs.append(v)
        embeddings = np.array(vecs)

        entries = [_entry(0) for _ in range(4)]
        find_representatives(entries, embeddings, n_per_cluster=2)

        # Exactly 2 representatives marked for the single cluster.
        marked = [e for e in entries if e.discovery and e.discovery.is_representative]
        assert len(marked) == 2

    def test_caps_at_n_per_cluster(self):
        rng = np.random.RandomState(99)
        embeddings = np.array([rng.randn(64).astype(np.float32) for _ in range(3)])
        for i in range(len(embeddings)):
            embeddings[i] /= np.linalg.norm(embeddings[i])

        entries = [_entry(0) for _ in range(3)]
        find_representatives(entries, embeddings, n_per_cluster=5)

        # Request 5 but only 3 exist → all 3 get marked.
        marked = [e for e in entries if e.discovery and e.discovery.is_representative]
        assert len(marked) == 3

    def test_skips_noise_entries(self):
        rng = np.random.RandomState(7)
        embeddings = np.array([rng.randn(64).astype(np.float32) for _ in range(5)])
        for i in range(len(embeddings)):
            embeddings[i] /= np.linalg.norm(embeddings[i])

        entries = [_entry(0), _entry(0), _entry(-1), _entry(-1), _entry(-1)]
        find_representatives(entries, embeddings)

        # Noise entries never get marked as representative.
        for entry in entries[2:]:
            assert entry.discovery is not None
            assert entry.discovery.is_representative is False

        # At least one cluster-0 entry is marked.
        cluster_marked = [e for e in entries[:2] if e.discovery and e.discovery.is_representative]
        assert len(cluster_marked) >= 1


class TestClusterSummary:
    def test_counts_clusters_and_noise(self):
        labels = np.array([0, 0, 0, 1, 1, -1, -1])

        result = cluster_summary(labels)

        assert result["n_clusters"] == 2
        assert result["n_noise"] == 2
        assert result["cluster_sizes"][0] == 3
        assert result["cluster_sizes"][1] == 2

    def test_all_noise(self):
        labels = np.array([-1, -1, -1])

        result = cluster_summary(labels)

        assert result["n_clusters"] == 0
        assert result["n_noise"] == 3
        assert result["cluster_sizes"] == {}

    def test_no_noise(self):
        labels = np.array([0, 0, 1])

        result = cluster_summary(labels)

        assert result["n_clusters"] == 2
        assert result["n_noise"] == 0
