"""
Unit tests for the organize module's pure logic functions:
- _date_directory_from_timestamp
- _parse_llm_response
- build_organization_plan
- build_cluster_summary_text
"""

import pytest

from pixelkasten_ai.organize import (
    _date_directory_from_timestamp,
    _parse_llm_response,
    build_organization_plan,
    build_cluster_summary_text,
)


# ---------------------------------------------------------------------------
# _date_directory_from_timestamp
# ---------------------------------------------------------------------------


class TestDateDirectoryFromTimestamp:
    def test_valid_timestamp_returns_year(self):
        result = _date_directory_from_timestamp("2019-07-15T14:30:00")
        assert result == "2019"

    def test_none_returns_none(self):
        result = _date_directory_from_timestamp(None)
        assert result is None

    def test_empty_string_returns_none(self):
        result = _date_directory_from_timestamp("")
        assert result is None

    def test_december_timestamp_returns_correct_year(self):
        result = _date_directory_from_timestamp("2024-12-25T18:00:00")
        assert result == "2024"


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
# build_organization_plan (uses sample_manifest fixture from conftest)
# ---------------------------------------------------------------------------


class TestBuildOrganizationPlan:
    def test_clustered_image_placed_in_cluster_directory(self, sample_manifest):
        """An image belonging to a multi-image cluster goes to the LLM-proposed directory."""
        cluster_dirs = {
            "0": "2019/20190715 - Bay Area Trip",
            "1": "2019/20190820 - Dinner Party",
        }
        plan = build_organization_plan(sample_manifest, cluster_dirs)

        # Entry 0 belongs to cluster 0 (size 5), should be placed under the
        # cluster's proposed directory.
        entry_0 = next(p for p in plan if p["source"] == "/photos/img_001.jpg")
        assert entry_0["target"] == "2019/20190715 - Bay Area Trip/img_001.jpg"
        assert entry_0["cluster"] == 0

    def test_single_image_cluster_with_timestamp_placed_in_year_directory(self):
        """A single-image cluster with a timestamp goes into the year dir, not the event dir."""
        manifest = {
            "entries": [
                {
                    "path": "/photos/solo.jpg",
                    "status": "ok",
                    "cluster": 5,
                    "tags": [],
                    "exif": {
                        "timestamp": "2022-03-10T08:00:00",
                    },
                },
            ],
            "clusters": {
                "5": {
                    "size": 1,
                },
            },
        }
        cluster_dirs = {
            "5": "2022/20220310 - Random Photo",
        }
        plan = build_organization_plan(manifest, cluster_dirs)

        assert len(plan) == 1
        assert plan[0]["target"] == "2022/solo.jpg"
        assert "Single-image cluster" in plan[0]["reason"]

    def test_noise_image_with_timestamp_placed_in_year_directory(self, sample_manifest):
        """A noise image (cluster -1) with an EXIF timestamp goes into the year dir."""
        cluster_dirs = {
            "0": "2019/20190715 - Bay Area Trip",
            "1": "2019/20190820 - Dinner Party",
        }
        plan = build_organization_plan(sample_manifest, cluster_dirs)

        # Entry 8 is noise (cluster -1) with timestamp "2019-09-01T12:00:00".
        noise_entry = next(p for p in plan if p["source"] == "/photos/img_009.jpg")
        assert noise_entry["target"] == "2019/img_009.jpg"
        assert noise_entry["cluster"] == -1

    def test_noise_image_without_timestamp_goes_to_unsorted(self):
        """A noise image with no EXIF timestamp at all lands in Unsorted/."""
        manifest = {
            "entries": [
                {
                    "path": "/photos/mystery.jpg",
                    "status": "ok",
                    "cluster": -1,
                    "tags": [],
                    "exif": {
                        "timestamp": None,
                        "gps": None,
                    },
                },
            ],
            "clusters": {},
        }
        plan = build_organization_plan(manifest, {})

        assert len(plan) == 1
        assert plan[0]["target"] == "Unsorted/mystery.jpg"
        assert plan[0]["reason"] == "Unclustered, no date available"

    def test_failed_image_is_skipped(self, sample_manifest):
        """An image with status 'failed' does not appear in the plan at all."""
        cluster_dirs = {
            "0": "2019/20190715 - Bay Area Trip",
            "1": "2019/20190820 - Dinner Party",
        }
        plan = build_organization_plan(sample_manifest, cluster_dirs)

        # Entry 9 has status "failed" and should be absent from the plan.
        sources = [p["source"] for p in plan]
        assert "/photos/img_010.jpg" not in sources


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
