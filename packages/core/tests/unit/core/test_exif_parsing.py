"""Unit tests for EXIF parsing helper functions in pixelkasten.core.exif."""

import pytest

from pixelkasten.core.exiftool import (
    _normalize_timestamp,
    _parse_exiftool_entry,
    _safe_float,
    _validate_gps,
)


class TestNormalizeTimestamp:
    def test_exif_colon_format_returns_iso(self):
        result = _normalize_timestamp("2019:07:15 14:30:00")
        assert result == "2019-07-15T14:30:00"

    def test_exif_colon_format_with_timezone_strips_offset(self):
        result = _normalize_timestamp("2019:07:15 14:30:00+02:00")
        assert result == "2019-07-15T14:30:00"

    def test_unix_epoch_numeric_returns_utc_iso(self):
        result = _normalize_timestamp(1563197400)
        assert result == "2019-07-15T13:30:00"

    def test_none_returns_none(self):
        assert _normalize_timestamp(None) is None

    def test_empty_string_returns_none(self):
        assert _normalize_timestamp("") is None

    def test_zero_date_returns_none(self):
        assert _normalize_timestamp("0000:00:00 00:00:00") is None

    def test_midnight_returns_correct_iso(self):
        result = _normalize_timestamp("2023:01:01 00:00:00")
        assert result == "2023-01-01T00:00:00"

    def test_end_of_day_returns_correct_iso(self):
        result = _normalize_timestamp("2023:12:31 23:59:59")
        assert result == "2023-12-31T23:59:59"


class TestValidateGps:
    def test_valid_coordinates_returns_parsed_floats(self):
        assert _validate_gps(37.8, -122.4) == (37.8, -122.4)

    def test_both_zero_returns_none(self):
        assert _validate_gps(0.0, 0.0) is None

    def test_none_values_returns_none(self):
        assert _validate_gps(None, None) is None

    def test_non_numeric_strings_returns_none(self):
        assert _validate_gps("abc", "xyz") is None

    def test_one_zero_one_nonzero_returns_parsed_floats(self):
        # Latitude zero is the equator -- perfectly valid.
        assert _validate_gps(0, 122.4) == (0.0, 122.4)


class TestSafeFloat:
    def test_valid_number_returns_float(self):
        assert _safe_float(42) == 42.0
        assert isinstance(_safe_float(42), float)

    def test_none_returns_none(self):
        assert _safe_float(None) is None

    def test_non_numeric_string_returns_none(self):
        assert _safe_float("not_a_number") is None


class TestParseExiftoolEntry:
    def test_full_metadata_returns_complete_exif_data(self):
        raw = {
            "SourceFile": "/photos/img.jpg",
            "EXIF:DateTimeOriginal": "2023:06:15 10:30:00",
            "Composite:GPSLatitude": 48.8584,
            "Composite:GPSLongitude": 2.2945,
            "Composite:GPSAltitude": 35.0,
            "EXIF:Model": "Pixel 7",
        }

        result = _parse_exiftool_entry(raw)

        # Timestamp parsed from DateTimeOriginal
        assert result["timestamp"] == "2023-06-15T10:30:00"

        # GPS populated with correct coordinates
        assert result["gps"] is not None
        assert result["gps"]["latitude"] == 48.8584
        assert result["gps"]["longitude"] == 2.2945
        assert result["gps"]["altitude"] == 35.0

        # Camera model extracted
        assert result["camera"] == "Pixel 7"

    def test_partial_metadata_without_gps_returns_none_gps(self):
        raw = {
            "SourceFile": "/photos/img.jpg",
            "EXIF:DateTimeOriginal": "2023:06:15 10:30:00",
        }

        result = _parse_exiftool_entry(raw)

        assert result["timestamp"] == "2023-06-15T10:30:00"
        assert result["gps"] is None
        assert result["camera"] is None

    def test_empty_dict_returns_all_none(self):
        result = _parse_exiftool_entry({})

        assert result["timestamp"] is None
        assert result["gps"] is None
        assert result["camera"] is None

    def test_datetime_original_wins_over_create_date(self):
        raw = {
            "EXIF:DateTimeOriginal": "2023:01:01 12:00:00",
            "EXIF:CreateDate": "2023:06:15 08:00:00",
        }

        result = _parse_exiftool_entry(raw)

        # DateTimeOriginal has higher priority and should be chosen.
        assert result["timestamp"] == "2023-01-01T12:00:00"
