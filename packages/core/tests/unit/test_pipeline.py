"""
Tests for the unified pipeline orchestrator.

Tests stage sequencing, skip flags, dry-run, and hooks.
All I/O-bound stages are mocked.
"""

from unittest.mock import MagicMock, patch

from helpers import make_options, noop_progress
from pixelkasten.manifest import ManifestEntry, Source
from pixelkasten.configuration import Hooks

PATCH_PREFIX = "pixelkasten.pipeline"


@patch(f"{PATCH_PREFIX}.report")
@patch(f"{PATCH_PREFIX}.emit")
@patch(f"{PATCH_PREFIX}.dedupe_resolve")
@patch(f"{PATCH_PREFIX}.dedupe_hash")
@patch(f"{PATCH_PREFIX}.reconcile")
@patch(f"{PATCH_PREFIX}.link")
@patch(f"{PATCH_PREFIX}.scan")
class TestPipeline:
    def _run(self, options, hooks=None):
        from pixelkasten.pipeline import run_pipeline

        return run_pipeline(options, hooks or Hooks(), progress=noop_progress)

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

    def test_returns_manifest(
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
        expected = [ManifestEntry(media_path="/src/photo.jpg", source=Source(type="loose"))]
        mock_link.return_value = {"manifest": expected, "stats": {}}

        result = self._run(make_options())

        assert result is expected

    def test_calls_hooks(
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

        on_scan = MagicMock()
        on_link = MagicMock()
        on_dedupe = MagicMock()
        on_reconcile = MagicMock()
        on_apply = MagicMock()

        hooks = Hooks(
            on_scan=on_scan,
            on_link=on_link,
            on_dedupe=on_dedupe,
            on_reconcile=on_reconcile,
            on_apply=on_apply,
        )

        self._run(make_options(), hooks)

        on_scan.assert_called_once()
        on_link.assert_called_once()
        on_dedupe.assert_called_once()
        on_reconcile.assert_called_once()
        on_apply.assert_called_once()
