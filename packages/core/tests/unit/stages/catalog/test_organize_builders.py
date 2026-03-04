"""
Unit tests for the organize module's pure logic functions:
- _parse_llm_response
- build_cluster_summary_text
"""

import pytest

from pixelkasten.stages.catalog.organize import (
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
        raw = (
            "Here is the proposed structure:\n"
            '{"5": "Christmas Dinner"}\n'
            "I hope this helps!"
        )
        result = _parse_llm_response(raw)
        assert result == {"5": "Christmas Dinner"}

    def test_completely_invalid_text_raises_value_error(self):
        raw = "Sorry, I cannot process this request."
        with pytest.raises(ValueError, match="LLM did not return valid JSON"):
            _parse_llm_response(raw)


class TestBuildClusterSummaryText:
    def test_output_includes_captions_tags_and_date_range(self, sample_manifest):
        """The summary text must contain captions, tags, and date range for each cluster."""
        text = build_cluster_summary_text(sample_manifest)

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

    def test_output_includes_location_info(self, sample_manifest):
        """The summary text must include location data from entries."""
        text = build_cluster_summary_text(sample_manifest)

        # Cluster 0 has entries with location_name including San Francisco.
        assert "San Francisco" in text
        assert "California" in text

    def test_no_noise_section(self, sample_manifest):
        """Noise images should not appear in the cluster summary."""
        text = build_cluster_summary_text(sample_manifest)
        assert "Unclustered" not in text
        assert "Unsorted" not in text
