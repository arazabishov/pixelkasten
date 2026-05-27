"""
Tests for the enrich command.

CLIP and reverse_geocoder are mocked so the suite stays fast and offline.
Tests run against a real tmp working library and inspect records +
embeddings files directly.
"""

import json
import os
from unittest.mock import patch

import numpy as np
import pytest

from pixelkasten.commands.enrich import enrich
from pixelkasten.configuration import EnrichOptions


def _make_working_library(tmp_path, records: dict[str, dict], media: dict[str, bytes]):
    """
    Build a minimal working-library layout under tmp_path/lib.

    records: filename -> record dict written to .pixelkasten/<filename>.pk.json
    media:   filename -> raw bytes written to <library>/<filename>
    """
    lib = tmp_path / "lib"
    pk = lib / ".pixelkasten"
    pk.mkdir(parents=True)
    for name, data in records.items():
        (pk / f"{name}.pk.json").write_text(json.dumps(data))
    for name, payload in media.items():
        (lib / name).write_bytes(payload)
    return str(lib)


def _read_record(library: str, name: str) -> dict:
    with open(os.path.join(library, ".pixelkasten", f"{name}.pk.json")) as f:
        return json.load(f)


class TestGeocodeStep:
    @patch("reverse_geocoder.search")
    def test_writes_location_for_records_with_geo(self, mock_rg, tmp_path):
        mock_rg.return_value = [{"name": "Berlin", "admin1": "Berlin", "cc": "DE"}]
        lib = _make_working_library(
            tmp_path,
            records={
                "a.jpg": {
                    "dates": ["2024-01-01T00:00:00"],
                    "geo": {"latitude": 52.52, "longitude": 13.40, "altitude": None},
                    "album": None,
                }
            },
            media={},
        )

        enrich(EnrichOptions(library=lib, video_frames=5))

        record = _read_record(lib, "a.jpg")
        # location now populated from the reverse-geocode result
        assert record["location"]["name"] == "Berlin, Berlin, DE"
        assert record["location"]["region"] == "Berlin, DE"
        assert record["location"]["country"] == "DE"

    @patch("reverse_geocoder.search")
    def test_skips_records_without_geo(self, mock_rg, tmp_path):
        lib = _make_working_library(
            tmp_path,
            records={
                "a.jpg": {"dates": [], "geo": None, "album": None},
            },
            media={},
        )

        enrich(EnrichOptions(library=lib, video_frames=5))

        # Nothing to geocode -> reverse_geocoder never called
        mock_rg.assert_not_called()
        # location remains absent
        record = _read_record(lib, "a.jpg")
        assert "location" not in record or record["location"] is None

    @patch("reverse_geocoder.search")
    def test_is_idempotent_when_location_already_set(self, mock_rg, tmp_path):
        existing_location = {"name": "Already", "region": "X", "country": "X"}
        lib = _make_working_library(
            tmp_path,
            records={
                "a.jpg": {
                    "dates": [],
                    "geo": {"latitude": 1.0, "longitude": 2.0, "altitude": None},
                    "album": None,
                    "location": existing_location,
                }
            },
            media={},
        )

        enrich(EnrichOptions(library=lib, video_frames=5))

        # Re-run is a no-op when location is already present
        mock_rg.assert_not_called()
        # Existing location is preserved
        record = _read_record(lib, "a.jpg")
        assert record["location"] == existing_location

    @patch("reverse_geocoder.search")
    def test_batches_unique_coords(self, mock_rg, tmp_path):
        # Two records at the same rounded coord -> a single reverse-geocode call.
        mock_rg.return_value = [{"name": "Paris", "admin1": "IDF", "cc": "FR"}]
        lib = _make_working_library(
            tmp_path,
            records={
                "a.jpg": {
                    "dates": [],
                    "geo": {"latitude": 48.8584, "longitude": 2.2945, "altitude": None},
                    "album": None,
                },
                "b.jpg": {
                    "dates": [],
                    # Same coord after rounding to 2 decimals
                    "geo": {"latitude": 48.86, "longitude": 2.29, "altitude": None},
                    "album": None,
                },
            },
            media={},
        )

        enrich(EnrichOptions(library=lib, video_frames=5))

        # One batch call covers both records
        assert mock_rg.call_count == 1
        # Both records get the same location
        assert _read_record(lib, "a.jpg")["location"]["name"] == "Paris, IDF, FR"
        assert _read_record(lib, "b.jpg")["location"]["name"] == "Paris, IDF, FR"


class TestEmbedStep:
    @patch("pixelkasten.utils.clip.embed_images")
    @patch("reverse_geocoder.search")
    def test_writes_embeddings_npy_and_paths_json(self, mock_rg, mock_embed, tmp_path):
        # Two image files, mocked CLIP returns a (2, 768) matrix from one batched call.
        mock_embed.return_value = np.full((2, 768), 0.1, dtype=np.float32)
        lib = _make_working_library(
            tmp_path,
            records={
                "a.jpg": {"dates": [], "geo": None, "album": None},
                "b.jpg": {"dates": [], "geo": None, "album": None},
            },
            media={"a.jpg": b"\xff\xd8\xff", "b.jpg": b"\xff\xd8\xff"},
        )

        with patch("PIL.Image.open") as mock_open:
            mock_open.return_value = object()
            enrich(EnrichOptions(library=lib, video_frames=5))

        # CLIP is invoked exactly once for both images
        assert mock_embed.call_count == 1
        # embeddings.npy contains 2 rows of dim 768
        matrix = np.load(os.path.join(lib, ".pixelkasten", "embeddings.npy"))
        assert matrix.shape == (2, 768)

        # embeddings.paths.json lists both filenames
        with open(os.path.join(lib, ".pixelkasten", "embeddings.paths.json")) as f:
            paths = json.load(f)
        assert set(paths) == {"a.jpg", "b.jpg"}

    @patch("pixelkasten.utils.clip.embed_images")
    @patch("reverse_geocoder.search")
    def test_skips_already_embedded_files(self, mock_rg, mock_embed, tmp_path):
        lib = _make_working_library(
            tmp_path,
            records={"a.jpg": {"dates": [], "geo": None, "album": None}},
            media={"a.jpg": b"\xff"},
        )
        # Pre-existing paths.json claims a.jpg is already embedded
        with open(os.path.join(lib, ".pixelkasten", "embeddings.paths.json"), "w") as f:
            json.dump(["a.jpg"], f)
        np.save(
            os.path.join(lib, ".pixelkasten", "embeddings.npy"),
            np.full((1, 768), 0.5, dtype=np.float32),
        )

        enrich(EnrichOptions(library=lib, video_frames=5))

        # CLIP never invoked because the only file is already embedded
        mock_embed.assert_not_called()
        # paths.json unchanged
        with open(os.path.join(lib, ".pixelkasten", "embeddings.paths.json")) as f:
            paths = json.load(f)
        assert paths == ["a.jpg"]

    def test_rejects_incomplete_embeddings_store(self, tmp_path):
        lib = _make_working_library(
            tmp_path,
            records={"a.jpg": {"dates": [], "geo": None, "album": None}},
            media={"a.jpg": b"\xff"},
        )
        with open(os.path.join(lib, ".pixelkasten", "embeddings.paths.json"), "w") as f:
            json.dump(["a.jpg"], f)

        with pytest.raises(RuntimeError, match="Incomplete embeddings"):
            enrich(EnrichOptions(library=lib, video_frames=5))

    @patch("pixelkasten.utils.clip.embed_images")
    @patch("pixelkasten.utils.ffmpeg.capture_frames")
    @patch("reverse_geocoder.search")
    def test_embeds_video_via_mean_of_frame_embeddings(
        self, mock_rg, mock_extract, mock_embed, tmp_path
    ):
        mock_extract.return_value = [b"f1", b"f2", b"f3"]
        # Three frame embeddings; mean should be normalized to unit length.
        mock_embed.return_value = np.array(
            [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
            dtype=np.float32,
        )
        lib = _make_working_library(
            tmp_path,
            records={"v.mp4": {"dates": [], "geo": None, "album": None}},
            media={"v.mp4": b"fake-video"},
        )

        with patch("PIL.Image.open") as mock_image:
            mock_image.return_value = object()
            enrich(EnrichOptions(library=lib, video_frames=3))

        matrix = np.load(os.path.join(lib, ".pixelkasten", "embeddings.npy"))
        # One row written for the video
        assert matrix.shape == (1, 3)
        # The video's embedding is the L2-normalized mean of frame embeddings
        norm = np.linalg.norm(matrix[0])
        assert abs(norm - 1.0) < 1e-5
        # frame extraction was called with the configured frame count
        mock_extract.assert_called_once_with(os.path.join(lib, "v.mp4"), 3)

    @patch("pixelkasten.utils.clip.embed_images")
    @patch("reverse_geocoder.search")
    def test_logs_and_skips_on_embed_failure(self, mock_rg, mock_embed, tmp_path, capsys):
        # CLIP raises -> file is skipped, not aborted.
        mock_embed.side_effect = RuntimeError("CLIP crashed")
        lib = _make_working_library(
            tmp_path,
            records={"bad.jpg": {"dates": [], "geo": None, "album": None}},
            media={"bad.jpg": b"corrupt"},
        )

        with patch("PIL.Image.open") as mock_open:
            mock_open.return_value = object()
            enrich(EnrichOptions(library=lib, video_frames=5))

        # Error message printed to stderr; no embeddings file written
        captured = capsys.readouterr()
        assert "skipping" in captured.err
        assert not os.path.exists(os.path.join(lib, ".pixelkasten", "embeddings.npy"))


class TestEnrichValidation:
    def test_rejects_missing_library(self, tmp_path):
        missing = tmp_path / "missing-library"

        with pytest.raises(FileNotFoundError, match="Library directory not found"):
            enrich(EnrichOptions(library=str(missing), video_frames=5))

    def test_rejects_non_working_library(self, tmp_path):
        bare = tmp_path / "not-a-library"
        bare.mkdir()

        with pytest.raises(FileNotFoundError, match="Working library records not found"):
            enrich(EnrichOptions(library=str(bare), video_frames=5))


class TestEnrichState:
    """Verifies the EnrichState returned by enrich() reflects what changed."""

    @patch("pixelkasten.utils.clip.embed_images")
    @patch("reverse_geocoder.search")
    def test_counts_match_what_was_written(self, mock_rg, mock_embed, tmp_path):
        mock_rg.return_value = [{"name": "Berlin", "admin1": "Berlin", "cc": "DE"}]
        mock_embed.return_value = np.full((1, 768), 0.1, dtype=np.float32)
        lib = _make_working_library(
            tmp_path,
            records={
                "a.jpg": {
                    "dates": [],
                    "geo": {"latitude": 52.52, "longitude": 13.40, "altitude": None},
                    "album": None,
                }
            },
            media={"a.jpg": b"image-bytes"},
        )

        with patch("PIL.Image.open") as mock_open:
            mock_open.return_value = object()
            summary = enrich(EnrichOptions(library=lib, video_frames=5))

        # Verify totals match what landed on disk
        assert summary.records_total == 1
        assert summary.locations_added == 1
        assert summary.locations_already_set == 0
        assert summary.images_embedded == 1
        assert summary.videos_embedded == 0
        assert summary.images_already_embedded == 0
        assert summary.videos_already_embedded == 0
        assert summary.unsupported_media == []
        assert summary.images_failed == []
        assert summary.videos_failed == []

    @patch("reverse_geocoder.search")
    def test_reports_unsupported_top_level_files(self, mock_rg, tmp_path):
        lib = _make_working_library(
            tmp_path,
            records={},
            media={"notes.txt": b"not-media"},
        )

        summary = enrich(EnrichOptions(library=lib, video_frames=5))

        # Verify unsupported top-level files are captured for reporting
        assert [os.path.basename(p) for p in summary.unsupported_media] == ["notes.txt"]
        # No records with geo -> geocoder is not called
        mock_rg.assert_not_called()

    @patch("pixelkasten.utils.clip.embed_images")
    @patch("reverse_geocoder.search")
    def test_rerun_reports_zero_new_work(self, mock_rg, mock_embed, tmp_path):
        mock_rg.return_value = [{"name": "Berlin", "admin1": "Berlin", "cc": "DE"}]
        mock_embed.return_value = np.full((1, 768), 0.1, dtype=np.float32)
        lib = _make_working_library(
            tmp_path,
            records={
                "a.jpg": {
                    "dates": [],
                    "geo": {"latitude": 52.52, "longitude": 13.40, "altitude": None},
                    "album": None,
                }
            },
            media={"a.jpg": b"image-bytes"},
        )

        with patch("PIL.Image.open") as mock_open:
            mock_open.return_value = object()
            enrich(EnrichOptions(library=lib, video_frames=5))
            # Re-run: everything is idempotent
            summary = enrich(EnrichOptions(library=lib, video_frames=5))

        # Verify the second pass adds nothing
        assert summary.locations_added == 0
        # The record's location was set in the first run
        assert summary.locations_already_set == 1
        # The image is already in embeddings.paths.json
        assert summary.images_already_embedded == 1
        assert summary.videos_already_embedded == 0
        assert summary.images_embedded == 0

    @patch("pixelkasten.utils.clip.embed_images")
    @patch("reverse_geocoder.search")
    def test_failed_image_appears_in_images_failed(self, mock_rg, mock_embed, tmp_path):
        mock_rg.return_value = []
        # Whole-batch failure simulates a CLIP forward-pass crash
        mock_embed.side_effect = RuntimeError("CLIP died")
        lib = _make_working_library(
            tmp_path,
            records={"a.jpg": {"dates": [], "geo": None, "album": None}},
            media={"a.jpg": b"image-bytes"},
        )

        with patch("PIL.Image.open") as mock_open:
            mock_open.return_value = object()
            summary = enrich(EnrichOptions(library=lib, video_frames=5))

        # The failed image path is recorded for the renderer
        assert any(p.endswith("a.jpg") for p in summary.images_failed)
        # And no image got embedded
        assert summary.images_embedded == 0
