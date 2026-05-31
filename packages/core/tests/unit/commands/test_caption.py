"""Tests for tools/caption.py — VLM captioning of one asset."""

import json
import os
from unittest.mock import patch

from PIL import Image

from pixelkasten.commands.caption import caption

TEST_MODEL = "gemma4:e4b"
TEST_VIDEO_FRAMES = 5


def _run_caption(path: str, **overrides):
    kwargs = {"model": TEST_MODEL, "video_frames": TEST_VIDEO_FRAMES, **overrides}
    return caption(path, **kwargs)


def _make_library_with_asset(tmp_path, asset_name: str, content: bytes, sidecar: dict):
    lib = tmp_path / "lib"
    pk = lib / ".pixelkasten"
    pk.mkdir(parents=True)
    (lib / asset_name).write_bytes(content)
    (pk / f"{asset_name}.pk.json").write_text(json.dumps(sidecar))
    return str(lib)


def _make_image_library(tmp_path, asset_name="photo.jpg", sidecar=None):
    sidecar = sidecar or {"dates": [], "geo": None, "album": None}
    lib = tmp_path / "lib"
    pk = lib / ".pixelkasten"
    pk.mkdir(parents=True)
    img = Image.new("RGB", (32, 32), color="red")
    img.save(str(lib / asset_name), format="JPEG")
    (pk / f"{asset_name}.pk.json").write_text(json.dumps(sidecar))
    return str(lib)


def _read_sidecar(library: str, name: str) -> dict:
    with open(os.path.join(library, ".pixelkasten", f"{name}.pk.json")) as f:
        return json.load(f)


class TestCaptionImage:
    @patch("pixelkasten.tools.ollama.chat")
    def test_runs_ollama_and_writes_caption_to_sidecar(self, mock_chat, tmp_path):
        mock_chat.return_value = "A red square."
        lib = _make_image_library(tmp_path)

        result = _run_caption(os.path.join(lib, "photo.jpg"))

        # Returns the caption string
        assert result == "A red square."

        # Record now contains the caption
        assert _read_sidecar(lib, "photo.jpg")["caption"] == "A red square."

        # Ollama was called exactly once with the configured model
        assert mock_chat.call_count == 1
        called_args = mock_chat.call_args
        assert called_args[0][0] == TEST_MODEL

        # Image bytes were passed
        assert isinstance(called_args[1]["images"][0], bytes)

    @patch("pixelkasten.tools.ollama.chat")
    def test_returns_cached_caption_without_calling_model(self, mock_chat, tmp_path):
        lib = _make_image_library(
            tmp_path,
            sidecar={"dates": [], "geo": None, "album": None, "caption": "Already captioned."},
        )

        result = _run_caption(os.path.join(lib, "photo.jpg"))

        # Cached caption returned; model not invoked
        assert result == "Already captioned."
        mock_chat.assert_not_called()

    @patch("pixelkasten.tools.ollama.chat")
    def test_force_recaptions_even_when_present(self, mock_chat, tmp_path):
        mock_chat.return_value = "Fresh caption."
        lib = _make_image_library(
            tmp_path,
            sidecar={"dates": [], "geo": None, "album": None, "caption": "Stale."},
        )

        result = _run_caption(os.path.join(lib, "photo.jpg"), force=True)

        # Caption is regenerated and overwrites the cached value
        assert result == "Fresh caption."
        assert _read_sidecar(lib, "photo.jpg")["caption"] == "Fresh caption."

    @patch("pixelkasten.tools.ollama.chat")
    def test_returns_none_and_leaves_sidecar_when_ollama_fails(self, mock_chat, tmp_path, capsys):
        mock_chat.side_effect = RuntimeError("ollama not running")
        lib = _make_image_library(tmp_path)

        result = _run_caption(os.path.join(lib, "photo.jpg"))

        # Failure surfaces via None return and a stderr message
        assert result is None
        assert "failed for" in capsys.readouterr().err

        # Record is untouched: no caption written
        assert "caption" not in _read_sidecar(lib, "photo.jpg")

    @patch("pixelkasten.tools.ollama.chat")
    def test_returns_none_when_model_returns_empty(self, mock_chat, tmp_path, capsys):
        mock_chat.return_value = None
        lib = _make_image_library(tmp_path)

        result = _run_caption(os.path.join(lib, "photo.jpg"))

        # Empty model output is treated as failure
        assert result is None
        assert "empty caption" in capsys.readouterr().err


class TestCaptionVideo:
    @patch("pixelkasten.tools.ollama.chat")
    @patch("pixelkasten.tools.ffmpeg.capture_frames")
    def test_extracts_frames_and_passes_them_to_ollama(self, mock_extract, mock_chat, tmp_path):
        # Build two real JPEG frames so PIL can open them
        frame_buf = []
        for _ in range(2):
            img = Image.new("RGB", (16, 16), color="blue")
            import io as _io

            b = _io.BytesIO()
            img.save(b, format="JPEG")
            frame_buf.append(b.getvalue())
        mock_extract.return_value = frame_buf
        mock_chat.return_value = "A short blue clip."
        lib = _make_library_with_asset(
            tmp_path,
            asset_name="clip.mp4",
            content=b"fake-mp4",
            sidecar={"dates": [], "geo": None, "album": None},
        )

        result = _run_caption(os.path.join(lib, "clip.mp4"), video_frames=2)

        # Caption recorded on the sidecar
        assert result == "A short blue clip."
        assert _read_sidecar(lib, "clip.mp4")["caption"] == "A short blue clip."

        # ffmpeg was asked for exactly the configured frame count
        mock_extract.assert_called_once_with(os.path.join(lib, "clip.mp4"), 2)

        # All extracted frames are forwarded to the VLM
        passed_images = mock_chat.call_args[1]["images"]
        assert len(passed_images) == 2

    @patch("pixelkasten.tools.ffmpeg.capture_frames")
    def test_returns_none_when_frame_extraction_fails(self, mock_extract, tmp_path, capsys):
        mock_extract.side_effect = RuntimeError("ffmpeg crashed")
        lib = _make_library_with_asset(
            tmp_path,
            asset_name="clip.mov",
            content=b"fake",
            sidecar={"dates": [], "geo": None, "album": None},
        )

        result = _run_caption(os.path.join(lib, "clip.mov"))

        # Failure surfaces; sidecar untouched
        assert result is None
        assert "failed for" in capsys.readouterr().err
        assert "caption" not in _read_sidecar(lib, "clip.mov")


class TestCaptionValidation:
    @patch("pixelkasten.tools.ollama.chat")
    def test_raises_when_no_record(self, mock_chat, tmp_path):
        lib = tmp_path / "lib"
        (lib / ".pixelkasten").mkdir(parents=True)
        img = Image.new("RGB", (16, 16))
        img.save(str(lib / "photo.jpg"), format="JPEG")

        # No record -> caption raises rather than silently no-op'ing
        import pytest as _pytest

        with _pytest.raises(RuntimeError, match="No record"):
            _run_caption(str(lib / "photo.jpg"))

    @patch("pixelkasten.tools.ollama.chat")
    def test_returns_none_for_unsupported_extension(self, mock_chat, tmp_path, capsys):
        lib = _make_library_with_asset(
            tmp_path,
            asset_name="raw.dng",
            content=b"raw",
            sidecar={"dates": [], "geo": None, "album": None},
        )

        result = _run_caption(os.path.join(lib, "raw.dng"))

        # Unsupported extension surfaces as caption failure (no crash)
        assert result is None
        assert "failed for" in capsys.readouterr().err
