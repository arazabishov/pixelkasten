"""
Tests for the reconcile stage -- ported from packages/core/test/stages/reconcile.test.js.

Mocks read_metadata (I/O) and read_sidecar (I/O). Uses real handlers
(pure, fast, already tested) so we verify real tag formatting.
"""

from unittest.mock import patch

from helpers import make_options
from pixelkasten.stages.reconcile import reconcile


def _entry(media_path, json_path=None, dedupe_status="keep"):
    """Helper to create a manifest entry."""
    e = {
        "mediaPath": media_path,
        "dedupe": {"hash": "abc", "status": dedupe_status},
    }
    if json_path:
        e["json"] = {"path": json_path, "confidence": 3}
    return e


class TestReconcile:
    @patch("pixelkasten.stages.reconcile.read_metadata")
    @patch("pixelkasten.stages.reconcile.read_sidecar")
    def test_does_not_perform_disk_ops_when_manifest_is_empty(self, mock_sidecar, mock_metadata):
        manifest = []
        reconcile(manifest, make_options())

        # Verify no entries were added
        assert len(manifest) == 0

        # Verify no metadata was read from disk
        mock_metadata.assert_not_called()

        # Verify no sidecar was read from disk
        mock_sidecar.assert_not_called()

    @patch("pixelkasten.stages.reconcile.read_metadata")
    @patch("pixelkasten.stages.reconcile.read_sidecar")
    def test_skips_entries_marked_for_deletion(self, mock_sidecar, mock_metadata):
        mock_sidecar.return_value = None
        mock_metadata.return_value = {
            "/tmp/keep.jpg": {"EXIF:DateTimeOriginal": "2023:01:01 12:00:00"},
        }

        manifest = [
            _entry("/tmp/delete.jpg", dedupe_status="delete"),
            _entry("/tmp/keep.jpg", "/tmp/keep.json"),
        ]
        reconcile(manifest, make_options())

        # Only 1 batch call (just the keeper)
        assert mock_metadata.call_count == 1

        # The deleted entry should NOT have metadata
        assert "metadata" not in manifest[0]

        # read_metadata should only receive the keeper path
        call_paths = mock_metadata.call_args[0][0]
        assert call_paths == ["/tmp/keep.jpg"]

    @patch("pixelkasten.stages.reconcile.read_metadata")
    @patch("pixelkasten.stages.reconcile.read_sidecar")
    def test_does_not_queue_writes_when_no_sidecar(self, mock_sidecar, mock_metadata):
        mock_sidecar.return_value = None
        mock_metadata.return_value = {
            "/tmp/image.jpg": {"EXIF:DateTimeOriginal": "2023:01:01 12:00:00"},
        }

        manifest = [_entry("/tmp/image.jpg", "/tmp/image.json")]
        reconcile(manifest, make_options())

        # Verify no metadata changes were needed
        assert manifest[0]["metadata"]["status"] == "noop"

        # Verify no tags were queued for writing
        assert manifest[0]["metadata"]["writeTags"] == []

        # Verify dates from disk are preserved even without sidecar
        assert "2023-01-01T12:00:00" in manifest[0]["metadata"]["dates"]

    @patch("pixelkasten.stages.reconcile.read_metadata")
    @patch("pixelkasten.stages.reconcile.read_sidecar")
    def test_does_not_queue_writes_when_disk_already_has_data(self, mock_sidecar, mock_metadata):
        mock_metadata.return_value = {
            "/tmp/image.jpg": {"EXIF:DateTimeOriginal": "2023:01:01 12:00:00"},
        }
        mock_sidecar.return_value = {"timestamp": "1672574400", "geo": None}

        manifest = [_entry("/tmp/image.jpg", "/tmp/image.json")]
        reconcile(manifest, make_options())

        # Disk already has DateTimeOriginal -- noop
        assert manifest[0]["metadata"]["status"] == "noop"

        # No tags queued for writing
        assert manifest[0]["metadata"]["writeTags"] == []

    @patch("pixelkasten.stages.reconcile.read_metadata")
    @patch("pixelkasten.stages.reconcile.read_sidecar")
    def test_queues_timestamp_write_when_missing_from_disk(self, mock_sidecar, mock_metadata):
        # Disk has no timestamp
        mock_metadata.return_value = {"/tmp/image.jpg": {}}
        mock_sidecar.return_value = {"timestamp": "1672574400", "geo": None}

        manifest = [_entry("/tmp/image.jpg", "/tmp/image.json")]
        reconcile(manifest, make_options())

        # Verify entry was marked for processing
        assert manifest[0]["metadata"]["status"] == "processed"

        # Verify at least one tag was queued for writing
        assert len(manifest[0]["metadata"]["writeTags"]) >= 1

        # Verify the EXIF timestamp tag format is correct
        assert manifest[0]["metadata"]["writeTags"][0].startswith("SubSecDateTimeOriginal=")

        # Verify timestamp was prepended to dates
        assert manifest[0]["metadata"]["dates"][0] == "2023-01-01T12:00:00"

    @patch("pixelkasten.stages.reconcile.read_metadata")
    @patch("pixelkasten.stages.reconcile.read_sidecar")
    def test_queues_geo_write_when_missing_from_disk(self, mock_sidecar, mock_metadata):
        mock_metadata.return_value = {"/tmp/image.jpg": {}}
        mock_sidecar.return_value = {
            "timestamp": None,
            "geo": {"latitude": 40.7128, "longitude": -74.006, "altitude": 10},
        }

        manifest = [_entry("/tmp/image.jpg", "/tmp/image.json")]
        reconcile(manifest, make_options())

        # Verify entry was marked for processing
        assert manifest[0]["metadata"]["status"] == "processed"

        # Verify geo tags were queued for writing (EXIF handler produces 4 geo tags)
        assert len(manifest[0]["metadata"]["writeTags"]) >= 1

    @patch("pixelkasten.stages.reconcile.read_metadata")
    @patch("pixelkasten.stages.reconcile.read_sidecar")
    def test_queues_both_timestamp_and_geo_when_both_missing(self, mock_sidecar, mock_metadata):
        mock_metadata.return_value = {"/tmp/image.jpg": {}}
        mock_sidecar.return_value = {
            "timestamp": "1672574400",
            "geo": {"latitude": 40.7128, "longitude": -74.006, "altitude": 10},
        }

        manifest = [_entry("/tmp/image.jpg", "/tmp/image.json")]
        reconcile(manifest, make_options())

        # Verify entry was marked for processing
        assert manifest[0]["metadata"]["status"] == "processed"

        # Should have at least 2 writeTags (timestamp + geo)
        assert len(manifest[0]["metadata"]["writeTags"]) >= 2

        # Verify timestamp was prepended to dates
        assert manifest[0]["metadata"]["dates"][0] == "2023-01-01T12:00:00"

    @patch("pixelkasten.stages.reconcile.read_metadata")
    @patch("pixelkasten.stages.reconcile.read_sidecar")
    def test_reads_metadata_in_batches_of_512(self, mock_sidecar, mock_metadata):
        mock_sidecar.return_value = None

        # Override read_metadata to return tags for each path
        def fake_read(paths, tags):
            return {p: {} for p in paths}

        mock_metadata.side_effect = fake_read

        # Create 1000 entries -- should result in 2 batches
        manifest = [_entry(f"/tmp/img_{i}.jpg") for i in range(1000)]

        reconcile(manifest, make_options())

        # Verify metadata was read in exactly 2 batches
        assert mock_metadata.call_count == 2

        # First batch: 512 items
        assert len(mock_metadata.call_args_list[0][0][0]) == 512

        # Second batch: 488 items
        assert len(mock_metadata.call_args_list[1][0][0]) == 488

    @patch("pixelkasten.stages.reconcile.read_metadata")
    @patch("pixelkasten.stages.reconcile.read_sidecar")
    def test_marks_error_when_exiftool_missing_file(self, mock_sidecar, mock_metadata):
        # Return empty dict (file not found in exiftool output)
        mock_metadata.return_value = {}
        mock_sidecar.return_value = None

        manifest = [_entry("/tmp/missing.jpg", "/tmp/missing.json")]
        reconcile(manifest, make_options())

        # Verify error was recorded without throwing
        assert manifest[0]["metadata"]["status"] == "error"

    @patch("pixelkasten.stages.reconcile.read_metadata")
    @patch("pixelkasten.stages.reconcile.read_sidecar")
    def test_marks_unsupported_file_types_as_skipped(self, mock_sidecar, mock_metadata):
        mock_metadata.return_value = {"/tmp/file.unknown": {}}
        mock_sidecar.return_value = None

        manifest = [_entry("/tmp/file.unknown")]
        reconcile(manifest, make_options())

        # Verify unsupported file type was skipped
        assert manifest[0]["metadata"]["status"] == "skipped"

        # Verify reason is set
        assert "No metadata handler for .unknown" in manifest[0]["metadata"]["reason"]

        # Verify empty writeTags and dates
        assert manifest[0]["metadata"]["writeTags"] == []
        assert manifest[0]["metadata"]["dates"] == []

    @patch("pixelkasten.stages.reconcile.read_metadata")
    @patch("pixelkasten.stages.reconcile.read_sidecar")
    def test_does_not_queue_writeTags_when_skip_embed(self, mock_sidecar, mock_metadata):
        mock_metadata.return_value = {"/tmp/image.jpg": {}}
        mock_sidecar.return_value = {
            "timestamp": "1672574400",
            "geo": {"latitude": 40.7128, "longitude": -74.006, "altitude": 10},
        }

        manifest = [_entry("/tmp/image.jpg", "/tmp/image.json")]
        reconcile(manifest, make_options(skip_embed=True))

        # No writeTags queued due to skip_embed
        assert manifest[0]["metadata"]["writeTags"] == []

        # Status is noop since no writes are queued
        assert manifest[0]["metadata"]["status"] == "noop"

        # But dates should still be populated (needed for rename stage)
        assert manifest[0]["metadata"]["dates"][0] == "2023-01-01T12:00:00"
