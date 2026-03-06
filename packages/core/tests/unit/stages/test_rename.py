"""
Tests for the rename stage — ported from packages/core/test/stages/rename.test.js.

All path expectations adapted for no-month format:
  Loose:  YYYY/yyyymmdd-hhmmss.ext
  Album:  YYYY/yyyymmdd-Album Name/yyyymmdd-hhmmss.ext
"""

from pixelkasten.manifest import Dedupe, DedupeResult, ManifestEntry, Metadata, Source, Status
from pixelkasten.stages.rename import rename


def _entry(
    media_path,
    dates,
    source_type="loose",
    source_name=None,
    dedupe=None,
    metadata_status=Status.PROCESSED,
):
    """Helper to create a manifest entry for rename tests."""
    return ManifestEntry(
        media_path=media_path,
        source=Source(type=source_type, name=source_name),
        dedupe=dedupe,
        metadata=Metadata(status=metadata_status, dates=dates) if dates is not None else None,
    )


class TestRenameBasic:
    def test_does_not_process_empty_manifest(self):
        manifest = []
        rename(manifest)
        assert len(manifest) == 0

    def test_skips_entries_marked_for_deletion(self):
        manifest = [
            _entry(
                "/path/to/delete.jpg",
                ["2023-01-15T14:30:45"],
                dedupe=Dedupe(status=Status.PROCESSED, result=DedupeResult.DELETE, hash="abc"),
            ),
            _entry(
                "/path/to/keep.jpg",
                ["2023-01-15T14:30:45"],
                dedupe=Dedupe(status=Status.PROCESSED, result=DedupeResult.KEEP, hash="def"),
            ),
        ]
        rename(manifest)

        # Deleted entry not processed
        assert manifest[0].rename is None

        # Kept entry processed
        assert manifest[1].rename is not None
        assert manifest[1].rename.status == Status.PROCESSED

    def test_generates_correct_path_from_date(self):
        manifest = [_entry("/path/to/image.jpg", ["2024-03-01T13:32:45"])]
        rename(manifest)

        assert manifest[0].rename is not None
        assert manifest[0].rename.target_path == "2024/20240301-133245.jpg"

    def test_handles_different_months(self):
        manifest = [
            _entry("/path/to/jan.jpg", ["2024-01-15T10:00:30"]),
            _entry("/path/to/dec.jpg", ["2024-12-25T18:30:59"]),
        ]
        rename(manifest)

        assert manifest[0].rename is not None
        assert manifest[0].rename.target_path == "2024/20240115-100030.jpg"
        assert manifest[1].rename is not None
        assert manifest[1].rename.target_path == "2024/20241225-183059.jpg"


class TestRenameExtensions:
    def test_preserves_extension_in_lowercase(self):
        manifest = [
            _entry("/path/to/image.JPG", ["2024-03-01T13:32:00"]),
            _entry("/path/to/video.MP4", ["2024-03-01T14:00:00"]),
        ]
        rename(manifest)

        assert manifest[0].rename is not None
        assert manifest[0].rename.target_path is not None
        assert manifest[0].rename.target_path.endswith(".jpg")
        assert manifest[1].rename is not None
        assert manifest[1].rename.target_path is not None
        assert manifest[1].rename.target_path.endswith(".mp4")

    def test_handles_heic_files(self):
        manifest = [_entry("/path/to/image.HEIC", ["2024-03-01T13:32:00"])]
        rename(manifest)

        assert manifest[0].rename is not None
        assert manifest[0].rename.target_path == "2024/20240301-133200.heic"

    def test_handles_mov_files(self):
        manifest = [_entry("/path/to/video.MOV", ["2024-03-01T13:32:00"])]
        rename(manifest)

        assert manifest[0].rename is not None
        assert manifest[0].rename.target_path == "2024/20240301-133200.mov"


class TestRenameCollisions:
    def test_appends_suffix_for_collisions(self):
        manifest = [
            _entry("/path/to/first.jpg", ["2024-03-01T14:02:30"]),
            _entry("/path/to/second.jpg", ["2024-03-01T14:02:30"]),
            _entry("/path/to/third.jpg", ["2024-03-01T14:02:30"]),
        ]
        rename(manifest)

        assert manifest[0].rename is not None
        assert manifest[0].rename.target_path == "2024/20240301-140230.jpg"
        assert manifest[1].rename is not None
        assert manifest[1].rename.target_path == "2024/20240301-140230-1.jpg"
        assert manifest[2].rename is not None
        assert manifest[2].rename.target_path == "2024/20240301-140230-2.jpg"

    def test_different_extensions_do_not_collide(self):
        manifest = [
            _entry("/path/to/image.jpg", ["2024-03-01T14:02:00"]),
            _entry("/path/to/video.mp4", ["2024-03-01T14:02:00"]),
        ]
        rename(manifest)

        assert manifest[0].rename is not None
        assert manifest[0].rename.target_path == "2024/20240301-140200.jpg"
        assert manifest[1].rename is not None
        assert manifest[1].rename.target_path == "2024/20240301-140200.mp4"

    def test_seconds_reduce_collisions(self):
        manifest = [
            _entry("/path/to/first.jpg", ["2024-03-01T14:02:30"]),
            _entry("/path/to/second.jpg", ["2024-03-01T14:02:31"]),
        ]
        rename(manifest)

        assert manifest[0].rename is not None
        assert manifest[0].rename.target_path == "2024/20240301-140230.jpg"
        assert manifest[1].rename is not None
        assert manifest[1].rename.target_path == "2024/20240301-140231.jpg"


class TestRenameDateHandling:
    def test_marks_entries_without_dates_as_error(self):
        manifest = [_entry("/path/to/image.jpg", None)]
        rename(manifest)

        assert manifest[0].rename is not None
        assert manifest[0].rename.status == Status.ERROR

    def test_marks_entries_with_empty_dates_as_error(self):
        manifest = [_entry("/path/to/image.jpg", [])]
        rename(manifest)

        assert manifest[0].rename is not None
        assert manifest[0].rename.status == Status.ERROR

    def test_marks_entries_with_invalid_date_as_error(self):
        manifest = [_entry("/path/to/image.jpg", ["not-a-valid-date"])]
        rename(manifest)

        assert manifest[0].rename is not None
        assert manifest[0].rename.status == Status.ERROR

    def test_uses_first_date_as_primary(self):
        manifest = [_entry("/path/to/image.jpg", ["2024-03-01T13:32:15", "2024-03-01T14:00:00"])]
        rename(manifest)

        assert manifest[0].rename is not None
        assert manifest[0].rename.target_path == "2024/20240301-133215.jpg"

    def test_falls_back_to_next_date_if_first_invalid(self):
        manifest = [
            _entry("/path/to/image.jpg", ["invalid-date", "also-invalid", "2024-05-10T09:15:30"])
        ]
        rename(manifest)

        assert manifest[0].rename is not None
        assert manifest[0].rename.target_path == "2024/20240510-091530.jpg"

    def test_pads_single_digit_values(self):
        manifest = [_entry("/path/to/image.jpg", ["2024-01-05T09:05:07"])]
        rename(manifest)

        assert manifest[0].rename is not None
        assert manifest[0].rename.target_path == "2024/20240105-090507.jpg"


class TestRenameDedupe:
    def test_processes_entries_without_dedupe(self):
        manifest = [_entry("/path/to/image.jpg", ["2024-03-01T13:32:00"])]
        rename(manifest)

        assert manifest[0].rename is not None
        assert manifest[0].rename.status == Status.PROCESSED

    def test_processes_entries_with_pending_dedupe(self):
        manifest = [
            _entry(
                "/path/to/image.jpg",
                ["2024-03-01T13:32:00"],
                dedupe=Dedupe(status=Status.PENDING),
            ),
        ]
        rename(manifest)

        assert manifest[0].rename is not None
        assert manifest[0].rename.status == Status.PROCESSED


class TestRenameAlbums:
    def test_places_album_photos_in_album_subfolder(self):
        manifest = [
            _entry(
                "/path/to/image.jpg",
                ["2024-04-15T10:30:00"],
                source_type="album",
                source_name="Trip to Japan",
            ),
        ]
        rename(manifest)

        assert manifest[0].rename is not None
        assert manifest[0].rename.target_path == "2024/20240415-Trip to Japan/20240415-103000.jpg"

    def test_uses_earliest_album_date_for_folder(self):
        manifest = [
            _entry(
                "/path/to/later.jpg",
                ["2024-03-20T15:00:00"],
                source_type="album",
                source_name="Vacation",
            ),
            _entry(
                "/path/to/earlier.jpg",
                ["2024-03-18T09:00:00"],
                source_type="album",
                source_name="Vacation",
            ),
        ]
        rename(manifest)

        # Both use earliest date (March 18) for folder
        assert manifest[0].rename is not None
        assert manifest[0].rename.target_path == "2024/20240318-Vacation/20240320-150000.jpg"
        assert manifest[1].rename is not None
        assert manifest[1].rename.target_path == "2024/20240318-Vacation/20240318-090000.jpg"

    def test_cross_month_album_uses_earliest_month(self):
        manifest = [
            _entry(
                "/path/to/jan.jpg",
                ["2024-01-02T12:00:00"],
                source_type="album",
                source_name="New Year Trip",
            ),
            _entry(
                "/path/to/dec.jpg",
                ["2023-12-31T23:00:00"],
                source_type="album",
                source_name="New Year Trip",
            ),
        ]
        rename(manifest)

        # Both go to December (earliest)
        assert manifest[0].rename is not None
        assert manifest[0].rename.target_path == "2023/20231231-New Year Trip/20240102-120000.jpg"
        assert manifest[1].rename is not None
        assert manifest[1].rename.target_path == "2023/20231231-New Year Trip/20231231-230000.jpg"

    def test_handles_mix_of_album_and_loose(self):
        manifest = [
            _entry(
                "/path/to/album-photo.jpg",
                ["2024-05-10T14:00:00"],
                source_type="album",
                source_name="Birthday",
            ),
            _entry("/path/to/loose-photo.jpg", ["2024-05-10T14:30:00"]),
        ]
        rename(manifest)

        assert manifest[0].rename is not None
        assert manifest[0].rename.target_path == "2024/20240510-Birthday/20240510-140000.jpg"
        assert manifest[1].rename is not None
        assert manifest[1].rename.target_path == "2024/20240510-143000.jpg"

    def test_handles_collisions_within_album(self):
        manifest = [
            _entry(
                "/path/to/first.jpg",
                ["2024-06-01T20:00:00"],
                source_type="album",
                source_name="Party",
            ),
            _entry(
                "/path/to/second.jpg",
                ["2024-06-01T20:00:00"],
                source_type="album",
                source_name="Party",
            ),
        ]
        rename(manifest)

        assert manifest[0].rename is not None
        assert manifest[0].rename.target_path == "2024/20240601-Party/20240601-200000.jpg"
        assert manifest[1].rename is not None
        assert manifest[1].rename.target_path == "2024/20240601-Party/20240601-200000-1.jpg"
