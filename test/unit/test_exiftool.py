"""
Tests for the exiftool subprocess wrapper module.

Unit tests mock subprocess.run. Integration tests require exiftool installed.
"""

import shutil
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pixelkasten.exiftool import read_metadata, write_metadata


# ---------------------------------------------------------------------------
# write_metadata — unit tests
# ---------------------------------------------------------------------------


class TestWriteMetadata:
    @patch("pixelkasten.exiftool.subprocess.run")
    def test_returns_without_subprocess_for_empty_tags(self, mock_run):
        write_metadata("/some/file.jpg", [])

        # subprocess.run should never be called
        mock_run.assert_not_called()

    @patch("pixelkasten.exiftool.subprocess.run")
    def test_constructs_correct_exiftool_args(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        write_metadata(
            "/some/file.jpg",
            ["SubSecDateTimeOriginal=2023:05:20 14:30:00+00:00"],
        )

        call_args = mock_run.call_args[0][0]

        # Verify key args
        assert "exiftool" == call_args[0]
        assert "-api" in call_args
        assert "largefilesupport=1" in call_args
        assert "-overwrite_original" in call_args
        assert "-SubSecDateTimeOriginal=2023:05:20 14:30:00+00:00" in call_args
        assert call_args[-1] == "/some/file.jpg"

    @patch("pixelkasten.exiftool.subprocess.run")
    def test_raises_on_nonzero_exit(self, mock_run):
        mock_run.return_value = MagicMock(returncode=2, stderr="some error")

        with pytest.raises(RuntimeError, match="Failed to write metadata"):
            write_metadata("/some/file.jpg", ["Tag=Value"])

    @patch("pixelkasten.exiftool.subprocess.run")
    def test_handles_multiple_tags(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        write_metadata("/some/file.jpg", ["Tag1=Value1", "Tag2=Value2"])

        call_args = mock_run.call_args[0][0]

        assert "-Tag1=Value1" in call_args
        assert "-Tag2=Value2" in call_args


# ---------------------------------------------------------------------------
# read_metadata — unit tests
# ---------------------------------------------------------------------------


class TestReadMetadata:
    def test_returns_empty_dict_for_empty_paths(self):
        result = read_metadata([])

        assert result == {}

    @patch("pixelkasten.exiftool.subprocess.run")
    def test_includes_tag_args_when_provided(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='[{"SourceFile": "/test.jpg"}]',
            stderr="",
        )

        read_metadata([Path("/test.jpg")], ["EXIF:DateTimeOriginal"])

        call_args = mock_run.call_args[0][0]

        assert "-EXIF:DateTimeOriginal" in call_args


# ---------------------------------------------------------------------------
# write_metadata — integration test (requires exiftool)
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "media"


class TestWriteMetadataIntegration:
    def test_writes_timestamp_to_fixture_copy(self, tmp_path):
        # Copy fixture to avoid modifying shared test data
        src = FIXTURES_DIR / "no-metadata.jpg"
        if not src.exists():
            pytest.skip("Fixture not found")

        dest = tmp_path / "test.jpg"
        shutil.copy2(src, dest)

        # Write a timestamp
        write_metadata(dest, ["SubSecDateTimeOriginal=2024:01:01 12:00:00+00:00"])

        # Read it back to verify
        result = subprocess.run(
            ["exiftool", "-json", "-n", "-G", "-EXIF:DateTimeOriginal", str(dest)],
            capture_output=True,
            text=True,
        )

        import json

        entries = json.loads(result.stdout)
        assert len(entries) == 1

        # Verify the timestamp was written
        assert "EXIF:DateTimeOriginal" in entries[0]
