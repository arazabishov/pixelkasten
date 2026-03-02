from pathlib import Path

import pytest

from pixelkasten.stages.scan import scan, is_image, is_video


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
    def test_finds_media_files_recursively(self, tmp_path):
        (tmp_path / "sub").mkdir()
        (tmp_path / "photo1.jpg").touch()
        (tmp_path / "sub" / "photo2.png").touch()
        (tmp_path / "readme.txt").touch()

        result = scan(str(tmp_path))

        media_names = [Path(p).name for p in result["files_media"]]
        assert "photo1.jpg" in media_names
        assert "photo2.png" in media_names

    def test_categorizes_non_media_as_other(self, tmp_path):
        (tmp_path / "readme.txt").touch()
        (tmp_path / "photo.jpg").touch()

        result = scan(str(tmp_path))

        other_names = [Path(p).name for p in result["files_other_ignored"]]
        assert "readme.txt" in other_names

    def test_raises_for_nonexistent_directory(self):
        with pytest.raises(FileNotFoundError):
            scan("/nonexistent/directory")
