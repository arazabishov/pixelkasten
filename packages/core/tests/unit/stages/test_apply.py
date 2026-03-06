"""
Tests for the apply stage -- ported from packages/core/test/stages/apply.test.js.

Mocks shutil.copy2 (file copy), os.makedirs (directory creation), and
write_metadata (exiftool subprocess) to test pure logic without disk I/O.

Path comparisons use os.path.join for platform independence.
"""

import os
from unittest.mock import call, patch

from helpers import make_options
from pixelkasten.manifest import (
    ApplyResult,
    Dedupe,
    DedupeResult,
    ManifestEntry,
    Metadata,
    Rename,
    Sidecar,
    Source,
    Status,
)
from pixelkasten.stages.apply import apply

# Helper: build platform-correct paths for assertions
J = os.path.join


def _entry(
    media_path,
    dedupe_result=DedupeResult.KEEP,
    rename_path=None,
    write_tags=None,
    metadata_status=Status.PROCESSED,
    sidecar_path=None,
    skip_dedupe=False,
):
    """Helper to create a manifest entry for apply tests."""
    dedupe = (
        None if skip_dedupe else Dedupe(status=Status.PROCESSED, result=dedupe_result, hash="abc")
    )
    rename = Rename(status=Status.PROCESSED, target_path=rename_path) if rename_path else None
    metadata = (
        Metadata(status=metadata_status, write_tags=write_tags or [])
        if write_tags is not None
        else None
    )
    sidecar = Sidecar(path=sidecar_path, confidence=3) if sidecar_path else None

    return ManifestEntry(
        media_path=media_path,
        source=Source(type="loose"),
        dedupe=dedupe,
        rename=rename,
        metadata=metadata,
        sidecar=sidecar,
    )


class TestApply:
    @patch("pixelkasten.stages.apply.write_metadata")
    @patch("pixelkasten.stages.apply.shutil.copy2")
    @patch("pixelkasten.stages.apply.os.makedirs")
    def test_does_not_perform_disk_ops_when_manifest_is_empty(
        self, mock_makedirs, mock_copy2, mock_write_metadata
    ):
        manifest = []
        apply(manifest, make_options(destination="/dest"))

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
            _entry("/source/delete-me.jpg", dedupe_result=DedupeResult.DELETE),
            _entry("/source/keep-me.jpg", rename_path="2023/keep-me.jpg"),
        ]

        apply(manifest, make_options(destination="/dest", skip_metadata_write=True))

        assert mock_copy2.call_count == 1
        assert mock_copy2.call_args_list[0] == call(
            "/source/keep-me.jpg", J("/dest", "2023/keep-me.jpg")
        )
        assert manifest[0].apply is None
        assert manifest[1].apply is not None
        assert manifest[1].apply.result == ApplyResult.COPIED

    @patch("pixelkasten.stages.apply.write_metadata")
    @patch("pixelkasten.stages.apply.shutil.copy2")
    @patch("pixelkasten.stages.apply.os.makedirs")
    def test_uses_original_filename_when_rename_stage_was_skipped(
        self, mock_makedirs, mock_copy2, mock_write_metadata
    ):
        manifest = [_entry("/source/photos/IMG_1234.jpg")]

        apply(manifest, make_options(destination="/dest", skip_metadata_write=True))

        assert mock_copy2.call_args_list[0] == call(
            "/source/photos/IMG_1234.jpg", J("/dest", "IMG_1234.jpg")
        )
        assert manifest[0].apply is not None
        assert manifest[0].apply.result == ApplyResult.COPIED

    @patch("pixelkasten.stages.apply.write_metadata")
    @patch("pixelkasten.stages.apply.shutil.copy2")
    @patch("pixelkasten.stages.apply.os.makedirs")
    def test_uses_target_path_when_rename_stage_was_run(
        self, mock_makedirs, mock_copy2, mock_write_metadata
    ):
        manifest = [_entry("/source/IMG_1234.jpg", rename_path="2023/20230515-120000.jpg")]

        apply(manifest, make_options(destination="/dest", skip_metadata_write=True))

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
        manifest = [_entry("/source/photo.jpg", rename_path="photo.jpg", skip_dedupe=True)]

        apply(manifest, make_options(destination="/dest", skip_metadata_write=True))

        assert mock_copy2.call_count == 1
        assert manifest[0].apply is not None
        assert manifest[0].apply.result == ApplyResult.COPIED

    @patch("pixelkasten.stages.apply.write_metadata")
    @patch("pixelkasten.stages.apply.shutil.copy2")
    @patch("pixelkasten.stages.apply.os.makedirs")
    def test_only_checks_write_tags_to_decide_metadata_write_not_options(
        self, mock_makedirs, mock_copy2, mock_write_metadata
    ):
        manifest = [_entry("/source/photo.jpg", rename_path="photo.jpg", write_tags=[])]

        apply(manifest, make_options(destination="/dest"))

        mock_write_metadata.assert_not_called()
        assert manifest[0].apply is not None
        assert manifest[0].apply.result == ApplyResult.COPIED

    @patch("pixelkasten.stages.apply.write_metadata")
    @patch("pixelkasten.stages.apply.shutil.copy2")
    @patch("pixelkasten.stages.apply.os.makedirs")
    def test_skips_metadata_write_when_entry_has_no_write_tags(
        self, mock_makedirs, mock_copy2, mock_write_metadata
    ):
        manifest = [_entry("/source/photo.jpg", rename_path="photo.jpg", write_tags=[])]

        apply(manifest, make_options(destination="/dest"))

        mock_write_metadata.assert_not_called()
        assert manifest[0].apply is not None
        assert manifest[0].apply.result == ApplyResult.COPIED

    @patch("pixelkasten.stages.apply.write_metadata")
    @patch("pixelkasten.stages.apply.shutil.copy2")
    @patch("pixelkasten.stages.apply.os.makedirs")
    def test_skips_metadata_write_when_metadata_property_is_undefined(
        self, mock_makedirs, mock_copy2, mock_write_metadata
    ):
        manifest = [_entry("/source/photo.jpg", rename_path="photo.jpg")]

        apply(manifest, make_options(destination="/dest"))

        mock_write_metadata.assert_not_called()
        assert manifest[0].apply is not None
        assert manifest[0].apply.result == ApplyResult.COPIED

    @patch("pixelkasten.stages.apply.write_metadata")
    @patch("pixelkasten.stages.apply.shutil.copy2")
    @patch("pixelkasten.stages.apply.os.makedirs")
    def test_writes_metadata_into_copied_files(
        self, mock_makedirs, mock_copy2, mock_write_metadata
    ):
        manifest = [
            _entry(
                "/source/photo.jpg",
                rename_path="photo.jpg",
                write_tags=["DateTimeOriginal=2023:01:01 12:00:00"],
                metadata_status=Status.PROCESSED,
            ),
        ]

        apply(manifest, make_options(destination="/dest"))

        assert mock_write_metadata.call_count == 1
        assert mock_write_metadata.call_args_list[0] == call(
            J("/dest", "photo.jpg"),
            ["DateTimeOriginal=2023:01:01 12:00:00"],
        )
        assert manifest[0].apply is not None
        assert manifest[0].apply.result == ApplyResult.WRITTEN

    @patch("pixelkasten.stages.apply.write_metadata")
    @patch("pixelkasten.stages.apply.shutil.copy2")
    @patch("pixelkasten.stages.apply.os.makedirs")
    def test_marks_entry_as_error_when_copy_fails(
        self, mock_makedirs, mock_copy2, mock_write_metadata
    ):
        manifest = [_entry("/source/photo.jpg", rename_path="photo.jpg")]

        mock_copy2.side_effect = OSError("ENOENT: no such file")

        apply(manifest, make_options(destination="/dest", skip_metadata_write=True))

        assert manifest[0].apply is not None
        assert manifest[0].apply.status == Status.ERROR
        assert manifest[0].apply.error == "ENOENT: no such file"

    @patch("pixelkasten.stages.apply.write_metadata")
    @patch("pixelkasten.stages.apply.shutil.copy2")
    @patch("pixelkasten.stages.apply.os.makedirs")
    def test_marks_entry_as_error_when_metadata_write_fails(
        self, mock_makedirs, mock_copy2, mock_write_metadata
    ):
        manifest = [
            _entry(
                "/source/photo.jpg",
                rename_path="photo.jpg",
                write_tags=["DateTimeOriginal=2023:01:01 12:00:00"],
                metadata_status=Status.PROCESSED,
            ),
        ]

        mock_write_metadata.side_effect = RuntimeError("exiftool failed")

        apply(manifest, make_options(destination="/dest"))

        assert manifest[0].apply is not None
        assert manifest[0].apply.status == Status.ERROR
        assert manifest[0].apply.error == "exiftool failed"

    @patch("pixelkasten.stages.apply.write_metadata")
    @patch("pixelkasten.stages.apply.shutil.copy2")
    @patch("pixelkasten.stages.apply.os.makedirs")
    def test_stores_dest_path_in_apply_object(self, mock_makedirs, mock_copy2, mock_write_metadata):
        manifest = [_entry("/source/photo.jpg", rename_path="2023/photo.jpg")]

        apply(manifest, make_options(destination="/dest", skip_metadata_write=True))

        assert manifest[0].apply is not None
        assert manifest[0].apply.target_path == J("/dest", "2023/photo.jpg")

    @patch("pixelkasten.stages.apply.write_metadata")
    @patch("pixelkasten.stages.apply.shutil.copy2")
    @patch("pixelkasten.stages.apply.os.makedirs")
    def test_copies_sidecar_when_skip_metadata_write_is_true_and_sidecar_exists(
        self, mock_makedirs, mock_copy2, mock_write_metadata
    ):
        manifest = [
            _entry(
                "/source/photo.jpg",
                rename_path="2023/photo.jpg",
                sidecar_path="/source/photo.jpg.json",
            ),
        ]

        apply(manifest, make_options(destination="/dest", skip_metadata_write=True))

        assert mock_copy2.call_count == 2
        assert mock_copy2.call_args_list[1] == call(
            "/source/photo.jpg.json", J("/dest", "2023/photo.jpg") + ".json"
        )

    @patch("pixelkasten.stages.apply.write_metadata")
    @patch("pixelkasten.stages.apply.shutil.copy2")
    @patch("pixelkasten.stages.apply.os.makedirs")
    def test_does_not_copy_sidecar_when_skip_metadata_write_is_false(
        self, mock_makedirs, mock_copy2, mock_write_metadata
    ):
        manifest = [
            _entry(
                "/source/photo.jpg", rename_path="photo.jpg", sidecar_path="/source/photo.jpg.json"
            ),
        ]

        apply(manifest, make_options(destination="/dest"))

        assert mock_copy2.call_count == 1

    @patch("pixelkasten.stages.apply.write_metadata")
    @patch("pixelkasten.stages.apply.shutil.copy2")
    @patch("pixelkasten.stages.apply.os.makedirs")
    def test_does_not_copy_sidecar_when_no_matched_sidecar(
        self, mock_makedirs, mock_copy2, mock_write_metadata
    ):
        manifest = [_entry("/source/photo.jpg", rename_path="photo.jpg")]

        apply(manifest, make_options(destination="/dest", skip_metadata_write=True))

        assert mock_copy2.call_count == 1

    @patch("pixelkasten.stages.apply.write_metadata")
    @patch("pixelkasten.stages.apply.shutil.copy2")
    @patch("pixelkasten.stages.apply.os.makedirs")
    def test_uses_original_filename_for_sidecar_when_rename_is_skipped(
        self, mock_makedirs, mock_copy2, mock_write_metadata
    ):
        manifest = [
            _entry("/source/photos/IMG_1234.jpg", sidecar_path="/source/photos/IMG_1234.jpg.json")
        ]

        apply(manifest, make_options(destination="/dest", skip_metadata_write=True))

        assert mock_copy2.call_args_list[1] == call(
            "/source/photos/IMG_1234.jpg.json", J("/dest", "IMG_1234.jpg") + ".json"
        )

    @patch("pixelkasten.stages.apply.write_metadata")
    @patch("pixelkasten.stages.apply.shutil.copy2")
    @patch("pixelkasten.stages.apply.os.makedirs")
    def test_does_not_copy_sidecar_when_skip_metadata_write_is_not_set(
        self, mock_makedirs, mock_copy2, mock_write_metadata
    ):
        manifest = [
            _entry(
                "/source/photo.jpg", rename_path="photo.jpg", sidecar_path="/source/photo.jpg.json"
            ),
        ]

        apply(manifest, make_options(destination="/dest"))

        assert mock_copy2.call_count == 1

    @patch("pixelkasten.stages.apply.write_metadata")
    @patch("pixelkasten.stages.apply.shutil.copy2")
    @patch("pixelkasten.stages.apply.os.makedirs")
    def test_handles_nested_album_paths(self, mock_makedirs, mock_copy2, mock_write_metadata):
        manifest = [
            _entry("/source/photo.jpg", rename_path="2023/20230501 - Vacation/20230515-120000.jpg"),
        ]

        apply(manifest, make_options(destination="/dest", skip_metadata_write=True))

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
            _entry(
                "/source/photo.jpg", rename_path="photo.jpg", sidecar_path="/source/photo.jpg.json"
            ),
        ]

        def copy_side_effect(src, dst):
            if src == "/source/photo.jpg.json":
                raise OSError("ENOSPC: no space left")

        mock_copy2.side_effect = copy_side_effect

        apply(manifest, make_options(destination="/dest", skip_metadata_write=True))

        assert manifest[0].apply is not None
        assert manifest[0].apply.status == Status.ERROR
        assert manifest[0].apply.error == "ENOSPC: no space left"
