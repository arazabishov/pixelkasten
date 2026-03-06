from pathlib import Path

import pytest

from pixelkasten.handlers import is_image, is_video
from pixelkasten.stages.scan import scan


class TestIsImage:
    def test_recognizes_supported_extensions(self):
        assert is_image(Path("photo.jpg")) is True
        assert is_image(Path("photo.jpeg")) is True
        assert is_image(Path("photo.heic")) is True
        assert is_image(Path("photo.png")) is True

    def test_rejects_non_image_extensions(self):
        assert is_image(Path("video.mp4")) is False
        assert is_image(Path("readme.txt")) is False
        assert is_image(Path("data.json")) is False

    def test_case_insensitive(self):
        assert is_image(Path("PHOTO.JPG")) is True
        assert is_image(Path("Photo.Jpeg")) is True


class TestIsVideo:
    def test_recognizes_video_extensions(self):
        assert is_video(Path("clip.mp4")) is True
        assert is_video(Path("clip.mov")) is True

    def test_rejects_non_video(self):
        assert is_video(Path("photo.jpg")) is False


class TestScan:
    def test_categorizes_media_files_by_known_extensions(self, tmp_path):
        (tmp_path / "sub").mkdir()
        (tmp_path / "photo.jpg").touch()
        (tmp_path / "image.jpeg").touch()
        (tmp_path / "image.heic").touch()
        (tmp_path / "screenshot.png").touch()
        (tmp_path / "clip.mp4").touch()
        (tmp_path / "video.mov").touch()
        (tmp_path / "sub" / "motion.mp").touch()

        result = scan(str(tmp_path))

        # All supported media files are categorized
        assert len(result["files_media"]) == 7

        # No files leaked into other buckets
        assert len(result["files_metadata"]) == 0
        assert len(result["files_metadata_albums"]) == 0
        assert len(result["files_other_ignored"]) == 0

    def test_categorizes_unsupported_media_files_as_media(self, tmp_path):
        (tmp_path / "old-video.avi").touch()
        (tmp_path / "movie.mkv").touch()
        (tmp_path / "clip.wmv").touch()
        (tmp_path / "stream.flv").touch()

        result = scan(str(tmp_path))

        # Unsupported-but-known media files are categorized as media
        assert len(result["files_media"]) == 4

    def test_categorizes_json_files_as_metadata(self, tmp_path):
        (tmp_path / "photo.jpg.supplemental-metadata.json").touch()
        (tmp_path / "photo.jpg.suppl.json").touch()
        (tmp_path / "photo.jpeg..json").touch()

        result = scan(str(tmp_path))

        # All JSON files are categorized as metadata
        assert len(result["files_metadata"]) == 3

        # Not miscategorized as media
        assert len(result["files_media"]) == 0

    def test_categorizes_metadata_json_as_album_metadata(self, tmp_path):
        (tmp_path / "Vacation").mkdir()
        (tmp_path / "Japan").mkdir()
        (tmp_path / "Vacation" / "metadata.json").touch()
        (tmp_path / "Japan" / "metadata.json").touch()
        (tmp_path / "other.json").touch()

        result = scan(str(tmp_path))

        # metadata.json files are categorized as album metadata
        assert len(result["files_metadata_albums"]) == 2

        # Other JSON files are categorized as regular metadata
        assert len(result["files_metadata"]) == 1

    def test_categorizes_unknown_extensions_as_other(self, tmp_path):
        (tmp_path / "readme.txt").touch()
        (tmp_path / "notes.md").touch()
        (tmp_path / "archive.zip").touch()

        result = scan(str(tmp_path))

        # Unknown extensions go to the other/ignored bucket
        assert len(result["files_other_ignored"]) == 3

        # Not miscategorized
        assert len(result["files_media"]) == 0
        assert len(result["files_metadata"]) == 0

    def test_builds_full_paths_from_nested_directories(self, tmp_path):
        (tmp_path / "Photos from 2024").mkdir()
        (tmp_path / "Vacation").mkdir()
        (tmp_path / "Photos from 2024" / "photo.jpg").touch()
        (tmp_path / "Vacation" / "metadata.json").touch()

        result = scan(str(tmp_path))

        # Full paths are constructed correctly
        assert result["files_media"] == [str(tmp_path / "Photos from 2024" / "photo.jpg")]
        assert result["files_metadata_albums"] == [str(tmp_path / "Vacation" / "metadata.json")]

    def test_handles_case_insensitive_extensions(self, tmp_path):
        (tmp_path / "PHOTO.JPG").touch()
        (tmp_path / "image.HEIC").touch()
        (tmp_path / "video.MP4").touch()

        result = scan(str(tmp_path))

        # Uppercase extensions are matched case-insensitively
        assert len(result["files_media"]) == 3

    def test_maintains_correct_total_count_across_all_buckets(self, tmp_path):
        (tmp_path / "Album").mkdir()
        (tmp_path / "photo.jpg").touch()
        (tmp_path / "photo.jpg.json").touch()
        (tmp_path / "Album" / "metadata.json").touch()
        (tmp_path / "readme.txt").touch()

        result = scan(str(tmp_path))

        # Total counts only files
        assert result["files_total"] == 4

        # Invariant: all buckets sum to total
        bucket_sum = (
            len(result["files_media"])
            + len(result["files_metadata"])
            + len(result["files_metadata_albums"])
            + len(result["files_other_ignored"])
        )
        assert bucket_sum == result["files_total"]

    def test_raises_for_nonexistent_directory(self):
        with pytest.raises(FileNotFoundError):
            scan("/nonexistent/directory")
