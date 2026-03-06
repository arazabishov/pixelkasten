"""
Tests for the sidecar module — ported from packages/core/test/core/sidecar.test.js.

Uses tmp_path pytest fixture to write real JSON files (no mocking needed).
"""

import json

import pytest

from pixelkasten.tools.sidecar import read_sidecar


def _write_sidecar(tmp_path, data):
    """Helper to write a JSON sidecar file and return the path."""
    path = tmp_path / "sidecar.json"
    path.write_text(json.dumps(data))
    return path


class TestReadSidecar:
    def test_returns_none_for_none_path(self):
        assert read_sidecar(None) is None

    def test_returns_none_for_empty_string_path(self):
        assert read_sidecar("") is None

    def test_extracts_timestamp_from_photo_taken_time(self, tmp_path):
        path = _write_sidecar(
            tmp_path,
            {
                "photoTakenTime": {
                    "timestamp": "1719935787",
                    "formatted": "Jul 2, 2024",
                },
                "geoData": {"latitude": 0.0, "longitude": 0.0, "altitude": 0.0},
            },
        )

        result = read_sidecar(path)
        assert result is not None

        # Unix epoch string returned as-is
        assert result["timestamp"] == "1719935787"

    def test_returns_none_timestamp_when_photo_taken_time_absent(self, tmp_path):
        path = _write_sidecar(
            tmp_path,
            {
                "geoData": {"latitude": 0.0, "longitude": 0.0, "altitude": 0.0},
            },
        )

        result = read_sidecar(path)
        assert result is not None

        assert result["timestamp"] is None

    def test_prefers_geo_data_exif_over_geo_data(self, tmp_path):
        path = _write_sidecar(
            tmp_path,
            {
                "photoTakenTime": {"timestamp": "1719935787"},
                "geoData": {
                    "latitude": 10.0,
                    "longitude": 20.0,
                    "altitude": 5.0,
                    "latitudeSpan": 0.0,
                    "longitudeSpan": 0.0,
                },
                "geoDataExif": {
                    "latitude": 48.8584,
                    "longitude": 2.2945,
                    "altitude": 35.0,
                    "latitudeSpan": 0.0,
                    "longitudeSpan": 0.0,
                },
            },
        )

        result = read_sidecar(path)
        assert result is not None

        # geoDataExif coordinates used, not geoData
        assert result["geo"] == {
            "latitude": 48.8584,
            "longitude": 2.2945,
            "altitude": 35.0,
        }

    def test_falls_back_to_geo_data_when_exif_absent(self, tmp_path):
        path = _write_sidecar(
            tmp_path,
            {
                "photoTakenTime": {"timestamp": "1719935787"},
                "geoData": {
                    "latitude": 40.6892,
                    "longitude": -74.0445,
                    "altitude": 10.0,
                    "latitudeSpan": 0.0,
                    "longitudeSpan": 0.0,
                },
            },
        )

        result = read_sidecar(path)
        assert result is not None

        assert result["geo"] == {
            "latitude": 40.6892,
            "longitude": -74.0445,
            "altitude": 10.0,
        }

    def test_treats_zero_zero_geo_data_as_missing(self, tmp_path):
        path = _write_sidecar(
            tmp_path,
            {
                "photoTakenTime": {"timestamp": "1719935787"},
                "geoData": {
                    "latitude": 0.0,
                    "longitude": 0.0,
                    "altitude": 0.0,
                    "latitudeSpan": 0.0,
                    "longitudeSpan": 0.0,
                },
            },
        )

        result = read_sidecar(path)
        assert result is not None

        # (0, 0) treated as no geo data (Google's default for missing location)
        assert result["geo"] is None

    def test_treats_zero_zero_geo_data_exif_as_missing(self, tmp_path):
        path = _write_sidecar(
            tmp_path,
            {
                "photoTakenTime": {"timestamp": "1719935787"},
                "geoData": {"latitude": 0.0, "longitude": 0.0, "altitude": 0.0},
                "geoDataExif": {"latitude": 0, "longitude": 0, "altitude": 0},
            },
        )

        result = read_sidecar(path)
        assert result is not None

        assert result["geo"] is None

    def test_falls_back_to_geo_data_when_exif_is_zero_zero(self, tmp_path):
        path = _write_sidecar(
            tmp_path,
            {
                "photoTakenTime": {"timestamp": "1719935787"},
                "geoData": {
                    "latitude": 40.6892,
                    "longitude": -74.0445,
                    "altitude": 10.0,
                },
                "geoDataExif": {"latitude": 0, "longitude": 0, "altitude": 0},
            },
        )

        result = read_sidecar(path)
        assert result is not None

        # geoData used because geoDataExif has zeroed coordinates
        assert result["geo"] == {
            "latitude": 40.6892,
            "longitude": -74.0445,
            "altitude": 10.0,
        }

    def test_strips_span_fields_from_geo(self, tmp_path):
        path = _write_sidecar(
            tmp_path,
            {
                "photoTakenTime": {"timestamp": "1719935787"},
                "geoDataExif": {
                    "latitude": 48.8584,
                    "longitude": 2.2945,
                    "altitude": 35.0,
                    "latitudeSpan": 0.003,
                    "longitudeSpan": 0.004,
                },
            },
        )

        result = read_sidecar(path)
        assert result is not None
        assert result["geo"] is not None

        # Span fields not included in output
        assert "latitudeSpan" not in result["geo"]
        assert "longitudeSpan" not in result["geo"]

    def test_preserves_negative_altitude(self, tmp_path):
        path = _write_sidecar(
            tmp_path,
            {
                "photoTakenTime": {"timestamp": "1735645750"},
                "geoDataExif": {
                    "latitude": 40.3865,
                    "longitude": 49.8916,
                    "altitude": -11.19,
                },
            },
        )

        result = read_sidecar(path)
        assert result is not None
        assert result["geo"] is not None

        # Negative altitude preserved (below sea level)
        assert result["geo"]["altitude"] == -11.19

    def test_ignores_unrelated_sidecar_fields(self, tmp_path):
        path = _write_sidecar(
            tmp_path,
            {
                "title": "IMG_001.jpg",
                "description": "My vacation photo",
                "imageViews": "42",
                "creationTime": {"timestamp": "1700000000"},
                "photoTakenTime": {"timestamp": "1719935787"},
                "geoData": {"latitude": 0.0, "longitude": 0.0, "altitude": 0.0},
                "url": "https://photos.google.com/photo/abc123",
                "googlePhotosOrigin": {"mobileUpload": {"deviceType": "IOS_PHONE"}},
            },
        )

        result = read_sidecar(path)
        assert result is not None

        # Only timestamp and geo returned
        assert result["timestamp"] == "1719935787"
        assert result["geo"] is None
        assert "title" not in result
        assert "description" not in result

    def test_raises_for_malformed_json(self, tmp_path):
        import re

        path = tmp_path / "broken.json"
        path.write_text("{ not valid json")

        with pytest.raises(RuntimeError, match=re.escape(f"Failed to read sidecar file at {path}")):
            read_sidecar(path)

    def test_raises_for_missing_file(self):
        with pytest.raises(
            RuntimeError, match="Failed to read sidecar file at /nonexistent/path.json"
        ):
            read_sidecar("/nonexistent/path.json")
