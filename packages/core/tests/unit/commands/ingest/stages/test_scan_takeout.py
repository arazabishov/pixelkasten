import os

import pytest

from pixelkasten.commands.ingest.stages.scan import scan


class TestScanTakeout:
    def test_categorizes_media_files_by_known_extensions(self, tmp_path):
        # Create supported media files with various extensions.
        for name in [
            "photo.jpg",
            "image.heic",
            "screenshot.png",
            "clip.mp4",
            "video.mov",
            "audio.mp",
            "pic.jpeg",
        ]:
            (tmp_path / name).touch()

        result = scan(str(tmp_path))

        # All 7 files should be categorized as media
        assert len(result["files_media"]) == 7

        # No files should leak into other buckets
        assert len(result["files_metadata"]) == 0
        assert len(result["files_metadata_albums"]) == 0
        assert len(result["files_other_ignored"]) == 0

    def test_categorizes_unsupported_media_as_media(self, tmp_path):
        # Create unsupported-but-known media files.
        for name in ["video.avi", "movie.mkv", "clip.wmv", "stream.flv"]:
            (tmp_path / name).touch()

        result = scan(str(tmp_path))

        # All 4 unsupported media files should still be categorized as media
        assert len(result["files_media"]) == 4

    def test_categorizes_json_files_as_metadata(self, tmp_path):
        # Create JSON sidecar files with various naming patterns.
        for name in [
            "photo.jpg.supplemental-metadata.json",
            "photo.jpg.suppl.json",
            "photo.jpg.json",
        ]:
            (tmp_path / name).touch()

        result = scan(str(tmp_path))

        # All 3 JSON files should be categorized as metadata
        assert len(result["files_metadata"]) == 3

        # They should not be miscategorized as media
        assert len(result["files_media"]) == 0

    def test_categorizes_metadata_json_as_album_metadata(self, tmp_path):
        # Create metadata.json in two subdirectories and one other JSON file.
        (tmp_path / "Vacation").mkdir()
        (tmp_path / "Japan").mkdir()
        (tmp_path / "Vacation" / "metadata.json").touch()
        (tmp_path / "Japan" / "metadata.json").touch()
        (tmp_path / "other.json").touch()

        result = scan(str(tmp_path))

        # Two metadata.json files should be album metadata
        assert len(result["files_metadata_albums"]) == 2

        # The other JSON file should be regular metadata
        assert len(result["files_metadata"]) == 1

    def test_categorizes_unknown_extensions_as_other_ignored(self, tmp_path):
        # Create files with unrecognized extensions.
        for name in ["readme.txt", "notes.md", "archive.zip"]:
            (tmp_path / name).touch()

        result = scan(str(tmp_path))

        # All 3 files should go to other/ignored
        assert len(result["files_other_ignored"]) == 3

        # They should not be miscategorized
        assert len(result["files_media"]) == 0
        assert len(result["files_metadata"]) == 0

    def test_skips_directories_counts_only_files(self, tmp_path):
        # Create a subdirectory and a single file.
        (tmp_path / "subdir").mkdir()
        (tmp_path / "photo.jpg").touch()

        result = scan(str(tmp_path))

        # Total should count only files, not directories
        assert result["files_total"] == 1

        # The single file should be in media
        assert len(result["files_media"]) == 1

    def test_builds_full_paths_from_directory_structure(self, tmp_path):
        # Create a nested file under a directory with spaces.
        album_dir = tmp_path / "Photos from 2024"
        album_dir.mkdir()
        (album_dir / "photo.jpg").touch()

        result = scan(str(tmp_path))

        # The full path should include the directory name
        assert len(result["files_media"]) == 1
        expected = os.path.join(str(album_dir), "photo.jpg")
        assert result["files_media"][0] == expected

    def test_handles_case_insensitive_media_extensions(self, tmp_path):
        # Create files with uppercase extensions.
        for name in ["photo.JPG", "image.HEIC", "clip.MP4"]:
            (tmp_path / name).touch()

        result = scan(str(tmp_path))

        # All 3 uppercase-extension files should be categorized as media
        assert len(result["files_media"]) == 3

    def test_maintains_correct_total_count(self, tmp_path):
        # Create a mix of file types plus a directory.
        (tmp_path / "Album").mkdir()
        (tmp_path / "photo.jpg").touch()
        (tmp_path / "photo.jpg.json").touch()
        (tmp_path / "Album" / "metadata.json").touch()
        (tmp_path / "readme.txt").touch()

        result = scan(str(tmp_path))

        # Total should count only files (not the directory)
        assert result["files_total"] == 4

        # Invariant: all bucket lengths must sum to files_total
        bucket_sum = (
            len(result["files_media"])
            + len(result["files_metadata"])
            + len(result["files_metadata_albums"])
            + len(result["files_other_ignored"])
        )
        assert bucket_sum == result["files_total"]

    def test_raises_for_nonexistent_directory(self):
        # Attempting to scan a path that does not exist should raise
        with pytest.raises(FileNotFoundError):
            scan("/nonexistent/path")
