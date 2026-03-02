"""
Tests for the rename stage — ported from packages/core/test/stages/rename.test.js.

All path expectations adapted for no-month format:
  Loose:  YYYY/yyyymmdd-hhmmss.ext
  Album:  YYYY/yyyymmdd - Album Name/yyyymmdd-hhmmss.ext
"""

from pixelkasten.stages.rename import rename


class TestRenameBasic:
    def test_does_not_process_empty_manifest(self):
        manifest = []
        rename(manifest)
        assert len(manifest) == 0

    def test_skips_entries_marked_for_deletion(self):
        manifest = [
            {
                "mediaPath": "/path/to/delete.jpg",
                "dedupe": {"status": "delete"},
                "metadata": {"dates": ["2023-01-15T14:30:45"]},
            },
            {
                "mediaPath": "/path/to/keep.jpg",
                "dedupe": {"status": "keep"},
                "metadata": {"dates": ["2023-01-15T14:30:45"]},
            },
        ]
        rename(manifest)

        # Deleted entry not processed
        assert "rename" not in manifest[0]

        # Kept entry processed
        assert manifest[1]["rename"]["status"] == "processed"

    def test_generates_correct_path_from_date(self):
        manifest = [
            {
                "mediaPath": "/path/to/image.jpg",
                "metadata": {"dates": ["2024-03-01T13:32:45"]},
            },
        ]
        rename(manifest)

        assert manifest[0]["rename"]["targetPath"] == "2024/20240301-133245.jpg"

    def test_handles_different_months(self):
        manifest = [
            {
                "mediaPath": "/path/to/jan.jpg",
                "metadata": {"dates": ["2024-01-15T10:00:30"]},
            },
            {
                "mediaPath": "/path/to/dec.jpg",
                "metadata": {"dates": ["2024-12-25T18:30:59"]},
            },
        ]
        rename(manifest)

        assert manifest[0]["rename"]["targetPath"] == "2024/20240115-100030.jpg"
        assert manifest[1]["rename"]["targetPath"] == "2024/20241225-183059.jpg"


class TestRenameExtensions:
    def test_preserves_extension_in_lowercase(self):
        manifest = [
            {
                "mediaPath": "/path/to/image.JPG",
                "metadata": {"dates": ["2024-03-01T13:32:00"]},
            },
            {
                "mediaPath": "/path/to/video.MP4",
                "metadata": {"dates": ["2024-03-01T14:00:00"]},
            },
        ]
        rename(manifest)

        assert manifest[0]["rename"]["targetPath"].endswith(".jpg")
        assert manifest[1]["rename"]["targetPath"].endswith(".mp4")

    def test_handles_heic_files(self):
        manifest = [
            {
                "mediaPath": "/path/to/image.HEIC",
                "metadata": {"dates": ["2024-03-01T13:32:00"]},
            },
        ]
        rename(manifest)

        assert manifest[0]["rename"]["targetPath"] == "2024/20240301-133200.heic"

    def test_handles_mov_files(self):
        manifest = [
            {
                "mediaPath": "/path/to/video.MOV",
                "metadata": {"dates": ["2024-03-01T13:32:00"]},
            },
        ]
        rename(manifest)

        assert manifest[0]["rename"]["targetPath"] == "2024/20240301-133200.mov"


class TestRenameCollisions:
    def test_appends_suffix_for_collisions(self):
        manifest = [
            {
                "mediaPath": "/path/to/first.jpg",
                "metadata": {"dates": ["2024-03-01T14:02:30"]},
            },
            {
                "mediaPath": "/path/to/second.jpg",
                "metadata": {"dates": ["2024-03-01T14:02:30"]},
            },
            {
                "mediaPath": "/path/to/third.jpg",
                "metadata": {"dates": ["2024-03-01T14:02:30"]},
            },
        ]
        rename(manifest)

        assert manifest[0]["rename"]["targetPath"] == "2024/20240301-140230.jpg"
        assert manifest[1]["rename"]["targetPath"] == "2024/20240301-140230-1.jpg"
        assert manifest[2]["rename"]["targetPath"] == "2024/20240301-140230-2.jpg"

    def test_different_extensions_do_not_collide(self):
        manifest = [
            {
                "mediaPath": "/path/to/image.jpg",
                "metadata": {"dates": ["2024-03-01T14:02:00"]},
            },
            {
                "mediaPath": "/path/to/video.mp4",
                "metadata": {"dates": ["2024-03-01T14:02:00"]},
            },
        ]
        rename(manifest)

        assert manifest[0]["rename"]["targetPath"] == "2024/20240301-140200.jpg"
        assert manifest[1]["rename"]["targetPath"] == "2024/20240301-140200.mp4"

    def test_seconds_reduce_collisions(self):
        manifest = [
            {
                "mediaPath": "/path/to/first.jpg",
                "metadata": {"dates": ["2024-03-01T14:02:30"]},
            },
            {
                "mediaPath": "/path/to/second.jpg",
                "metadata": {"dates": ["2024-03-01T14:02:31"]},
            },
        ]
        rename(manifest)

        assert manifest[0]["rename"]["targetPath"] == "2024/20240301-140230.jpg"
        assert manifest[1]["rename"]["targetPath"] == "2024/20240301-140231.jpg"


class TestRenameDateHandling:
    def test_marks_entries_without_dates_as_error(self):
        manifest = [
            {"mediaPath": "/path/to/image.jpg", "metadata": {}},
        ]
        rename(manifest)

        assert manifest[0]["rename"]["status"] == "error"

    def test_marks_entries_with_empty_dates_as_error(self):
        manifest = [
            {"mediaPath": "/path/to/image.jpg", "metadata": {"dates": []}},
        ]
        rename(manifest)

        assert manifest[0]["rename"]["status"] == "error"

    def test_marks_entries_with_invalid_date_as_error(self):
        manifest = [
            {"mediaPath": "/path/to/image.jpg", "metadata": {"dates": ["not-a-valid-date"]}},
        ]
        rename(manifest)

        assert manifest[0]["rename"]["status"] == "error"

    def test_uses_first_date_as_primary(self):
        manifest = [
            {
                "mediaPath": "/path/to/image.jpg",
                "metadata": {
                    "dates": ["2024-03-01T13:32:15", "2024-03-01T14:00:00"],
                },
            },
        ]
        rename(manifest)

        assert manifest[0]["rename"]["targetPath"] == "2024/20240301-133215.jpg"

    def test_falls_back_to_next_date_if_first_invalid(self):
        manifest = [
            {
                "mediaPath": "/path/to/image.jpg",
                "metadata": {
                    "dates": ["invalid-date", "also-invalid", "2024-05-10T09:15:30"],
                },
            },
        ]
        rename(manifest)

        assert manifest[0]["rename"]["targetPath"] == "2024/20240510-091530.jpg"

    def test_pads_single_digit_values(self):
        manifest = [
            {
                "mediaPath": "/path/to/image.jpg",
                "metadata": {"dates": ["2024-01-05T09:05:07"]},
            },
        ]
        rename(manifest)

        assert manifest[0]["rename"]["targetPath"] == "2024/20240105-090507.jpg"


class TestRenameDedupe:
    def test_processes_entries_without_dedupe(self):
        manifest = [
            {
                "mediaPath": "/path/to/image.jpg",
                "metadata": {"dates": ["2024-03-01T13:32:00"]},
            },
        ]
        rename(manifest)

        assert manifest[0]["rename"]["status"] == "processed"

    def test_processes_entries_with_pending_dedupe(self):
        manifest = [
            {
                "mediaPath": "/path/to/image.jpg",
                "dedupe": {"status": "pending"},
                "metadata": {"dates": ["2024-03-01T13:32:00"]},
            },
        ]
        rename(manifest)

        assert manifest[0]["rename"]["status"] == "processed"


class TestRenameAlbums:
    def test_places_album_photos_in_album_subfolder(self):
        manifest = [
            {
                "mediaPath": "/path/to/image.jpg",
                "source": {"type": "album", "name": "Trip to Japan"},
                "metadata": {"dates": ["2024-04-15T10:30:00"]},
            },
        ]
        rename(manifest)

        assert (
            manifest[0]["rename"]["targetPath"]
            == "2024/20240415 - Trip to Japan/20240415-103000.jpg"
        )

    def test_uses_earliest_album_date_for_folder(self):
        manifest = [
            {
                "mediaPath": "/path/to/later.jpg",
                "source": {"type": "album", "name": "Vacation"},
                "metadata": {"dates": ["2024-03-20T15:00:00"]},
            },
            {
                "mediaPath": "/path/to/earlier.jpg",
                "source": {"type": "album", "name": "Vacation"},
                "metadata": {"dates": ["2024-03-18T09:00:00"]},
            },
        ]
        rename(manifest)

        # Both use earliest date (March 18) for folder
        assert (
            manifest[0]["rename"]["targetPath"]
            == "2024/20240318 - Vacation/20240320-150000.jpg"
        )
        assert (
            manifest[1]["rename"]["targetPath"]
            == "2024/20240318 - Vacation/20240318-090000.jpg"
        )

    def test_cross_month_album_uses_earliest_month(self):
        manifest = [
            {
                "mediaPath": "/path/to/jan.jpg",
                "source": {"type": "album", "name": "New Year Trip"},
                "metadata": {"dates": ["2024-01-02T12:00:00"]},
            },
            {
                "mediaPath": "/path/to/dec.jpg",
                "source": {"type": "album", "name": "New Year Trip"},
                "metadata": {"dates": ["2023-12-31T23:00:00"]},
            },
        ]
        rename(manifest)

        # Both go to December (earliest)
        assert (
            manifest[0]["rename"]["targetPath"]
            == "2023/20231231 - New Year Trip/20240102-120000.jpg"
        )
        assert (
            manifest[1]["rename"]["targetPath"]
            == "2023/20231231 - New Year Trip/20231231-230000.jpg"
        )

    def test_handles_mix_of_album_and_loose(self):
        manifest = [
            {
                "mediaPath": "/path/to/album-photo.jpg",
                "source": {"type": "album", "name": "Birthday"},
                "metadata": {"dates": ["2024-05-10T14:00:00"]},
            },
            {
                "mediaPath": "/path/to/loose-photo.jpg",
                "source": {"type": "loose"},
                "metadata": {"dates": ["2024-05-10T14:30:00"]},
            },
        ]
        rename(manifest)

        assert (
            manifest[0]["rename"]["targetPath"]
            == "2024/20240510 - Birthday/20240510-140000.jpg"
        )
        assert manifest[1]["rename"]["targetPath"] == "2024/20240510-143000.jpg"

    def test_handles_collisions_within_album(self):
        manifest = [
            {
                "mediaPath": "/path/to/first.jpg",
                "source": {"type": "album", "name": "Party"},
                "metadata": {"dates": ["2024-06-01T20:00:00"]},
            },
            {
                "mediaPath": "/path/to/second.jpg",
                "source": {"type": "album", "name": "Party"},
                "metadata": {"dates": ["2024-06-01T20:00:00"]},
            },
        ]
        rename(manifest)

        assert (
            manifest[0]["rename"]["targetPath"]
            == "2024/20240601 - Party/20240601-200000.jpg"
        )
        assert (
            manifest[1]["rename"]["targetPath"]
            == "2024/20240601 - Party/20240601-200000-1.jpg"
        )
