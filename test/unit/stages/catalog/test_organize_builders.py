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


# ---------------------------------------------------------------------------
# _parse_llm_response
# ---------------------------------------------------------------------------


class TestParseLlmResponse:
    def test_clean_json_string(self):
        raw = '{"0": "2019/20190715 - Beach Vacation", "1": "2019/20190820 - Dinner"}'
        result = _parse_llm_response(raw)
        assert result == {
            "0": "2019/20190715 - Beach Vacation",
            "1": "2019/20190820 - Dinner",
        }

    def test_json_wrapped_in_markdown_fences(self):
        raw = '```json\n{"0": "2019/20190715 - Beach Vacation"}\n```'
        result = _parse_llm_response(raw)
        assert result == {"0": "2019/20190715 - Beach Vacation"}

    def test_json_with_surrounding_explanation_text(self):
        raw = (
            "Here is the proposed directory structure:\n"
            '{"5": "2023/20231225 - Christmas Dinner"}\n'
            "I hope this helps!"
        )
        result = _parse_llm_response(raw)
        assert result == {"5": "2023/20231225 - Christmas Dinner"}

    def test_completely_invalid_text_raises_value_error(self):
        raw = "Sorry, I cannot process this request."
        with pytest.raises(ValueError, match="LLM did not return valid JSON"):
            _parse_llm_response(raw)


# ---------------------------------------------------------------------------
# build_cluster_summary_text (uses sample_manifest fixture from conftest)
# ---------------------------------------------------------------------------


class TestBuildClusterSummaryText:
    def test_output_includes_captions_tags_and_date_range(self, sample_manifest):
        """The summary text must contain captions, tags, and date range for each cluster."""
        text = build_cluster_summary_text(sample_manifest)

        # Cluster 0 caption.
        assert "A beach scene" in text

        # Cluster 0 tags.
        assert "scene:beach" in text

        # Cluster 0 date range.
        assert "2019-07-15T14:30:00" in text
        assert "2019-07-17T11:00:00" in text

        # Cluster 1 caption.
        assert "A dinner gathering" in text

        # Cluster 1 date range.
        assert "2019-08-20T19:00:00" in text
        assert "2019-08-20T21:00:00" in text

    def test_output_includes_noise_count(self, sample_manifest):
        """The summary must report unclustered (noise) images and their count."""
        text = build_cluster_summary_text(sample_manifest)

        # One noise entry in sample_manifest (img_009, cluster -1, status ok).
        assert "Unclustered images (1 images)" in text
        assert "Unsorted" in text
