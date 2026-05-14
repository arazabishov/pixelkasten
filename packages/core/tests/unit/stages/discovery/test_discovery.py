"""
Unit tests for the discovery orchestrator.

All heavy dependencies (CLIP, Ollama) are mocked. These tests verify
the wiring: that the orchestrator correctly maps between image entries,
embedding rows, and manifest fields.
"""

from unittest.mock import patch
from contextlib import contextmanager

import numpy as np

from pixelkasten.configuration import DiscoveryOptions, Options
from pixelkasten.manifest import ManifestEntry, Source, Status
from pixelkasten.stages.discovery.discovery import run_discovery


def _make_options(
    skip_refine=True,
    skip_caption=True,
) -> Options:
    return Options(
        source="/photos",
        destination="/out",
        discovery=DiscoveryOptions(
            clip_model="ViT-L-14",
            caption_model="gemma4:e4b",
            organize_model="gemma4:31b",
            batch_size=32,
            min_cluster_size=5,
            skip_caption=skip_caption,
            skip_refine=skip_refine,
        ),
        dry_run=False,
        skip_dedupe=True,
        skip_metadata_write=True,
        skip_rename=True,
        prefer="album",
        fuzzy=False,
        fuzzy_threshold=10,
    )


@contextmanager
def _noop_progress(label, total):
    """A no-op progress context manager matching the pipeline's interface."""
    yield lambda n: None


def _make_entry(path: str) -> ManifestEntry:
    return ManifestEntry(media_path=path, source=Source(type="loose"))


def _make_embeddings(n: int, dim: int = 768) -> np.ndarray:
    """Create n normalized random embeddings."""
    rng = np.random.RandomState(42)
    emb = rng.randn(n, dim).astype(np.float32)
    norms = np.linalg.norm(emb, axis=1, keepdims=True)
    return emb / norms


# Patch targets — all in the discovery module's namespace.
EMBED_MOD = "pixelkasten.stages.discovery.discovery"


class TestDiscoveryIndexMapping:
    """Verify that the orchestrator correctly maps entries to embedding rows,
    especially when some images fail to embed."""

    @patch("pixelkasten.stages.discovery.geocode.reverse_geocode")
    @patch(f"{EMBED_MOD}.propose_albums")
    @patch(f"{EMBED_MOD}.find_representatives")
    @patch(f"{EMBED_MOD}.cluster_embeddings")
    @patch(f"{EMBED_MOD}.embed_images")
    def test_maps_entries_to_correct_embedding_rows_with_failures(
        self,
        mock_embed_images,
        mock_cluster,
        mock_find_reps,
        mock_propose,
        mock_geocode,
    ):
        # 5 images, image at index 2 fails embedding.
        entries = [_make_entry(f"/photos/img_{i}.jpg") for i in range(5)]
        embeddings = _make_embeddings(4)  # 4 successful
        failed_indices = [2]

        mock_embed_images.return_value = (embeddings, failed_indices)

        # Cluster: 4 images → labels [0, 0, 1, 1]
        mock_cluster.return_value = np.array([0, 0, 1, 1])

        # Representatives: embedding rows 0 and 2.
        def _find_reps(entries, embeddings, n_per_cluster=3):
            rep_positions = {0, 2}
            for i, entry in enumerate(entries):
                if entry.discovery is not None:
                    entry.discovery.is_representative = i in rep_positions

        mock_find_reps.side_effect = _find_reps

        options = _make_options(skip_refine=True, skip_caption=True)
        run_discovery(entries, options, progress=_noop_progress)

        # Entry 0 → embed row 0 → cluster 0, representative
        assert entries[0].discovery is not None
        assert entries[0].discovery.status == Status.PROCESSED
        assert entries[0].discovery.cluster == 0
        assert entries[0].discovery.is_representative is True

        # Entry 1 → embed row 1 → cluster 0, not representative
        assert entries[1].discovery is not None
        assert entries[1].discovery.status == Status.PROCESSED
        assert entries[1].discovery.cluster == 0
        assert entries[1].discovery.is_representative is False

        # Entry 2 → failed, should be ERROR
        assert entries[2].discovery is not None
        assert entries[2].discovery.status == Status.ERROR

        # Entry 3 → embed row 2 → cluster 1, representative
        assert entries[3].discovery is not None
        assert entries[3].discovery.status == Status.PROCESSED
        assert entries[3].discovery.cluster == 1
        assert entries[3].discovery.is_representative is True

        # Entry 4 → embed row 3 → cluster 1, not representative
        assert entries[4].discovery is not None
        assert entries[4].discovery.status == Status.PROCESSED
        assert entries[4].discovery.cluster == 1

    @patch("pixelkasten.stages.discovery.geocode.reverse_geocode")
    @patch(f"{EMBED_MOD}.propose_albums")
    @patch(f"{EMBED_MOD}.find_representatives")
    @patch(f"{EMBED_MOD}.cluster_embeddings")
    @patch(f"{EMBED_MOD}.embed_images")
    def test_all_entries_processed_when_no_failures(
        self,
        mock_embed_images,
        mock_cluster,
        mock_find_reps,
        mock_propose,
        mock_geocode,
    ):
        entries = [_make_entry(f"/photos/img_{i}.jpg") for i in range(3)]
        embeddings = _make_embeddings(3)

        mock_embed_images.return_value = (embeddings, [])
        mock_cluster.return_value = np.array([0, 0, 0])

        options = _make_options()
        run_discovery(entries, options, progress=_noop_progress)

        # All entries should be PROCESSED.
        for entry in entries:
            assert entry.discovery is not None
            assert entry.discovery.status == Status.PROCESSED
            assert entry.discovery.cluster == 0

    @patch("pixelkasten.stages.discovery.geocode.reverse_geocode")
    @patch(f"{EMBED_MOD}.propose_albums")
    @patch(f"{EMBED_MOD}.find_representatives")
    @patch(f"{EMBED_MOD}.cluster_embeddings")
    @patch(f"{EMBED_MOD}.embed_images")
    def test_non_image_entries_are_ignored(
        self,
        mock_embed_images,
        mock_cluster,
        mock_find_reps,
        mock_propose,
        mock_geocode,
    ):
        entries = [
            _make_entry("/photos/img_0.jpg"),
            _make_entry("/photos/video.mp4"),  # Not an image
            _make_entry("/photos/img_1.jpg"),
        ]
        embeddings = _make_embeddings(2)

        mock_embed_images.return_value = (embeddings, [])
        mock_cluster.return_value = np.array([0, 0])

        options = _make_options()
        run_discovery(entries, options, progress=_noop_progress)

        # Image entries get discovery.
        assert entries[0].discovery is not None
        assert entries[0].discovery.status == Status.PROCESSED
        assert entries[2].discovery is not None
        assert entries[2].discovery.status == Status.PROCESSED

        # Video entry is untouched.
        assert entries[1].discovery is None

    def test_returns_early_for_no_images(self):
        entries = [_make_entry("/photos/video.mp4")]
        options = _make_options()

        # Should not raise — just returns.
        result = run_discovery(entries, options, progress=_noop_progress)
        assert result is entries


class TestDiscoveryRefineIntegration:
    """Test that the orchestrator correctly wires refine results
    back into manifest entries."""

    @patch("pixelkasten.stages.discovery.geocode.reverse_geocode")
    @patch(f"{EMBED_MOD}.propose_albums")
    @patch(f"{EMBED_MOD}.refine_clusters")
    @patch(f"{EMBED_MOD}.find_representatives")
    @patch(f"{EMBED_MOD}.cluster_embeddings")
    @patch(f"{EMBED_MOD}.embed_images")
    def test_refine_updates_cluster_assignments(
        self,
        mock_embed_images,
        mock_cluster,
        mock_find_reps,
        mock_refine,
        mock_propose,
        mock_geocode,
    ):
        entries = [_make_entry(f"/photos/img_{i}.jpg") for i in range(4)]
        embeddings = _make_embeddings(4)

        mock_embed_images.return_value = (embeddings, [])

        # Initial clustering: all in cluster 0.
        mock_cluster.return_value = np.array([0, 0, 0, 0])

        # Refine splits into two clusters by mutating entry.discovery.cluster.
        def _refine(entries, embeddings, home_region=None):
            new_clusters = [0, 0, 1, 1]
            for i, entry in enumerate(entries):
                if entry.discovery is not None:
                    entry.discovery.cluster = new_clusters[i]
            return {"splits": 1}

        mock_refine.side_effect = _refine

        # Representatives are computed once after refine, on the final clusters.
        def _find_reps(entries, embeddings, n_per_cluster=3):
            rep_positions = {0, 2}
            for i, entry in enumerate(entries):
                if entry.discovery is not None:
                    entry.discovery.is_representative = i in rep_positions

        mock_find_reps.side_effect = _find_reps

        options = _make_options(skip_refine=False, skip_caption=True)
        run_discovery(entries, options, progress=_noop_progress)

        # Entries should reflect refined clusters.
        d0 = entries[0].discovery
        d1 = entries[1].discovery
        d2 = entries[2].discovery
        d3 = entries[3].discovery
        assert d0 is not None
        assert d1 is not None
        assert d2 is not None
        assert d3 is not None

        assert d0.cluster == 0
        assert d1.cluster == 0
        assert d2.cluster == 1
        assert d3.cluster == 1

        # Representatives should be updated after refine.
        assert d0.is_representative is True
        assert d2.is_representative is True
        assert d1.is_representative is False
        assert d3.is_representative is False
