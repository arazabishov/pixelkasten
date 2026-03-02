"""
Tests for the apply stage -- ported from packages/core/test/stages/apply.test.js.

Mocks shutil.copy2 (file copy), os.makedirs (directory creation), and
write_metadata (exiftool subprocess) to test pure logic without disk I/O.

Path comparisons use os.path.join for platform independence.
"""

import os
from unittest.mock import call, patch

from pixelkasten.stages.apply import apply

# Helper: build platform-correct paths for assertions
J = os.path.join


class TestApply:
    @patch("pixelkasten.stages.apply.write_metadata")
    @patch("pixelkasten.stages.apply.shutil.copy2")
    @patch("pixelkasten.stages.apply.os.makedirs")
    def test_does_not_perform_disk_ops_when_manifest_is_empty(
        self, mock_makedirs, mock_copy2, mock_write_metadata
    ):
        manifest = []
        apply(manifest, {"destination": "/dest"})

        mock_makedirs.assert_not_called()
        mock_copy2.assert_not_called()
        mock_write_metadata.assert_not_called()

    @patch("pixelkasten.stages.apply.write_metadata")
    @patch("pixelkasten.stages.apply.shutil.copy2")
    @patch("pixelkasten.stages.apply.os.makedirs")
    def test_does_not_copy_entries_marked_for_deletion(
        self, mock_makedirs, mock_copy2, mock_write_metadata
    ):
        manifest = [
            {
                "mediaPath": "/source/delete-me.jpg",
                "dedupe": {"status": "delete"},
            },
            {
                "mediaPath": "/source/keep-me.jpg",
                "dedupe": {"status": "keep"},
                "rename": {"targetPath": "2023/keep-me.jpg"},
            },
        ]

        apply(manifest, {"destination": "/dest", "skip_embed": True})

        assert mock_copy2.call_count == 1
        assert mock_copy2.call_args_list[0] == call(
            "/source/keep-me.jpg", J("/dest", "2023/keep-me.jpg")
        )
        assert "apply" not in manifest[0]
        assert manifest[1]["apply"]["status"] == "copied"

    @patch("pixelkasten.stages.apply.write_metadata")
    @patch("pixelkasten.stages.apply.shutil.copy2")
    @patch("pixelkasten.stages.apply.os.makedirs")
    def test_uses_original_filename_when_rename_stage_was_skipped(
        self, mock_makedirs, mock_copy2, mock_write_metadata
    ):
        manifest = [
            {
                "mediaPath": "/source/photos/IMG_1234.jpg",
                "dedupe": {"status": "keep"},
            },
        ]

        apply(manifest, {"destination": "/dest", "skip_embed": True})

        assert mock_copy2.call_args_list[0] == call(
            "/source/photos/IMG_1234.jpg", J("/dest", "IMG_1234.jpg")
        )
        assert manifest[0]["apply"]["status"] == "copied"

    @patch("pixelkasten.stages.apply.write_metadata")
    @patch("pixelkasten.stages.apply.shutil.copy2")
    @patch("pixelkasten.stages.apply.os.makedirs")
    def test_uses_target_path_when_rename_stage_was_run(
        self, mock_makedirs, mock_copy2, mock_write_metadata
    ):
        manifest = [
            {
                "mediaPath": "/source/IMG_1234.jpg",
                "dedupe": {"status": "keep"},
                "rename": {
                    "status": "processed",
                    "targetPath": "2023/20230515-120000.jpg",
                },
            },
        ]

        apply(manifest, {"destination": "/dest", "skip_embed": True})

        expected_dir = os.path.dirname(J("/dest", "2023/20230515-120000.jpg"))
        assert mock_makedirs.call_args_list[0] == call(expected_dir, exist_ok=True)

        assert mock_copy2.call_args_list[0] == call(
            "/source/IMG_1234.jpg", J("/dest", "2023/20230515-120000.jpg")
        )

    @patch("pixelkasten.stages.apply.write_metadata")
    @patch("pixelkasten.stages.apply.shutil.copy2")
    @patch("pixelkasten.stages.apply.os.makedirs")
    def test_treats_entries_without_dedupe_as_keepers(
        self, mock_makedirs, mock_copy2, mock_write_metadata
    ):
        manifest = [
            {
                "mediaPath": "/source/photo.jpg",
                "rename": {"targetPath": "photo.jpg"},
            },
        ]

        apply(manifest, {"destination": "/dest", "skip_embed": True})

        assert mock_copy2.call_count == 1
        assert manifest[0]["apply"]["status"] == "copied"

    @patch("pixelkasten.stages.apply.write_metadata")
    @patch("pixelkasten.stages.apply.shutil.copy2")
    @patch("pixelkasten.stages.apply.os.makedirs")
    def test_only_checks_write_tags_to_decide_embedding_not_options(
        self, mock_makedirs, mock_copy2, mock_write_metadata
    ):
        manifest = [
            {
                "mediaPath": "/source/photo.jpg",
                "dedupe": {"status": "keep"},
                "rename": {"targetPath": "photo.jpg"},
                "metadata": {
                    "status": "noop",
                    "writeTags": [],
                    "dates": ["2023-01-01T12:00:00"],
                },
            },
        ]

        apply(manifest, {"destination": "/dest", "skip_embed": False})

        mock_write_metadata.assert_not_called()
        assert manifest[0]["apply"]["status"] == "copied"

    @patch("pixelkasten.stages.apply.write_metadata")
    @patch("pixelkasten.stages.apply.shutil.copy2")
    @patch("pixelkasten.stages.apply.os.makedirs")
    def test_skips_embedding_when_entry_has_no_write_tags(
        self, mock_makedirs, mock_copy2, mock_write_metadata
    ):
        manifest = [
            {
                "mediaPath": "/source/photo.jpg",
                "dedupe": {"status": "keep"},
                "rename": {"targetPath": "photo.jpg"},
                "metadata": {"status": "noop", "writeTags": []},
            },
        ]

        apply(manifest, {"destination": "/dest"})

        mock_write_metadata.assert_not_called()
        assert manifest[0]["apply"]["status"] == "copied"

    @patch("pixelkasten.stages.apply.write_metadata")
    @patch("pixelkasten.stages.apply.shutil.copy2")
    @patch("pixelkasten.stages.apply.os.makedirs")
    def test_skips_embedding_when_metadata_property_is_undefined(
        self, mock_makedirs, mock_copy2, mock_write_metadata
    ):
        manifest = [
            {
                "mediaPath": "/source/photo.jpg",
                "dedupe": {"status": "keep"},
                "rename": {"targetPath": "photo.jpg"},
            },
        ]

        apply(manifest, {"destination": "/dest"})

        mock_write_metadata.assert_not_called()
        assert manifest[0]["apply"]["status"] == "copied"

    @patch("pixelkasten.stages.apply.write_metadata")
    @patch("pixelkasten.stages.apply.shutil.copy2")
    @patch("pixelkasten.stages.apply.os.makedirs")
    def test_embeds_metadata_into_copied_files(
        self, mock_makedirs, mock_copy2, mock_write_metadata
    ):
        manifest = [
            {
                "mediaPath": "/source/photo.jpg",
                "dedupe": {"status": "keep"},
                "rename": {"targetPath": "photo.jpg"},
                "metadata": {
                    "status": "processed",
                    "writeTags": ["DateTimeOriginal=2023:01:01 12:00:00"],
                },
            },
        ]

        apply(manifest, {"destination": "/dest"})

        assert mock_write_metadata.call_count == 1
        assert mock_write_metadata.call_args_list[0] == call(
            J("/dest", "photo.jpg"),
            ["DateTimeOriginal=2023:01:01 12:00:00"],
        )
        assert manifest[0]["apply"]["status"] == "embedded"

    @patch("pixelkasten.stages.apply.write_metadata")
    @patch("pixelkasten.stages.apply.shutil.copy2")
    @patch("pixelkasten.stages.apply.os.makedirs")
    def test_marks_entry_as_error_when_copy_fails(
        self, mock_makedirs, mock_copy2, mock_write_metadata
    ):
        manifest = [
            {
                "mediaPath": "/source/photo.jpg",
                "dedupe": {"status": "keep"},
                "rename": {"targetPath": "photo.jpg"},
            },
        ]

        mock_copy2.side_effect = OSError("ENOENT: no such file")

        apply(manifest, {"destination": "/dest", "skip_embed": True})

        assert manifest[0]["apply"]["status"] == "error"
        assert manifest[0]["apply"]["reason"] == "ENOENT: no such file"

    @patch("pixelkasten.stages.apply.write_metadata")
    @patch("pixelkasten.stages.apply.shutil.copy2")
    @patch("pixelkasten.stages.apply.os.makedirs")
    def test_marks_entry_as_error_when_embed_fails(
        self, mock_makedirs, mock_copy2, mock_write_metadata
    ):
        manifest = [
            {
                "mediaPath": "/source/photo.jpg",
                "dedupe": {"status": "keep"},
                "rename": {"targetPath": "photo.jpg"},
                "metadata": {
                    "status": "processed",
                    "writeTags": ["DateTimeOriginal=2023:01:01 12:00:00"],
                },
            },
        ]

        mock_write_metadata.side_effect = RuntimeError("exiftool failed")

        apply(manifest, {"destination": "/dest"})

        assert manifest[0]["apply"]["status"] == "error"
        assert manifest[0]["apply"]["reason"] == "exiftool failed"

    @patch("pixelkasten.stages.apply.write_metadata")
    @patch("pixelkasten.stages.apply.shutil.copy2")
    @patch("pixelkasten.stages.apply.os.makedirs")
    def test_stores_dest_path_in_apply_object(
        self, mock_makedirs, mock_copy2, mock_write_metadata
    ):
        manifest = [
            {
                "mediaPath": "/source/photo.jpg",
                "dedupe": {"status": "keep"},
                "rename": {"targetPath": "2023/photo.jpg"},
            },
        ]

        apply(manifest, {"destination": "/dest", "skip_embed": True})

        assert manifest[0]["apply"]["targetPath"] == J("/dest", "2023/photo.jpg")

    @patch("pixelkasten.stages.apply.write_metadata")
    @patch("pixelkasten.stages.apply.shutil.copy2")
    @patch("pixelkasten.stages.apply.os.makedirs")
    def test_copies_sidecar_when_skip_embed_is_true_and_sidecar_exists(
        self, mock_makedirs, mock_copy2, mock_write_metadata
    ):
        manifest = [
            {
                "mediaPath": "/source/photo.jpg",
                "dedupe": {"status": "keep"},
                "rename": {"targetPath": "2023/photo.jpg"},
                "json": {"path": "/source/photo.jpg.json"},
            },
        ]

        apply(manifest, {"destination": "/dest", "skip_embed": True})

        assert mock_copy2.call_count == 2
        assert mock_copy2.call_args_list[1] == call(
            "/source/photo.jpg.json", J("/dest", "2023/photo.jpg") + ".json"
        )

    @patch("pixelkasten.stages.apply.write_metadata")
    @patch("pixelkasten.stages.apply.shutil.copy2")
    @patch("pixelkasten.stages.apply.os.makedirs")
    def test_does_not_copy_sidecar_when_skip_embed_is_false(
        self, mock_makedirs, mock_copy2, mock_write_metadata
    ):
        manifest = [
            {
                "mediaPath": "/source/photo.jpg",
                "dedupe": {"status": "keep"},
                "rename": {"targetPath": "photo.jpg"},
                "json": {"path": "/source/photo.jpg.json"},
            },
        ]

        apply(manifest, {"destination": "/dest", "skip_embed": False})

        assert mock_copy2.call_count == 1

    @patch("pixelkasten.stages.apply.write_metadata")
    @patch("pixelkasten.stages.apply.shutil.copy2")
    @patch("pixelkasten.stages.apply.os.makedirs")
    def test_does_not_copy_sidecar_when_no_matched_sidecar(
        self, mock_makedirs, mock_copy2, mock_write_metadata
    ):
        manifest = [
            {
                "mediaPath": "/source/photo.jpg",
                "dedupe": {"status": "keep"},
                "rename": {"targetPath": "photo.jpg"},
                "json": None,
            },
        ]

        apply(manifest, {"destination": "/dest", "skip_embed": True})

        assert mock_copy2.call_count == 1

    @patch("pixelkasten.stages.apply.write_metadata")
    @patch("pixelkasten.stages.apply.shutil.copy2")
    @patch("pixelkasten.stages.apply.os.makedirs")
    def test_uses_original_filename_for_sidecar_when_rename_is_skipped(
        self, mock_makedirs, mock_copy2, mock_write_metadata
    ):
        manifest = [
            {
                "mediaPath": "/source/photos/IMG_1234.jpg",
                "dedupe": {"status": "keep"},
                "json": {"path": "/source/photos/IMG_1234.jpg.json"},
            },
        ]

        apply(manifest, {"destination": "/dest", "skip_embed": True})

        assert mock_copy2.call_args_list[1] == call(
            "/source/photos/IMG_1234.jpg.json", J("/dest", "IMG_1234.jpg") + ".json"
        )

    @patch("pixelkasten.stages.apply.write_metadata")
    @patch("pixelkasten.stages.apply.shutil.copy2")
    @patch("pixelkasten.stages.apply.os.makedirs")
    def test_does_not_copy_sidecar_when_skip_embed_is_not_set(
        self, mock_makedirs, mock_copy2, mock_write_metadata
    ):
        manifest = [
            {
                "mediaPath": "/source/photo.jpg",
                "dedupe": {"status": "keep"},
                "rename": {"targetPath": "photo.jpg"},
                "json": {"path": "/source/photo.jpg.json"},
            },
        ]

        apply(manifest, {"destination": "/dest"})

        assert mock_copy2.call_count == 1

    @patch("pixelkasten.stages.apply.write_metadata")
    @patch("pixelkasten.stages.apply.shutil.copy2")
    @patch("pixelkasten.stages.apply.os.makedirs")
    def test_handles_nested_album_paths(
        self, mock_makedirs, mock_copy2, mock_write_metadata
    ):
        manifest = [
            {
                "mediaPath": "/source/photo.jpg",
                "dedupe": {"status": "keep"},
                "rename": {
                    "status": "processed",
                    "targetPath": "2023/20230501 - Vacation/20230515-120000.jpg",
                },
            },
        ]

        apply(manifest, {"destination": "/dest", "skip_embed": True})

        expected_dest = J("/dest", "2023/20230501 - Vacation/20230515-120000.jpg")
        expected_dir = os.path.dirname(expected_dest)
        assert mock_makedirs.call_args_list[0] == call(expected_dir, exist_ok=True)
        assert mock_copy2.call_args_list[0] == call("/source/photo.jpg", expected_dest)

    @patch("pixelkasten.stages.apply.write_metadata")
    @patch("pixelkasten.stages.apply.shutil.copy2")
    @patch("pixelkasten.stages.apply.os.makedirs")
    def test_marks_entry_as_error_when_sidecar_copy_fails(
        self, mock_makedirs, mock_copy2, mock_write_metadata
    ):
        manifest = [
            {
                "mediaPath": "/source/photo.jpg",
                "dedupe": {"status": "keep"},
                "rename": {"targetPath": "photo.jpg"},
                "json": {"path": "/source/photo.jpg.json"},
            },
        ]

        def copy_side_effect(src, dst):
            if src == "/source/photo.jpg.json":
                raise OSError("ENOSPC: no space left")

        mock_copy2.side_effect = copy_side_effect

        apply(manifest, {"destination": "/dest", "skip_embed": True})

        assert manifest[0]["apply"]["status"] == "error"
        assert manifest[0]["apply"]["reason"] == "ENOSPC: no space left"
