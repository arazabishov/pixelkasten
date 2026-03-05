"""
Tests for the report module — ported from packages/core/test/core/report.test.js.
"""

import csv
import os

from helpers import make_options
from pixelkasten.core.report import report, resolve_status


class TestResolveStatus:
    def test_embedded_status(self):
        entry = {"apply": {"status": "embedded"}}
        assert resolve_status(entry) == {"status": "embedded", "reason": ""}

    def test_copied_status(self):
        entry = {"apply": {"status": "copied"}}
        assert resolve_status(entry) == {"status": "copied", "reason": ""}

    def test_apply_error_status(self):
        entry = {"apply": {"status": "error", "reason": "ENOENT"}}
        assert resolve_status(entry) == {"status": "error", "reason": "ENOENT"}

    def test_skipped_status(self):
        entry = {"metadata": {"status": "skipped", "reason": "No handler for .unknown"}}
        assert resolve_status(entry) == {
            "status": "skipped",
            "reason": "No handler for .unknown",
        }

    def test_deleted_status(self):
        entry = {"dedupe": {"status": "delete"}}
        assert resolve_status(entry) == {"status": "deleted", "reason": ""}

    def test_dedupe_error_status(self):
        entry = {"dedupe": {"status": "error", "reason": "Hash failed"}}
        assert resolve_status(entry) == {"status": "error", "reason": "Hash failed"}

    def test_unknown_state_fallback(self):
        entry = {}
        assert resolve_status(entry) == {"status": "error", "reason": "Unknown state"}


class TestReport:
    def test_writes_csv_with_correct_header_and_rows(self, tmp_path):
        manifest = [
            {
                "mediaPath": "/source/photos/IMG_001.jpg",
                "json": {
                    "path": "/source/photos/IMG_001.jpg.json",
                    "confidence": 3,
                },
                "dedupe": {"status": "keep"},
                "metadata": {
                    "status": "processed",
                    "writeTags": ["DateTimeOriginal=2023:01:01"],
                    "dates": ["2023-01-01T12:00:00"],
                },
                "apply": {
                    "status": "embedded",
                    "targetPath": "/dest/2023/01 - January/20230101-120000.jpg",
                },
            },
        ]
        options = make_options(source="/source", destination=str(tmp_path))

        result_path = report(manifest, options)

        # Verify report path
        assert result_path == os.path.join(str(tmp_path), "report.csv")

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
        assert rows[1][3] == "embedded"
        assert rows[1][4] == ""

    def test_resolves_deleted_entries(self, tmp_path):
        manifest = [
            {
                "mediaPath": "/source/dup.jpg",
                "json": None,
                "dedupe": {"status": "delete"},
            },
        ]
        options = make_options(source="/source", destination=str(tmp_path))

        report(manifest, options)

        with open(os.path.join(str(tmp_path), "report.csv")) as f:
            reader = csv.reader(f)
            rows = list(reader)

        # Verify status is deleted
        assert rows[1][3] == "deleted"

    def test_resolves_skipped_for_unsupported_formats(self, tmp_path):
        manifest = [
            {
                "mediaPath": "/source/video.avi",
                "json": {
                    "path": "/source/video.avi.json",
                    "confidence": 3,
                },
                "dedupe": {"status": "keep"},
                "metadata": {
                    "status": "skipped",
                    "reason": "No metadata handler for .avi",
                    "writeTags": [],
                    "dates": [],
                },
            },
        ]
        options = make_options(source="/source", destination=str(tmp_path))

        report(manifest, options)

        with open(os.path.join(str(tmp_path), "report.csv")) as f:
            reader = csv.reader(f)
            rows = list(reader)

        # Verify status is skipped with reason
        assert rows[1][3] == "skipped"
        assert rows[1][4] == "No metadata handler for .avi"

    def test_resolves_apply_error(self, tmp_path):
        manifest = [
            {
                "mediaPath": "/source/photo.jpg",
                "json": None,
                "dedupe": {"status": "keep"},
                "apply": {
                    "status": "error",
                    "reason": "ENOENT: no such file",
                },
            },
        ]
        options = make_options(source="/source", destination=str(tmp_path))

        report(manifest, options)

        with open(os.path.join(str(tmp_path), "report.csv")) as f:
            reader = csv.reader(f)
            rows = list(reader)

        # Verify status is error with reason
        assert rows[1][3] == "error"
        assert rows[1][4] == "ENOENT: no such file"

    def test_resolves_copied_status(self, tmp_path):
        manifest = [
            {
                "mediaPath": "/source/photo.jpg",
                "json": {
                    "path": "/source/photo.jpg.json",
                    "confidence": 2,
                },
                "dedupe": {"status": "keep"},
                "metadata": {
                    "status": "noop",
                    "writeTags": [],
                    "dates": ["2023-01-01T12:00:00"],
                },
                "apply": {
                    "status": "copied",
                    "targetPath": "/dest/photo.jpg",
                },
            },
        ]
        options = make_options(source="/source", destination=str(tmp_path))

        report(manifest, options)

        with open(os.path.join(str(tmp_path), "report.csv")) as f:
            reader = csv.reader(f)
            rows = list(reader)

        # Verify status is copied
        assert rows[1][3] == "copied"

    def test_escapes_commas_and_quotes_in_csv_fields(self, tmp_path):
        manifest = [
            {
                "mediaPath": '/source/photo, "special".jpg',
                "json": None,
                "apply": {
                    "status": "error",
                    "reason": 'Failed with "error"',
                },
            },
        ]
        options = make_options(source="/source", destination=str(tmp_path))

        report(manifest, options)

        with open(os.path.join(str(tmp_path), "report.csv")) as f:
            reader = csv.reader(f)
            rows = list(reader)

        # CSV module properly handles commas and quotes in round-trip
        assert rows[1][0] == 'photo, "special".jpg'
        assert rows[1][4] == 'Failed with "error"'

    def test_handles_entries_without_json_match(self, tmp_path):
        manifest = [
            {
                "mediaPath": "/source/unmatched.jpg",
                "json": None,
                "dedupe": {"status": "keep"},
                "apply": {
                    "status": "copied",
                    "targetPath": "/dest/unmatched.jpg",
                },
            },
        ]
        options = make_options(source="/source", destination=str(tmp_path))

        report(manifest, options)

        with open(os.path.join(str(tmp_path), "report.csv")) as f:
            reader = csv.reader(f)
            rows = list(reader)

        # metadata and confidence should be empty
        assert rows[1][1] == ""
        assert rows[1][2] == ""
        assert rows[1][3] == "copied"
