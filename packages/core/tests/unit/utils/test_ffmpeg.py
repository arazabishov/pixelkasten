"""Tests for tools/ffmpeg.py — capture_frames orchestration."""

from unittest.mock import patch, MagicMock

import pytest

from pixelkasten.utils.ffmpeg import capture_frames


def _probe_result(duration: float):
    """Build a ffprobe subprocess result with the given duration on stdout."""
    return MagicMock(returncode=0, stdout=f"{duration}\n", stderr="")


def _ffmpeg_result(payload: bytes):
    """Build an ffmpeg subprocess result returning a frame payload (JPEG-prefixed)."""
    return MagicMock(returncode=0, stdout=b"\xff\xd8\xff" + payload, stderr=b"")


class TestCaptureFrames:
    def test_returns_one_bytes_per_requested_frame(self):
        with patch("pixelkasten.utils.ffmpeg.subprocess.run") as mock_run:
            # First call is ffprobe (duration), then n ffmpeg calls.
            mock_run.side_effect = [
                _probe_result(10.0),
                _ffmpeg_result(b"frame-0"),
                _ffmpeg_result(b"frame-1"),
                _ffmpeg_result(b"frame-2"),
            ]

            frames = capture_frames("/tmp/video.mov", 3)

            # One JPEG-bytes payload per requested frame (with FF D8 FF prefix)
            assert frames == [
                b"\xff\xd8\xff" + b"frame-0",
                b"\xff\xd8\xff" + b"frame-1",
                b"\xff\xd8\xff" + b"frame-2",
            ]

    def test_samples_timestamps_at_segment_midpoints(self):
        with patch("pixelkasten.utils.ffmpeg.subprocess.run") as mock_run:
            mock_run.side_effect = [
                _probe_result(10.0),
                _ffmpeg_result(b"a"),
                _ffmpeg_result(b"b"),
            ]

            capture_frames("/tmp/video.mov", 2)

            # ffmpeg calls (positions 1, 2) include -ss with midpoint timestamps.
            # 10s duration, 2 frames -> midpoints at 2.5 and 7.5.
            ffmpeg_calls = mock_run.call_args_list[1:]
            timestamps = [call[0][0][call[0][0].index("-ss") + 1] for call in ffmpeg_calls]
            assert timestamps == ["2.500", "7.500"]

    def test_raises_when_ffprobe_fails(self):
        with patch("pixelkasten.utils.ffmpeg.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="boom")

            with pytest.raises(RuntimeError, match="ffprobe failed"):
                capture_frames("/tmp/x.mov", 3)

    def test_raises_when_duration_is_zero(self):
        with patch("pixelkasten.utils.ffmpeg.subprocess.run") as mock_run:
            mock_run.return_value = _probe_result(0.0)

            with pytest.raises(RuntimeError, match="Could not determine duration"):
                capture_frames("/tmp/x.mov", 3)

    def test_raises_when_ffmpeg_capture_fails(self):
        with patch("pixelkasten.utils.ffmpeg.subprocess.run") as mock_run:
            mock_run.side_effect = [
                _probe_result(5.0),
                MagicMock(returncode=1, stdout=b"", stderr=b"corrupt video"),
            ]

            with pytest.raises(RuntimeError, match="ffmpeg frame extraction failed"):
                capture_frames("/tmp/x.mov", 1)

    def test_rejects_zero_or_negative_frame_count(self):
        with pytest.raises(ValueError):
            capture_frames("/tmp/x.mov", 0)

    def test_raises_when_ffmpeg_returns_empty_payload(self):
        # Some MP4 variants make ffmpeg exit 0 but produce no decodable frame.
        with patch("pixelkasten.utils.ffmpeg.subprocess.run") as mock_run:
            mock_run.side_effect = [
                _probe_result(5.0),
                MagicMock(returncode=0, stdout=b"", stderr=b""),
            ]

            with pytest.raises(RuntimeError, match="no decodable frame"):
                capture_frames("/tmp/x.mov", 1)

    def test_raises_when_ffmpeg_returns_non_jpeg_bytes(self):
        # Defensive: payload that doesn't start with FF D8 FF is rejected.
        with patch("pixelkasten.utils.ffmpeg.subprocess.run") as mock_run:
            mock_run.side_effect = [
                _probe_result(5.0),
                MagicMock(returncode=0, stdout=b"not-a-jpeg", stderr=b""),
            ]

            with pytest.raises(RuntimeError, match="no decodable frame"):
                capture_frames("/tmp/x.mov", 1)
