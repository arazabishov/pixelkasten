"""
Tests for the propose stage — LLM album naming adapter.
"""

from unittest.mock import patch

from pixelkasten.catalog.propose import extract_album_name, propose_albums


class TestExtractAlbumName:
    def test_extracts_name_from_standard_format(self):
        assert extract_album_name("2024/20240715 - Beach Vacation") == "Beach Vacation"

    def test_extracts_name_without_date_prefix(self):
        assert extract_album_name("2024/Beach Vacation") == "Beach Vacation"

    def test_extracts_name_from_unknown_year(self):
        assert extract_album_name("Unknown/Misc Photos") == "Misc Photos"

    def test_handles_date_with_extra_spaces(self):
        assert extract_album_name("2024/20240715  -  Trip to Japan") == "Trip to Japan"

    def test_returns_none_for_single_component(self):
        assert extract_album_name("2024") is None

    def test_returns_none_for_empty_string(self):
        assert extract_album_name("") is None


class TestProposeAlbums:
    @patch("pixelkasten.catalog.propose.propose_organization")
    def test_mutates_entries_with_album_source(self, mock_propose):
        mock_propose.return_value = {
            "0": "2024/20240715 - Beach Vacation",
            "1": "2023/20231225 - Christmas",
        }

        manifest = {
            "entries": [
                {"path": "/img1.jpg", "cluster": 0, "source": {"type": "loose"}},
                {"path": "/img2.jpg", "cluster": 1, "source": {"type": "loose"}},
                {"path": "/img3.jpg", "cluster": -1, "source": {"type": "loose"}},
            ],
            "clusters": {"0": {}, "1": {}},
        }

        propose_albums(manifest)

        assert manifest["entries"][0]["source"] == {
            "type": "album",
            "name": "Beach Vacation",
        }
        assert manifest["entries"][1]["source"] == {
            "type": "album",
            "name": "Christmas",
        }

        # Noise entry unchanged
        assert manifest["entries"][2]["source"] == {"type": "loose"}

    @patch("pixelkasten.catalog.propose.propose_organization")
    def test_skips_noise_entries(self, mock_propose):
        mock_propose.return_value = {"0": "2024/20240715 - Album"}

        manifest = {
            "entries": [
                {"path": "/noise.jpg", "cluster": -1, "source": {"type": "loose"}},
            ],
            "clusters": {},
        }

        propose_albums(manifest)

        assert manifest["entries"][0]["source"]["type"] == "loose"

    @patch("pixelkasten.catalog.propose.propose_organization")
    def test_skips_entries_not_in_cluster_dirs(self, mock_propose):
        mock_propose.return_value = {"0": "2024/20240715 - Album"}

        manifest = {
            "entries": [
                {"path": "/img.jpg", "cluster": 5, "source": {"type": "loose"}},
            ],
            "clusters": {},
        }

        propose_albums(manifest)

        assert manifest["entries"][0]["source"]["type"] == "loose"
