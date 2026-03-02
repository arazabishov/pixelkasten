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
    def test_finds_images_recursively(self, tmp_path):
        # Create nested structure.
        (tmp_path / "sub").mkdir()
        (tmp_path / "photo1.jpg").touch()
        (tmp_path / "sub" / "photo2.png").touch()
        (tmp_path / "readme.txt").touch()

        result = scan(tmp_path)

        filenames = [p.name for p in result]
        assert "photo1.jpg" in filenames
        assert "photo2.png" in filenames
        assert "readme.txt" not in filenames

    def test_raises_for_nonexistent_directory(self):
        with pytest.raises(FileNotFoundError):
            scan(Path("/nonexistent/directory"))
