"""
Tests for the takeout pipeline orchestrator.

Tests the stage sequencing, skip flags, dry-run behavior, and hooks.
All I/O-bound stages are mocked.
"""

from unittest.mock import MagicMock, patch

import pytest

# We patch at the pipeline module level since that's where the imports are used
PATCH_PREFIX = "pixelkasten.pipeline"


@patch(f"{PATCH_PREFIX}.report")
@patch(f"{PATCH_PREFIX}.apply")
@patch(f"{PATCH_PREFIX}.rename")
@patch(f"{PATCH_PREFIX}.reconcile")
@patch(f"{PATCH_PREFIX}.dedupe_resolve")
@patch(f"{PATCH_PREFIX}.dedupe_hash")
@patch(f"{PATCH_PREFIX}.link")
@patch(f"{PATCH_PREFIX}.scan_takeout")
class TestRunTakeoutPipeline:
    def _import_and_run(self, options, hooks=None):
        """Import fresh to avoid stale module state."""
        from pixelkasten.pipeline import run_takeout_pipeline

        return run_takeout_pipeline(options, hooks)

    def test_runs_all_stages_in_order(
        self,
        mock_scan,
        mock_link,
        mock_hash,
        mock_resolve,
        mock_reconcile,
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

        options = {"source": "/src", "destination": "/dest"}
        self._import_and_run(options)

        # All stages called
        mock_scan.assert_called_once()
        mock_link.assert_called_once()
        mock_hash.assert_called_once()
        mock_resolve.assert_called_once()
        mock_reconcile.assert_called_once()
        mock_rename.assert_called_once()
        mock_apply.assert_called_once()
        mock_report.assert_called_once()

    def test_skips_dedupe_when_flag_set(
        self,
        mock_scan,
        mock_link,
        mock_hash,
        mock_resolve,
        mock_reconcile,
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

        options = {"source": "/src", "destination": "/dest", "skip_dedupe": True}
        self._import_and_run(options)

        mock_hash.assert_not_called()
        mock_resolve.assert_not_called()

    def test_skips_reconcile_when_both_embed_and_rename_skipped(
        self,
        mock_scan,
        mock_link,
        mock_hash,
        mock_resolve,
        mock_reconcile,
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

        options = {
            "source": "/src",
            "destination": "/dest",
            "skip_embed": True,
            "skip_rename": True,
        }
        self._import_and_run(options)

        mock_reconcile.assert_not_called()
        mock_rename.assert_not_called()

    def test_runs_reconcile_when_only_embed_skipped(
        self,
        mock_scan,
        mock_link,
        mock_hash,
        mock_resolve,
        mock_reconcile,
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

        options = {"source": "/src", "destination": "/dest", "skip_embed": True}
        self._import_and_run(options)

        # reconcile still runs because rename needs dates
        mock_reconcile.assert_called_once()

    def test_skips_rename_when_flag_set(
        self,
        mock_scan,
        mock_link,
        mock_hash,
        mock_resolve,
        mock_reconcile,
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

        options = {"source": "/src", "destination": "/dest", "skip_rename": True}
        self._import_and_run(options)

        mock_rename.assert_not_called()

    def test_dry_run_skips_apply_and_report(
        self,
        mock_scan,
        mock_link,
        mock_hash,
        mock_resolve,
        mock_reconcile,
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

        options = {"source": "/src", "destination": "/dest", "dry_run": True}
        self._import_and_run(options)

        mock_apply.assert_not_called()
        mock_report.assert_not_called()

    def test_returns_manifest(
        self,
        mock_scan,
        mock_link,
        mock_hash,
        mock_resolve,
        mock_reconcile,
        mock_rename,
        mock_apply,
        mock_report,
    ):
        mock_scan.return_value = {
            "files_media": [],
            "files_metadata": [],
            "files_metadata_albums": [],
        }
        expected = [{"mediaPath": "/src/photo.jpg"}]
        mock_link.return_value = {"manifest": expected, "stats": {}}

        result = self._import_and_run({"source": "/src", "destination": "/dest"})

        assert result is expected

    def test_calls_hooks(
        self,
        mock_scan,
        mock_link,
        mock_hash,
        mock_resolve,
        mock_reconcile,
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

        hooks = {
            "on_scan": MagicMock(),
            "on_link": MagicMock(),
            "on_dedupe": MagicMock(),
            "on_reconcile": MagicMock(),
            "on_rename": MagicMock(),
            "on_apply": MagicMock(),
        }

        self._import_and_run(
            {"source": "/src", "destination": "/dest"},
            hooks,
        )

        hooks["on_scan"].assert_called_once()
        hooks["on_link"].assert_called_once()
        hooks["on_dedupe"].assert_called_once()
        hooks["on_reconcile"].assert_called_once()
        hooks["on_rename"].assert_called_once()
        hooks["on_apply"].assert_called_once()

    def test_passes_options_to_link(
        self,
        mock_scan,
        mock_link,
        mock_hash,
        mock_resolve,
        mock_reconcile,
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

        options = {
            "source": "/src",
            "destination": "/dest",
            "fuzzy_threshold": 40,
            "fuzzy": True,
        }
        self._import_and_run(options)

        # link receives raw_collections and options
        call_args = mock_link.call_args
        assert call_args[0][1] is options
