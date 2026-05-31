"""
Tests for the ingest pipeline orchestrator.

Tests stage sequencing, skip flags, dry-run, and the shape of IngestResult.
All I/O-bound stages are mocked.
"""

from unittest.mock import patch

from helpers import make_options, noop_progress
from pixelkasten.commands.ingest.types import IngestEntry, Source

# Patch the stage names where they're looked up — inside the ingest module
# itself, not the package's __init__.
PATCH_PREFIX = "pixelkasten.commands.ingest.ingest"


@patch(f"{PATCH_PREFIX}.report")
@patch(f"{PATCH_PREFIX}.emit")
@patch(f"{PATCH_PREFIX}.dedupe_resolve")
@patch(f"{PATCH_PREFIX}.dedupe_hash")
@patch(f"{PATCH_PREFIX}.reconcile")
@patch(f"{PATCH_PREFIX}.link")
@patch(f"{PATCH_PREFIX}.scan")
class TestPipeline:
    def _run(self, options):
        from pixelkasten.commands.ingest import ingest

        return ingest(options, progress=noop_progress)

    def test_runs_all_stages(
        self,
        mock_scan,
        mock_link,
        mock_reconcile,
        mock_hash,
        mock_resolve,
        mock_emit,
        mock_report,
    ):
        mock_scan.return_value = {
            "files_media": [],
            "files_metadata": [],
            "files_metadata_albums": [],
        }
        mock_link.return_value = {"manifest": [], "stats": {}}

        self._run(make_options())

        mock_scan.assert_called_once()
        mock_link.assert_called_once()
        mock_reconcile.assert_called_once()
        mock_hash.assert_called_once()
        mock_resolve.assert_called_once()
        mock_emit.assert_called_once()
        mock_report.assert_called_once()

    def test_skips_dedupe(
        self,
        mock_scan,
        mock_link,
        mock_reconcile,
        mock_hash,
        mock_resolve,
        mock_emit,
        mock_report,
    ):
        mock_scan.return_value = {
            "files_media": [],
            "files_metadata": [],
            "files_metadata_albums": [],
        }
        mock_link.return_value = {"manifest": [], "stats": {}}

        self._run(make_options(skip_dedupe=True))

        mock_hash.assert_not_called()
        mock_resolve.assert_not_called()

    def test_reconcile_runs_even_when_metadata_write_is_skipped(
        self,
        mock_scan,
        mock_link,
        mock_reconcile,
        mock_hash,
        mock_resolve,
        mock_emit,
        mock_report,
    ):
        mock_scan.return_value = {
            "files_media": [],
            "files_metadata": [],
            "files_metadata_albums": [],
        }
        mock_link.return_value = {"manifest": [], "stats": {}}

        self._run(make_options(skip_metadata_write=True))

        # Reconcile must still run so the internal rename step has dates;
        # skip_metadata_write only suppresses queued EXIF write_tags within reconcile.
        mock_reconcile.assert_called_once()

    def test_dry_run_skips_emit_and_report(
        self,
        mock_scan,
        mock_link,
        mock_reconcile,
        mock_hash,
        mock_resolve,
        mock_emit,
        mock_report,
    ):
        mock_scan.return_value = {
            "files_media": [],
            "files_metadata": [],
            "files_metadata_albums": [],
        }
        mock_link.return_value = {"manifest": [], "stats": {}}

        self._run(make_options(dry_run=True))

        mock_emit.assert_not_called()
        mock_report.assert_not_called()

    def test_returns_ingest_result_with_manifest_and_link_stats(
        self,
        mock_scan,
        mock_link,
        mock_reconcile,
        mock_hash,
        mock_resolve,
        mock_emit,
        mock_report,
    ):
        scan_collections = {
            "files_media": [],
            "files_metadata": [],
            "files_metadata_albums": [],
        }
        mock_scan.return_value = scan_collections
        expected_manifest = [IngestEntry(media_path="/src/photo.jpg", source=Source(type="loose"))]
        expected_stats = {"unmatched_metadata_files": set(), "unmatched_media_files": set()}
        mock_link.return_value = {"manifest": expected_manifest, "stats": expected_stats}

        result = self._run(make_options())

        # Verify the manifest produced by link surfaces on the result
        assert result.manifest is expected_manifest
        # Verify link stats are exposed alongside the manifest for renderers
        assert result.link_stats is expected_stats
        # Verify the raw scan output is preserved on the result
        assert result.raw_collections is scan_collections
