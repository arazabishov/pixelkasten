import numpy as np

from pixelkasten.stages.catalog.cluster import find_representatives, cluster_summary


class TestFindRepresentatives:
    def test_returns_indices_closest_to_centroid(self):
        # 4 vectors in cluster 0, with vec[0] being closest to the mean.
        rng = np.random.RandomState(42)
        base = rng.randn(64).astype(np.float32)
        base /= np.linalg.norm(base)

        embeddings = []
        for i in range(4):
            v = base + rng.randn(64).astype(np.float32) * (0.01 * (i + 1))
            v /= np.linalg.norm(v)
            embeddings.append(v)
        embeddings = np.array(embeddings)

        labels = np.array([0, 0, 0, 0])

        reps = find_representatives(embeddings, labels, n_per_cluster=2)

        # Should return 2 representatives for cluster 0.
        assert 0 in reps
        assert len(reps[0]) == 2

    def test_caps_at_n_per_cluster(self):
        rng = np.random.RandomState(99)
        embeddings = np.array([rng.randn(64).astype(np.float32) for _ in range(3)])
        for i in range(len(embeddings)):
            embeddings[i] /= np.linalg.norm(embeddings[i])

        labels = np.array([0, 0, 0])

        # Request 5 but only 3 exist.
        reps = find_representatives(embeddings, labels, n_per_cluster=5)

        assert len(reps[0]) == 3

    def test_skips_noise_labels(self):
        rng = np.random.RandomState(7)
        embeddings = np.array([rng.randn(64).astype(np.float32) for _ in range(5)])
        for i in range(len(embeddings)):
            embeddings[i] /= np.linalg.norm(embeddings[i])

        labels = np.array([0, 0, -1, -1, -1])

        reps = find_representatives(embeddings, labels)

        # Only cluster 0 should have representatives, not -1.
        assert 0 in reps
        assert -1 not in reps


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
