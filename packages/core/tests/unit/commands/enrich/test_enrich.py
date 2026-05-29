"""
Tests for the enrich command.

CLIP and reverse_geocoder are mocked so the suite stays fast and offline.
Tests run against a real tmp working library and inspect records +
embeddings files (or the returned state) directly.
"""

import json
import os
from unittest.mock import patch

import numpy as np
import pytest

from pixelkasten.commands.enrich import enrich
from pixelkasten.configuration import EnrichOptions
from pixelkasten.pipeline import Status


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


def _write_store(library: str, names: list[str]) -> None:
    """Write a pre-existing embeddings store so a re-run can be shown to overwrite it."""
    with open(os.path.join(library, ".pixelkasten", "embeddings.paths.json"), "w") as f:
        json.dump(names, f)
    np.save(
        os.path.join(library, ".pixelkasten", "embeddings.npy"),
        np.full((len(names), 768), 0.5, dtype=np.float32),
    )


@pytest.fixture
def fake_clip():
    """Neutralize CLIP so a test can exercise the pipeline without loading the
    real model. Yields the embed_images mock for tests that assert on it or
    want to override its behavior (e.g. simulate a forward-pass crash)."""
    with (
        patch("PIL.Image.open", return_value=object()),
        patch("pixelkasten.utils.clip.embed_images") as mock_embed,
    ):
        mock_embed.side_effect = lambda images: np.full((len(images), 768), 0.1, dtype=np.float32)
        yield mock_embed


class TestGeocodeStep:
    @patch("reverse_geocoder.search")
    def test_writes_location_for_records_with_geo(self, mock_rg, fake_clip, tmp_path):
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
            media={"a.jpg": b"image-bytes"},
        )

        enrich(EnrichOptions(library=lib, video_frames=5))

        record = _read_record(lib, "a.jpg")
        # location: atomic fields straight from the reverse-geocode result
        assert record["location"] == {"city": "Berlin", "region": "Berlin", "country": "DE"}

    @patch("reverse_geocoder.search")
    def test_skips_records_without_geo(self, mock_rg, fake_clip, tmp_path):
        lib = _make_working_library(
            tmp_path,
            records={"a.jpg": {"dates": [], "geo": None, "album": None}},
            media={"a.jpg": b"image-bytes"},
        )

        enrich(EnrichOptions(library=lib, video_frames=5))

        # Nothing to geocode -> reverse_geocoder never called
        mock_rg.assert_not_called()
        # location remains absent
        record = _read_record(lib, "a.jpg")
        assert "location" not in record or record["location"] is None

    @patch("reverse_geocoder.search")
    def test_recomputes_location_even_when_already_set(self, mock_rg, fake_clip, tmp_path):
        mock_rg.return_value = [{"name": "Berlin", "admin1": "Berlin", "cc": "DE"}]
        stale = {"name": "Stale", "region": "X", "country": "X"}
        lib = _make_working_library(
            tmp_path,
            records={
                "a.jpg": {
                    "dates": [],
                    "geo": {"latitude": 52.52, "longitude": 13.40, "altitude": None},
                    "album": None,
                    "location": stale,
                }
            },
            media={"a.jpg": b"image-bytes"},
        )

        enrich(EnrichOptions(library=lib, video_frames=5))

        # No resume: a record with geo is geocoded again, overwriting the stale value
        mock_rg.assert_called_once()
        record = _read_record(lib, "a.jpg")
        assert record["location"] == {"city": "Berlin", "region": "Berlin", "country": "DE"}

    @patch("reverse_geocoder.search")
    def test_geocodes_all_records_in_one_search_call(self, mock_rg, fake_clip, tmp_path):
        # rg.search returns one hit per input coord, in order; here two distinct places.
        mock_rg.return_value = [
            {"name": "Paris", "admin1": "IDF", "cc": "FR"},
            {"name": "Lyon", "admin1": "ARA", "cc": "FR"},
        ]
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
                    "geo": {"latitude": 45.76, "longitude": 4.84, "altitude": None},
                    "album": None,
                },
            },
            media={"a.jpg": b"image-bytes", "b.jpg": b"image-bytes"},
        )

        enrich(EnrichOptions(library=lib, video_frames=5))

        # All geo'd records are reverse-geocoded in a single batched call, in input order
        assert mock_rg.call_count == 1
        assert _read_record(lib, "a.jpg")["location"]["city"] == "Paris"
        assert _read_record(lib, "b.jpg")["location"]["city"] == "Lyon"


class TestEmbedStep:
    def test_writes_embeddings_npy_and_paths_json(self, fake_clip, tmp_path):
        lib = _make_working_library(
            tmp_path,
            records={
                "a.jpg": {"dates": [], "geo": None, "album": None},
                "b.jpg": {"dates": [], "geo": None, "album": None},
            },
            media={"a.jpg": b"\xff\xd8\xff", "b.jpg": b"\xff\xd8\xff"},
        )

        enrich(EnrichOptions(library=lib, video_frames=5))

        # CLIP invoked once for both images in a single batch
        assert fake_clip.call_count == 1
        matrix = np.load(os.path.join(lib, ".pixelkasten", "embeddings.npy"))
        assert matrix.shape == (2, 768)
        with open(os.path.join(lib, ".pixelkasten", "embeddings.paths.json")) as f:
            paths = json.load(f)
        assert set(paths) == {"a.jpg", "b.jpg"}

    def test_overwrites_existing_store_each_run(self, fake_clip, tmp_path):
        lib = _make_working_library(
            tmp_path,
            records={"a.jpg": {"dates": [], "geo": None, "album": None}},
            media={"a.jpg": b"\xff"},
        )
        # A prior store exists; no-resume means this run rebuilds it from scratch.
        _write_store(lib, ["a.jpg", "stale.jpg"])

        enrich(EnrichOptions(library=lib, video_frames=5))

        # CLIP runs again (no skip), and the store reflects only this run's media
        assert fake_clip.call_count == 1
        with open(os.path.join(lib, ".pixelkasten", "embeddings.paths.json")) as f:
            paths = json.load(f)
        assert paths == ["a.jpg"]

    @patch("pixelkasten.utils.clip.embed_images")
    @patch("pixelkasten.utils.ffmpeg.capture_frames")
    def test_embeds_video_via_mean_of_frame_embeddings(self, mock_extract, mock_embed, tmp_path):
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

        with patch("PIL.Image.open", return_value=object()):
            enrich(EnrichOptions(library=lib, video_frames=3))

        matrix = np.load(os.path.join(lib, ".pixelkasten", "embeddings.npy"))
        # One row written for the video
        assert matrix.shape == (1, 3)
        # The video's embedding is the L2-normalized mean of frame embeddings
        norm = np.linalg.norm(matrix[0])
        assert abs(norm - 1.0) < 1e-5
        # frame extraction was called with the configured frame count
        mock_extract.assert_called_once_with(os.path.join(lib, "v.mp4"), 3)

    def test_batch_clip_failure_is_fatal(self, fake_clip, tmp_path):
        # A hard CLIP failure aborts the run (fail fast), like a broken exiftool
        # aborts import — rather than silently marking everything failed.
        fake_clip.side_effect = RuntimeError("CLIP died")
        lib = _make_working_library(
            tmp_path,
            records={"a.jpg": {"dates": [], "geo": None, "album": None}},
            media={"a.jpg": b"image-bytes"},
        )

        with pytest.raises(RuntimeError, match="CLIP died"):
            enrich(EnrichOptions(library=lib, video_frames=5))

        # The run aborts before emit, so no store is written
        assert not os.path.exists(os.path.join(lib, ".pixelkasten", "embeddings.npy"))

    @patch("pixelkasten.utils.clip.embed_images")
    def test_per_file_decode_failure_is_isolated(self, mock_embed, tmp_path):
        # One unreadable image is marked ERROR; the rest still embed and the run continues.
        mock_embed.side_effect = lambda imgs: np.full((len(imgs), 768), 0.1, dtype=np.float32)

        def fake_open(path):
            if path.endswith("bad.jpg"):
                raise OSError("cannot identify image file")
            return object()

        lib = _make_working_library(
            tmp_path,
            records={
                "good.jpg": {"dates": [], "geo": None, "album": None},
                "bad.jpg": {"dates": [], "geo": None, "album": None},
            },
            media={"good.jpg": b"\xff\xd8\xff", "bad.jpg": b"garbage"},
        )

        with patch("PIL.Image.open", side_effect=fake_open):
            summary = enrich(EnrichOptions(library=lib, video_frames=5))

        by_name = {os.path.basename(e.media): e for e in summary.entries}
        # the corrupt file is isolated as ERROR; the good one is embedded
        assert by_name["bad.jpg"].embed.status == Status.ERROR
        assert by_name["good.jpg"].embed.status == Status.PROCESSED
        # only the good file lands in the store
        with open(os.path.join(lib, ".pixelkasten", "embeddings.paths.json")) as f:
            assert json.load(f) == ["good.jpg"]


class TestEnrichValidation:
    def test_rejects_missing_library(self, tmp_path):
        missing = tmp_path / "missing-library"

        with pytest.raises(FileNotFoundError, match="Working library records not found"):
            enrich(EnrichOptions(library=str(missing), video_frames=5))

    def test_rejects_non_working_library(self, tmp_path):
        bare = tmp_path / "not-a-library"
        bare.mkdir()

        with pytest.raises(FileNotFoundError, match="Working library records not found"):
            enrich(EnrichOptions(library=str(bare), video_frames=5))


class TestEnrichState:
    """Verifies the EnrichState returned by enrich() reflects what changed."""

    @patch("reverse_geocoder.search")
    def test_state_reflects_what_was_written(self, mock_rg, fake_clip, tmp_path):
        mock_rg.return_value = [{"name": "Berlin", "admin1": "Berlin", "cc": "DE"}]
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

        summary = enrich(EnrichOptions(library=lib, video_frames=5))

        # One paired entry, geocoded and embedded
        assert len(summary.entries) == 1
        entry = summary.entries[0]
        assert entry.location is not None
        assert entry.embed.status == Status.PROCESSED
        # No leftover files on either side
        assert summary.unmatched_media == []
        assert summary.unmatched_records == []
        assert summary.unsupported_media == []

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

    @patch("reverse_geocoder.search")
    def test_reports_supported_media_without_record(self, mock_rg, tmp_path):
        lib = _make_working_library(
            tmp_path,
            records={},
            media={"orphan.jpg": b"image-bytes"},
        )

        summary = enrich(EnrichOptions(library=lib, video_frames=5))

        # Verify supported media without a record is captured for reporting
        assert [os.path.basename(p) for p in summary.unmatched_media] == ["orphan.jpg"]
        # No paired entries -> geocoder is not called
        mock_rg.assert_not_called()

    @patch("reverse_geocoder.search")
    def test_reports_records_without_matching_media(self, mock_rg, tmp_path):
        # Record exists but its media file was deleted from the library root.
        lib = _make_working_library(
            tmp_path,
            records={"ghost.jpg": {"dates": [], "geo": None, "album": None}},
            media={},
        )

        summary = enrich(EnrichOptions(library=lib, video_frames=5))

        # Verify the unmatched record path is captured for reporting
        assert len(summary.unmatched_records) == 1
        assert summary.unmatched_records[0].endswith("ghost.jpg.pk.json")
        # No paired entries -> geocoder is not called
        mock_rg.assert_not_called()

    @patch("reverse_geocoder.search")
    def test_rerun_redoes_all_work(self, mock_rg, fake_clip, tmp_path):
        mock_rg.return_value = [{"name": "Berlin", "admin1": "Berlin", "cc": "DE"}]
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

        enrich(EnrichOptions(library=lib, video_frames=5))
        summary = enrich(EnrichOptions(library=lib, video_frames=5))

        # No resume: the second run geocodes and embeds the same file again
        assert mock_rg.call_count == 2
        assert fake_clip.call_count == 2
        assert summary.entries[0].location is not None
        assert summary.entries[0].embed.status == Status.PROCESSED


class TestDryRun:
    @patch("reverse_geocoder.search")
    def test_populates_state_without_touching_disk(self, mock_rg, fake_clip, tmp_path):
        mock_rg.return_value = [{"name": "Berlin", "admin1": "Berlin", "cc": "DE"}]
        lib = _make_working_library(
            tmp_path,
            records={
                "a.jpg": {
                    "dates": [],
                    "geo": {"latitude": 52.52, "longitude": 13.40, "altitude": None},
                    "album": None,
                }
            },
            media={"a.jpg": b"\xff\xd8\xff"},
        )

        summary = enrich(EnrichOptions(library=lib, video_frames=5, dry_run=True))

        # The work is computed and staged on the entry...
        entry = summary.entries[0]
        assert entry.location is not None
        assert entry.embed.status == Status.PROCESSED
        assert entry.embed.embedding.shape == (768,)

        # ...but emit never ran: the record has no location and no store exists
        record = _read_record(lib, "a.jpg")
        assert "location" not in record or record["location"] is None
        assert not os.path.exists(os.path.join(lib, ".pixelkasten", "embeddings.npy"))
        assert not os.path.exists(os.path.join(lib, ".pixelkasten", "embeddings.paths.json"))
