"""
Tests for the report module — ported from packages/core/test/core/report.test.js.
"""

import csv
import os

from helpers import make_options
from pixelkasten.commands.ingest.stages.report import report, _resolve_status
from pixelkasten.commands.ingest.types import (
    Apply,
    ApplyResult,
    Dedupe,
    DedupeResult,
    IngestEntry,
    Metadata,
    SidecarMatch,
    Source,
)
from pixelkasten.types import Status


def _entry(
    media_path="/source/photo.jpg",
    sidecar_path=None,
    sidecar_confidence=None,
    dedupe_result=None,
    dedupe_error=None,
    metadata_status=None,
    metadata_error=None,
    apply_result=None,
    apply_error=None,
    apply_target=None,
):
    """Helper to build IngestEntry for report tests."""
    sidecar = (
        SidecarMatch(path=sidecar_path, confidence=sidecar_confidence or 0)
        if sidecar_path
        else None
    )
    dedupe = None
    if dedupe_result is not None:
        dedupe = Dedupe(status=Status.PROCESSED, result=dedupe_result, hash="abc")
    elif dedupe_error is not None:
        dedupe = Dedupe(status=Status.ERROR, error=dedupe_error)

    metadata = None
    if metadata_status is not None:
        metadata = Metadata(status=metadata_status, error=metadata_error)

    apply_obj = None
    if apply_result is not None:
        apply_obj = Apply(status=Status.PROCESSED, result=apply_result, target_path=apply_target)
    elif apply_error is not None:
        apply_obj = Apply(status=Status.ERROR, error=apply_error)

    return IngestEntry(
        media_path=media_path,
        source=Source(type="loose"),
        sidecar=sidecar,
        dedupe=dedupe,
        metadata=metadata,
        apply=apply_obj,
    )


class TestResolveStatus:
    def test_written_status(self):
        entry = _entry(apply_result=ApplyResult.WRITTEN)
        assert _resolve_status(entry) == ("written", "")

    def test_copied_status(self):
        entry = _entry(apply_result=ApplyResult.COPIED)
        assert _resolve_status(entry) == ("copied", "")

    def test_apply_error_status(self):
        entry = _entry(apply_error="ENOENT")
        assert _resolve_status(entry) == ("error", "ENOENT")

    def test_skipped_status(self):
        entry = _entry(metadata_status=Status.SKIPPED, metadata_error="No handler for .unknown")
        assert _resolve_status(entry) == ("skipped", "No handler for .unknown")

    def test_deleted_status(self):
        entry = _entry(dedupe_result=DedupeResult.DELETE)
        assert _resolve_status(entry) == ("deleted", "")

    def test_dedupe_error_status(self):
        entry = _entry(dedupe_error="Hash failed")
        assert _resolve_status(entry) == ("error", "Hash failed")

    def test_unknown_state_fallback(self):
        entry = _entry()
        assert _resolve_status(entry) == ("error", "Unknown state")


class TestReport:
    def test_writes_csv_with_correct_header_and_rows(self, tmp_path):
        manifest = [
            _entry(
                media_path="/source/photos/IMG_001.jpg",
                sidecar_path="/source/photos/IMG_001.jpg.json",
                sidecar_confidence=3,
                dedupe_result=DedupeResult.KEEP,
                apply_result=ApplyResult.WRITTEN,
                apply_target="/dest/2023/01 - January/20230101-120000.jpg",
            ),
        ]
        # Set metadata with write_tags
        manifest[0].metadata = Metadata(
            status=Status.PROCESSED,
            write_tags=["DateTimeOriginal=2023:01:01"],
            dates=["2023-01-01T12:00:00"],
        )

        options = make_options(source="/source", destination=str(tmp_path))
        result_path = report(manifest, options)

        # Verify report path
        assert result_path == os.path.join(str(tmp_path), ".pixelkasten", "report.csv")

        # Verify file was written
        assert os.path.exists(result_path)

        with open(result_path) as f:
            reader = csv.reader(f)
            rows = list(reader)

        # Verify header
        assert rows[0] == ["media", "metadata", "confidence", "status", "reason"]

        # Verify data row: relative paths, confidence, status
        assert rows[1][0] == "photos/IMG_001.jpg"
        assert rows[1][1] == "photos/IMG_001.jpg.json"
        assert rows[1][2] == "3"
        assert rows[1][3] == "written"
        assert rows[1][4] == ""

    def test_resolves_deleted_entries(self, tmp_path):
        manifest = [_entry(media_path="/source/dup.jpg", dedupe_result=DedupeResult.DELETE)]
        options = make_options(source="/source", destination=str(tmp_path))

        report(manifest, options)

        with open(os.path.join(str(tmp_path), ".pixelkasten", "report.csv")) as f:
            reader = csv.reader(f)
            rows = list(reader)

        # Verify status is deleted
        assert rows[1][3] == "deleted"

    def test_resolves_skipped_for_unsupported_formats(self, tmp_path):
        manifest = [
            _entry(
                media_path="/source/video.avi",
                sidecar_path="/source/video.avi.json",
                sidecar_confidence=3,
                dedupe_result=DedupeResult.KEEP,
                metadata_status=Status.SKIPPED,
                metadata_error="No metadata handler for .avi",
            ),
        ]
        options = make_options(source="/source", destination=str(tmp_path))

        report(manifest, options)

        with open(os.path.join(str(tmp_path), ".pixelkasten", "report.csv")) as f:
            reader = csv.reader(f)
            rows = list(reader)

        # Verify status is skipped with reason
        assert rows[1][3] == "skipped"
        assert rows[1][4] == "No metadata handler for .avi"

    def test_resolves_apply_error(self, tmp_path):
        manifest = [
            _entry(
                media_path="/source/photo.jpg",
                dedupe_result=DedupeResult.KEEP,
                apply_error="ENOENT: no such file",
            ),
        ]
        options = make_options(source="/source", destination=str(tmp_path))

        report(manifest, options)

        with open(os.path.join(str(tmp_path), ".pixelkasten", "report.csv")) as f:
            reader = csv.reader(f)
            rows = list(reader)

        # Verify status is error with reason
        assert rows[1][3] == "error"
        assert rows[1][4] == "ENOENT: no such file"

    def test_resolves_copied_status(self, tmp_path):
        manifest = [
            _entry(
                media_path="/source/photo.jpg",
                sidecar_path="/source/photo.jpg.json",
                sidecar_confidence=2,
                dedupe_result=DedupeResult.KEEP,
                apply_result=ApplyResult.COPIED,
                apply_target="/dest/photo.jpg",
            ),
        ]
        manifest[0].metadata = Metadata(
            status=Status.PROCESSED,
            dates=["2023-01-01T12:00:00"],
        )
        options = make_options(source="/source", destination=str(tmp_path))

        report(manifest, options)

        with open(os.path.join(str(tmp_path), ".pixelkasten", "report.csv")) as f:
            reader = csv.reader(f)
            rows = list(reader)

        # Verify status is copied
        assert rows[1][3] == "copied"

    def test_escapes_commas_and_quotes_in_csv_fields(self, tmp_path):
        manifest = [
            _entry(
                media_path='/source/photo, "special".jpg',
                apply_error='Failed with "error"',
            ),
        ]
        options = make_options(source="/source", destination=str(tmp_path))

        report(manifest, options)

        with open(os.path.join(str(tmp_path), ".pixelkasten", "report.csv")) as f:
            reader = csv.reader(f)
            rows = list(reader)

        # CSV module properly handles commas and quotes in round-trip
        assert rows[1][0] == 'photo, "special".jpg'
        assert rows[1][4] == 'Failed with "error"'

    def test_handles_entries_without_json_match(self, tmp_path):
        manifest = [
            _entry(
                media_path="/source/unmatched.jpg",
                dedupe_result=DedupeResult.KEEP,
                apply_result=ApplyResult.COPIED,
                apply_target="/dest/unmatched.jpg",
            ),
        ]
        options = make_options(source="/source", destination=str(tmp_path))

        report(manifest, options)

        with open(os.path.join(str(tmp_path), ".pixelkasten", "report.csv")) as f:
            reader = csv.reader(f)
            rows = list(reader)

        # metadata and confidence should be empty
        assert rows[1][1] == ""
        assert rows[1][2] == ""
        assert rows[1][3] == "copied"
