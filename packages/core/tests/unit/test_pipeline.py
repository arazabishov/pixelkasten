"""
Tests for the unified pipeline orchestrator.

Tests stage sequencing, skip flags, dry-run, and hooks.
All I/O-bound stages are mocked.
"""

from unittest.mock import MagicMock, patch

from helpers import make_options
from pixelkasten.core.types import ManifestEntry, Source
from pixelkasten.configuration import Hooks, _noop_progress

PATCH_PREFIX = "pixelkasten.pipeline"


@patch(f"{PATCH_PREFIX}.report")
@patch(f"{PATCH_PREFIX}.apply")
@patch(f"{PATCH_PREFIX}.rename")
@patch(f"{PATCH_PREFIX}.dedupe_resolve")
@patch(f"{PATCH_PREFIX}.dedupe_hash")
@patch(f"{PATCH_PREFIX}.reconcile")
@patch(f"{PATCH_PREFIX}.link")
@patch(f"{PATCH_PREFIX}.scan")
class TestPipeline:
    def _run(self, options, hooks=None):
        from pixelkasten.pipeline import run_pipeline

        return run_pipeline(options, hooks or Hooks(), progress=_noop_progress)

    def test_runs_all_stages(
        self,
        mock_scan,
        mock_link,
        mock_reconcile,
        mock_hash,
        mock_resolve,
        mock_rename,
        mock_apply,
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
        mock_rename.assert_called_once()
        mock_apply.assert_called_once()
        mock_report.assert_called_once()

    def test_skips_dedupe(
        self,
        mock_scan,
        mock_link,
        mock_reconcile,
        mock_hash,
        mock_resolve,
        mock_rename,
        mock_apply,
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

    def test_skips_reconcile_when_both_embed_and_rename_skipped(
        self,
        mock_scan,
        mock_link,
        mock_reconcile,
        mock_hash,
        mock_resolve,
        mock_rename,
        mock_apply,
        mock_report,
    ):
        mock_scan.return_value = {
            "files_media": [],
            "files_metadata": [],
            "files_metadata_albums": [],
        }
        mock_link.return_value = {"manifest": [], "stats": {}}

        self._run(make_options(skip_embed=True, skip_rename=True))

        mock_reconcile.assert_not_called()
        mock_rename.assert_not_called()

    def test_dry_run_skips_apply_and_report(
        self,
        mock_scan,
        mock_link,
        mock_reconcile,
        mock_hash,
        mock_resolve,
        mock_rename,
        mock_apply,
        mock_report,
    ):
        mock_scan.return_value = {
            "files_media": [],
            "files_metadata": [],
            "files_metadata_albums": [],
        }
        mock_link.return_value = {"manifest": [], "stats": {}}

        self._run(make_options(dry_run=True))

        mock_apply.assert_not_called()
        mock_report.assert_not_called()

    def test_returns_manifest(
        self,
        mock_scan,
        mock_link,
        mock_reconcile,
        mock_hash,
        mock_resolve,
        mock_rename,
        mock_apply,
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
        mock_rename,
        mock_apply,
        mock_report,
    ):
        mock_scan.return_value = {
            "files_media": [],
            "files_metadata": [],
            "files_metadata_albums": [],
        }
        mock_link.return_value = {"manifest": [], "stats": {}}

        hooks = Hooks(
            on_scan=MagicMock(),
            on_link=MagicMock(),
            on_dedupe=MagicMock(),
            on_reconcile=MagicMock(),
            on_rename=MagicMock(),
            on_apply=MagicMock(),
        )

        self._run(make_options(), hooks)

        hooks.on_scan.assert_called_once()
        hooks.on_link.assert_called_once()
        hooks.on_dedupe.assert_called_once()
        hooks.on_reconcile.assert_called_once()
        hooks.on_rename.assert_called_once()
        hooks.on_apply.assert_called_once()
