"""
Unit tests for the organize module's pure logic functions:
- _parse_llm_response
- build_cluster_summary_text
"""

import pytest

from pixelkasten.manifest import Discovery, Location, ManifestEntry, Metadata, Source, Status, Tag
from pixelkasten.stages.discovery.organize import (
    _parse_llm_response,
    build_cluster_summary_text,
)


class TestParseLlmResponse:
    def test_clean_json_string(self):
        raw = '{"0": "Beach Vacation", "1": "Dinner Party"}'
        result = _parse_llm_response(raw)
        assert result == {"0": "Beach Vacation", "1": "Dinner Party"}

    def test_json_wrapped_in_markdown_fences(self):
        raw = '```json\n{"0": "Beach Vacation"}\n```'
        result = _parse_llm_response(raw)
        assert result == {"0": "Beach Vacation"}

    def test_json_with_surrounding_explanation_text(self):
        raw = 'Here is the proposed structure:\n{"5": "Christmas Dinner"}\nI hope this helps!'
        result = _parse_llm_response(raw)
        assert result == {"5": "Christmas Dinner"}

    def test_completely_invalid_text_raises_value_error(self):
        raw = "Sorry, I cannot process this request."
        with pytest.raises(ValueError, match="LLM did not return valid JSON"):
            _parse_llm_response(raw)


class TestBuildClusterSummaryText:
    def test_output_includes_captions_tags_and_date_range(self, sample_entries):
        """The summary text must contain captions, tags, and date range for each cluster."""
        text = build_cluster_summary_text(sample_entries)

        # Cluster 0 caption (from entry-level caption field).
        assert "A beach scene" in text

        # Cluster 0 tags (aggregated from entry-level tags).
        assert "scene:beach" in text

        # Cluster 0 date range (computed from entry timestamps).
        assert "2019-07-15T14:30:00" in text
        assert "2019-07-17T11:00:00" in text

        # Cluster 1 caption.
        assert "A dinner gathering" in text

        # Cluster 1 date range.
        assert "2019-08-20T19:00:00" in text
        assert "2019-08-20T21:00:00" in text

    def test_output_includes_location_info(self, sample_entries):
        """The summary text must include location data from entries."""
        text = build_cluster_summary_text(sample_entries)

        # Cluster 0 has entries with location_name including San Francisco.
        assert "San Francisco" in text
        assert "California" in text

    def test_excludes_clusters_smaller_than_min_size(self, sample_entries):
        """Clusters with fewer entries than min_cluster_size should be excluded."""
        # Cluster 0 has 5 entries, cluster 1 has 3 entries.
        text = build_cluster_summary_text(sample_entries, min_cluster_size=4)

        # Cluster 0 should be included.
        assert "A beach scene" in text

        # Cluster 1 should be excluded.
        assert "A dinner gathering" not in text

    def test_excludes_home_location_clusters(self):
        """Clusters where the majority of entries are at the home location should be excluded."""
        home = Location(name="Oslo, Oslo, NO", region="Oslo, NO", country="NO")
        travel = Location(name="Antalya, Antalya, TR", region="Antalya, TR", country="TR")

        def _entry(path, cluster, location):
            return ManifestEntry(
                media_path=path,
                source=Source(type="loose"),
                metadata=Metadata(status=Status.PROCESSED, dates=["2019-07-15T14:00:00"]),
                location=location,
                discovery=Discovery(status=Status.PROCESSED, cluster=cluster),
            )

        entries = [
            # Cluster 0: travel (Antalya) — should be included.
            _entry("/photos/a1.jpg", 0, travel),
            _entry("/photos/a2.jpg", 0, travel),
            _entry("/photos/a3.jpg", 0, travel),
            # Cluster 1: home (Oslo) — should be excluded.
            _entry("/photos/h1.jpg", 1, home),
            _entry("/photos/h2.jpg", 1, home),
            _entry("/photos/h3.jpg", 1, home),
        ]

        text = build_cluster_summary_text(entries, home_region="Oslo, NO")

        # Travel cluster should be present.
        assert "Cluster 0" in text

        # Home cluster should be filtered out.
        assert "Cluster 1" not in text

    def test_no_noise_section(self, sample_entries):
        """Noise images should not appear in the cluster summary."""
        text = build_cluster_summary_text(sample_entries)
        assert "Unclustered" not in text
        assert "Unsorted" not in text
