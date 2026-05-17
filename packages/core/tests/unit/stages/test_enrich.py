"""
Tests for the enrich stage.

CLIP and reverse_geocoder are mocked so the suite stays fast and offline.
Tests run against a real tmp working library (init's output shape) and
inspect sidecar JSON + embeddings files directly.
"""

import json
import os
from unittest.mock import patch

import numpy as np
import pytest

from pixelkasten.configuration import EnrichOptions
from pixelkasten.stages.enrich import enrich


def _make_working_library(tmp_path, sidecars: dict[str, dict], media: dict[str, bytes]):
    """
    Build a minimal working-library layout under tmp_path/lib.

    sidecars: filename -> sidecar dict written to .pixelkasten/<filename>.pk.json
    media:    filename -> raw bytes written to <library>/<filename>
    """
    lib = tmp_path / "lib"
    pk = lib / ".pixelkasten"
    pk.mkdir(parents=True)
    for name, data in sidecars.items():
        (pk / f"{name}.pk.json").write_text(json.dumps(data))
    for name, payload in media.items():
        (lib / name).write_bytes(payload)
    return str(lib)


def _read_sidecar(library: str, name: str) -> dict:
    with open(os.path.join(library, ".pixelkasten", f"{name}.pk.json")) as f:
        return json.load(f)


class TestGeocodeStep:
    @patch("reverse_geocoder.search")
    def test_writes_location_for_sidecars_with_geo(self, mock_rg, tmp_path):
        mock_rg.return_value = [{"name": "Berlin", "admin1": "Berlin", "cc": "DE"}]
        lib = _make_working_library(
            tmp_path,
            sidecars={
                "a.jpg": {
                    "dates": ["2024-01-01T00:00:00"],
                    "geo": {"latitude": 52.52, "longitude": 13.40, "altitude": None},
                    "album": None,
                }
            },
            media={},
        )

        enrich(EnrichOptions(library=lib))

        sidecar = _read_sidecar(lib, "a.jpg")
        # location now populated from the reverse-geocode result
        assert sidecar["location"]["name"] == "Berlin, Berlin, DE"
        assert sidecar["location"]["region"] == "Berlin, DE"
        assert sidecar["location"]["country"] == "DE"

    @patch("reverse_geocoder.search")
    def test_skips_sidecars_without_geo(self, mock_rg, tmp_path):
        lib = _make_working_library(
            tmp_path,
            sidecars={
                "a.jpg": {"dates": [], "geo": None, "album": None},
            },
            media={},
        )

        enrich(EnrichOptions(library=lib))

        # Nothing to geocode -> reverse_geocoder never called
        mock_rg.assert_not_called()
        # location remains absent
        sidecar = _read_sidecar(lib, "a.jpg")
        assert "location" not in sidecar or sidecar["location"] is None

    @patch("reverse_geocoder.search")
    def test_is_idempotent_when_location_already_set(self, mock_rg, tmp_path):
        existing_location = {"name": "Already", "region": "X", "country": "X"}
        lib = _make_working_library(
            tmp_path,
            sidecars={
                "a.jpg": {
                    "dates": [],
                    "geo": {"latitude": 1.0, "longitude": 2.0, "altitude": None},
                    "album": None,
                    "location": existing_location,
                }
            },
            media={},
        )

        enrich(EnrichOptions(library=lib))

        # Re-run is a no-op when location is already present
        mock_rg.assert_not_called()
        # Existing location is preserved
        sidecar = _read_sidecar(lib, "a.jpg")
        assert sidecar["location"] == existing_location

    @patch("reverse_geocoder.search")
    def test_batches_unique_coords(self, mock_rg, tmp_path):
        # Two sidecars at the same rounded coord -> a single reverse-geocode call.
        mock_rg.return_value = [{"name": "Paris", "admin1": "IDF", "cc": "FR"}]
        lib = _make_working_library(
            tmp_path,
            sidecars={
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

        enrich(EnrichOptions(library=lib))

        # One batch call covers both sidecars
        assert mock_rg.call_count == 1
        # Both sidecars get the same location
        assert _read_sidecar(lib, "a.jpg")["location"]["name"] == "Paris, IDF, FR"
        assert _read_sidecar(lib, "b.jpg")["location"]["name"] == "Paris, IDF, FR"


class TestEmbedStep:
    @patch("pixelkasten.tools.clip_embed.embed_images")
    @patch("reverse_geocoder.search")
    def test_writes_embeddings_npy_and_paths_json(self, mock_rg, mock_embed, tmp_path):
        # Two image files, mocked CLIP returns a (2, 768) matrix from one batched call.
        mock_embed.return_value = np.full((2, 768), 0.1, dtype=np.float32)
        lib = _make_working_library(
            tmp_path,
            sidecars={
                "a.jpg": {"dates": [], "geo": None, "album": None},
                "b.jpg": {"dates": [], "geo": None, "album": None},
            },
            media={"a.jpg": b"\xff\xd8\xff", "b.jpg": b"\xff\xd8\xff"},
        )

        with patch("PIL.Image.open") as mock_open:
            mock_open.return_value = object()  # PIL image stand-in; embed_images is mocked
            enrich(EnrichOptions(library=lib))

        # CLIP is invoked exactly once for both images
        assert mock_embed.call_count == 1
        # embeddings.npy contains 2 rows of dim 768
        matrix = np.load(os.path.join(lib, ".pixelkasten", "embeddings.npy"))
        assert matrix.shape == (2, 768)

        # embeddings.paths.json lists both filenames
        with open(os.path.join(lib, ".pixelkasten", "embeddings.paths.json")) as f:
            paths = json.load(f)
        assert set(paths) == {"a.jpg", "b.jpg"}

    @patch("pixelkasten.tools.clip_embed.embed_images")
    @patch("reverse_geocoder.search")
    def test_skips_already_embedded_files(self, mock_rg, mock_embed, tmp_path):
        lib = _make_working_library(
            tmp_path,
            sidecars={"a.jpg": {"dates": [], "geo": None, "album": None}},
            media={"a.jpg": b"\xff"},
        )
        # Pre-existing paths.json claims a.jpg is already embedded
        with open(os.path.join(lib, ".pixelkasten", "embeddings.paths.json"), "w") as f:
            json.dump(["a.jpg"], f)
        np.save(
            os.path.join(lib, ".pixelkasten", "embeddings.npy"),
            np.full((1, 768), 0.5, dtype=np.float32),
        )

        enrich(EnrichOptions(library=lib))

        # CLIP never invoked because the only file is already embedded
        mock_embed.assert_not_called()
        # paths.json unchanged
        with open(os.path.join(lib, ".pixelkasten", "embeddings.paths.json")) as f:
            paths = json.load(f)
        assert paths == ["a.jpg"]

    @patch("pixelkasten.tools.clip_embed.embed_images")
    @patch("pixelkasten.tools.ffmpeg.extract_frames")
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
            sidecars={"v.mp4": {"dates": [], "geo": None, "album": None}},
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

    @patch("pixelkasten.tools.clip_embed.embed_images")
    @patch("reverse_geocoder.search")
    def test_logs_and_skips_on_embed_failure(self, mock_rg, mock_embed, tmp_path, capsys):
        # CLIP raises -> file is skipped, not aborted.
        mock_embed.side_effect = RuntimeError("CLIP crashed")
        lib = _make_working_library(
            tmp_path,
            sidecars={"bad.jpg": {"dates": [], "geo": None, "album": None}},
            media={"bad.jpg": b"corrupt"},
        )

        with patch("PIL.Image.open") as mock_open:
            mock_open.return_value = object()
            enrich(EnrichOptions(library=lib))

        # Error message printed to stderr; no embeddings file written
        captured = capsys.readouterr()
        assert "skipping" in captured.err
        assert not os.path.exists(os.path.join(lib, ".pixelkasten", "embeddings.npy"))


class TestCaptionGate:
    @patch("pixelkasten.tools.clip_embed.embed_images")
    @patch("reverse_geocoder.search")
    def test_does_not_run_captioning_without_flag(self, mock_rg, mock_embed, tmp_path, capsys):
        lib = _make_working_library(
            tmp_path,
            sidecars={"a.jpg": {"dates": [], "geo": None, "album": None}},
            media={},
        )

        enrich(EnrichOptions(library=lib))

        captured = capsys.readouterr()
        # No captioning-related message without the flag
        assert "caption" not in captured.err.lower()

    @patch("pixelkasten.tools.clip_embed.embed_images")
    @patch("reverse_geocoder.search")
    def test_with_captions_surfaces_pending_message(self, mock_rg, mock_embed, tmp_path, capsys):
        # Until Phase 10 wires bulk captioning, --with-captions surfaces a
        # clear message so users aren't silently no-op'd.
        lib = _make_working_library(
            tmp_path,
            sidecars={"a.jpg": {"dates": [], "geo": None, "album": None}},
            media={},
        )

        enrich(EnrichOptions(library=lib, with_captions=True))

        captured = capsys.readouterr()
        assert "caption" in captured.err.lower()


class TestEnrichValidation:
    def test_rejects_non_working_library(self, tmp_path):
        bare = tmp_path / "not-a-library"
        bare.mkdir()

        with pytest.raises(RuntimeError, match="working library"):
            enrich(EnrichOptions(library=str(bare)))
