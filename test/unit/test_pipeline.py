"""
Tests for the unified pipeline orchestrator.

Tests stage sequencing, skip flags, dry-run, hooks, mode dispatch, and workspace caching.
All I/O-bound stages are mocked.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

PATCH_PREFIX = "pixelkasten.pipeline"


@patch(f"{PATCH_PREFIX}.report")
@patch(f"{PATCH_PREFIX}.apply")
@patch(f"{PATCH_PREFIX}.rename")
@patch(f"{PATCH_PREFIX}.dedupe_resolve")
@patch(f"{PATCH_PREFIX}.dedupe_hash")
@patch(f"{PATCH_PREFIX}.reconcile")
@patch(f"{PATCH_PREFIX}.link")
@patch(f"{PATCH_PREFIX}.scan_takeout")
class TestTakeoutMode:
    def _run(self, options, hooks=None):
        from pixelkasten.pipeline import run_pipeline

        return run_pipeline(options, hooks)

    def test_runs_all_takeout_stages(
        self, mock_scan, mock_link, mock_reconcile,
        mock_hash, mock_resolve, mock_rename, mock_apply, mock_report,
    ):
        mock_scan.return_value = {"files_media": [], "files_metadata": [], "files_metadata_albums": []}
        mock_link.return_value = {"manifest": [], "stats": {}}

        self._run({"source": "/src", "destination": "/dest", "mode": "takeout"})

        mock_scan.assert_called_once()
        mock_link.assert_called_once()
        mock_reconcile.assert_called_once()
        mock_hash.assert_called_once()
        mock_resolve.assert_called_once()
        mock_rename.assert_called_once()
        mock_apply.assert_called_once()
        mock_report.assert_called_once()

    def test_skips_dedupe(
        self, mock_scan, mock_link, mock_reconcile,
        mock_hash, mock_resolve, mock_rename, mock_apply, mock_report,
    ):
        mock_scan.return_value = {"files_media": [], "files_metadata": [], "files_metadata_albums": []}
        mock_link.return_value = {"manifest": [], "stats": {}}

        self._run({"source": "/src", "destination": "/dest", "mode": "takeout", "skip_dedupe": True})

        mock_hash.assert_not_called()
        mock_resolve.assert_not_called()

    def test_skips_reconcile_when_both_embed_and_rename_skipped(
        self, mock_scan, mock_link, mock_reconcile,
        mock_hash, mock_resolve, mock_rename, mock_apply, mock_report,
    ):
        mock_scan.return_value = {"files_media": [], "files_metadata": [], "files_metadata_albums": []}
        mock_link.return_value = {"manifest": [], "stats": {}}

        self._run({
            "source": "/src", "destination": "/dest", "mode": "takeout",
            "skip_embed": True, "skip_rename": True,
        })

        mock_reconcile.assert_not_called()
        mock_rename.assert_not_called()

    def test_dry_run_skips_apply_and_report(
        self, mock_scan, mock_link, mock_reconcile,
        mock_hash, mock_resolve, mock_rename, mock_apply, mock_report,
    ):
        mock_scan.return_value = {"files_media": [], "files_metadata": [], "files_metadata_albums": []}
        mock_link.return_value = {"manifest": [], "stats": {}}

        self._run({"source": "/src", "destination": "/dest", "mode": "takeout", "dry_run": True})

        mock_apply.assert_not_called()
        mock_report.assert_not_called()

    def test_returns_manifest(
        self, mock_scan, mock_link, mock_reconcile,
        mock_hash, mock_resolve, mock_rename, mock_apply, mock_report,
    ):
        mock_scan.return_value = {"files_media": [], "files_metadata": [], "files_metadata_albums": []}
        expected = [{"mediaPath": "/src/photo.jpg"}]
        mock_link.return_value = {"manifest": expected, "stats": {}}

        result = self._run({"source": "/src", "destination": "/dest", "mode": "takeout"})

        assert result is expected

    def test_calls_hooks(
        self, mock_scan, mock_link, mock_reconcile,
        mock_hash, mock_resolve, mock_rename, mock_apply, mock_report,
    ):
        mock_scan.return_value = {"files_media": [], "files_metadata": [], "files_metadata_albums": []}
        mock_link.return_value = {"manifest": [], "stats": {}}

        hooks = {
            "on_scan": MagicMock(),
            "on_link": MagicMock(),
            "on_dedupe": MagicMock(),
            "on_reconcile": MagicMock(),
            "on_rename": MagicMock(),
            "on_apply": MagicMock(),
        }

        self._run({"source": "/src", "destination": "/dest", "mode": "takeout"}, hooks)

        hooks["on_scan"].assert_called_once()
        hooks["on_link"].assert_called_once()
        hooks["on_dedupe"].assert_called_once()
        hooks["on_reconcile"].assert_called_once()
        hooks["on_rename"].assert_called_once()
        hooks["on_apply"].assert_called_once()


class TestRunTakeoutPipelineConvenience:
    @patch(f"{PATCH_PREFIX}.run_pipeline")
    def test_sets_mode_to_takeout(self, mock_run):
        mock_run.return_value = []

        from pixelkasten.pipeline import run_takeout_pipeline

        run_takeout_pipeline({"source": "/src", "destination": "/dest"})

        call_options = mock_run.call_args[0][0]
        assert call_options["mode"] == "takeout"


class TestWorkspaceCaching:
    @patch(f"{PATCH_PREFIX}.report")
    @patch(f"{PATCH_PREFIX}.apply")
    @patch(f"{PATCH_PREFIX}.rename")
    @patch(f"{PATCH_PREFIX}.dedupe_resolve")
    @patch(f"{PATCH_PREFIX}.dedupe_hash")
    @patch(f"{PATCH_PREFIX}.reconcile")
    @patch(f"{PATCH_PREFIX}.link")
    @patch(f"{PATCH_PREFIX}.scan_takeout")
    def test_saves_manifest_to_workspace(
        self, mock_scan, mock_link, mock_reconcile,
        mock_hash, mock_resolve, mock_rename, mock_apply, mock_report,
        tmp_path,
    ):
        mock_scan.return_value = {"files_media": [], "files_metadata": [], "files_metadata_albums": []}
        mock_link.return_value = {"manifest": [{"mediaPath": "/test.jpg"}], "stats": {}}

        from pixelkasten.pipeline import run_pipeline

        run_pipeline({
            "source": "/src", "destination": "/dest",
            "mode": "takeout", "workspace": str(tmp_path),
        })

        # Manifest should be saved
        manifest_path = tmp_path / "manifest.json"
        assert manifest_path.exists()

        saved = json.loads(manifest_path.read_text())
        assert len(saved) == 1
        assert saved[0]["mediaPath"] == "/test.jpg"

    @patch(f"{PATCH_PREFIX}.report")
    @patch(f"{PATCH_PREFIX}.apply")
    @patch(f"{PATCH_PREFIX}.rename")
    @patch(f"{PATCH_PREFIX}.dedupe_resolve")
    @patch(f"{PATCH_PREFIX}.dedupe_hash")
    @patch(f"{PATCH_PREFIX}.reconcile")
    @patch(f"{PATCH_PREFIX}.link")
    @patch(f"{PATCH_PREFIX}.scan_takeout")
    def test_loads_manifest_from_workspace(
        self, mock_scan, mock_link, mock_reconcile,
        mock_hash, mock_resolve, mock_rename, mock_apply, mock_report,
        tmp_path,
    ):
        # Pre-populate workspace
        cached = [{"mediaPath": "/cached.jpg"}]
        (tmp_path / "manifest.json").write_text(json.dumps(cached))

        from pixelkasten.pipeline import run_pipeline

        result = run_pipeline({
            "source": "/src", "destination": "/dest",
            "mode": "takeout", "workspace": str(tmp_path),
        })

        # Scan and link should NOT be called (loaded from cache)
        mock_scan.assert_not_called()
        mock_link.assert_not_called()

        # Manifest should be the cached one
        assert result[0]["mediaPath"] == "/cached.jpg"

    @patch(f"{PATCH_PREFIX}.report")
    @patch(f"{PATCH_PREFIX}.apply")
    @patch(f"{PATCH_PREFIX}.rename")
    @patch(f"{PATCH_PREFIX}.dedupe_resolve")
    @patch(f"{PATCH_PREFIX}.dedupe_hash")
    @patch(f"{PATCH_PREFIX}.reconcile")
    @patch(f"{PATCH_PREFIX}.link")
    @patch(f"{PATCH_PREFIX}.scan_takeout")
    def test_rescan_ignores_workspace_cache(
        self, mock_scan, mock_link, mock_reconcile,
        mock_hash, mock_resolve, mock_rename, mock_apply, mock_report,
        tmp_path,
    ):
        # Pre-populate workspace
        (tmp_path / "manifest.json").write_text(json.dumps([{"mediaPath": "/old.jpg"}]))

        mock_scan.return_value = {"files_media": [], "files_metadata": [], "files_metadata_albums": []}
        mock_link.return_value = {"manifest": [{"mediaPath": "/fresh.jpg"}], "stats": {}}

        from pixelkasten.pipeline import run_pipeline

        result = run_pipeline({
            "source": "/src", "destination": "/dest",
            "mode": "takeout", "workspace": str(tmp_path),
            "rescan": True,
        })

        # Scan should be called despite cache existing
        mock_scan.assert_called_once()
        assert result[0]["mediaPath"] == "/fresh.jpg"
