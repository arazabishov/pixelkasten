"""
Unit tests for propose_albums — the organize stage's manifest mutation.

LLM interaction is mocked; we test that album names flow from the
LLM response into the correct manifest entries.
"""

from unittest.mock import patch

from pixelkasten.configuration import DiscoveryOptions
from pixelkasten.manifest import Discovery, ManifestEntry, Source, Status
from pixelkasten.stages.discovery.organize import propose_albums


def _entry(cluster, status=Status.PROCESSED):
    return ManifestEntry(
        media_path=f"/photos/img_{cluster}_{id(cluster)}.jpg",
        source=Source(type="loose"),
        discovery=Discovery(status=status, cluster=cluster),
    )


def _options(model="qwen3.5:35b"):
    return DiscoveryOptions(
        clip_model="ViT-L-14",
        caption_model="llava",
        organize_model=model,
        batch_size=32,
        min_cluster_size=5,
        classify_threshold=0.2,
        skip_caption=True,
        skip_refine=True,
    )


class TestProposeAlbums:
    @patch("pixelkasten.stages.discovery.organize._propose_organization")
    def test_sets_album_source_on_clustered_entries(self, mock_propose):
        mock_propose.return_value = {"0": "Beach Vacation", "1": "Christmas Dinner"}

        entries = [
            _entry(0),
            _entry(0),
            _entry(1),
        ]

        propose_albums(entries, _options())

        # Cluster 0 entries get "Beach Vacation".
        assert entries[0].source.type == "album"
        assert entries[0].source.name == "Beach Vacation"
        assert entries[1].source.name == "Beach Vacation"

        # Cluster 1 entry gets "Christmas Dinner".
        assert entries[2].source.name == "Christmas Dinner"

    @patch("pixelkasten.stages.discovery.organize._propose_organization")
    def test_does_not_set_album_on_noise_entries(self, mock_propose):
        mock_propose.return_value = {"0": "Beach Vacation"}

        entries = [
            _entry(0),
            _entry(-1),  # Noise
        ]

        propose_albums(entries, _options())

        # Noise entry should keep original source.
        assert entries[1].source.type == "loose"

    @patch("pixelkasten.stages.discovery.organize._propose_organization")
    def test_skips_entries_without_discovery(self, mock_propose):
        mock_propose.return_value = {"0": "Beach Vacation"}

        entry_no_discovery = ManifestEntry(
            media_path="/photos/video.mp4",
            source=Source(type="loose"),
        )
        entries = [_entry(0), entry_no_discovery]

        propose_albums(entries, _options())

        # Entry without discovery stays untouched.
        assert entry_no_discovery.source.type == "loose"

    @patch("pixelkasten.stages.discovery.organize._propose_organization")
    def test_skips_clusters_not_named_by_llm(self, mock_propose):
        # LLM only names cluster 0, not cluster 1.
        mock_propose.return_value = {"0": "Beach Vacation"}

        entries = [_entry(0), _entry(1)]

        propose_albums(entries, _options())

        # Cluster 0 gets album.
        assert entries[0].source.type == "album"

        # Cluster 1 keeps original source.
        assert entries[1].source.type == "loose"

    @patch("pixelkasten.stages.discovery.organize._propose_organization")
    def test_skips_empty_album_names(self, mock_propose):
        mock_propose.return_value = {"0": ""}

        entries = [_entry(0)]

        propose_albums(entries, _options())

        # Empty string is falsy, so the source should not be changed.
        assert entries[0].source.type == "loose"
