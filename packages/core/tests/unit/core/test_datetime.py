"""
Tests for the datetime module — ported from packages/core/test/core/datetime.test.js.

Covers normalize_disk_date (24 tests), parse_photo_taken_time (13 tests),
and parse_iso_date (5 tests).
"""

import pytest

from pixelkasten.core.datetime import (
    normalize_disk_date,
    parse_iso_date,
    parse_photo_taken_time,
)


class TestNormalizeDiskDate:
    def test_normalizes_standard_exif_datetime_original(self):
        assert normalize_disk_date("2023:05:20 14:30:00") == "2023-05-20T14:30:00"

    def test_normalizes_exif_create_date(self):
        assert normalize_disk_date("2024:03:15 08:45:30") == "2024-03-15T08:45:30"

    def test_normalizes_midnight_timestamp(self):
        assert normalize_disk_date("2023:01:01 00:00:00") == "2023-01-01T00:00:00"

    def test_normalizes_end_of_day_timestamp(self):
        assert normalize_disk_date("2023:12:31 23:59:59") == "2023-12-31T23:59:59"

    def test_strips_negative_timezone_offset(self):
        assert normalize_disk_date("2023:05:20 14:30:00-05:00") == "2023-05-20T14:30:00"

    def test_strips_positive_timezone_offset(self):
        assert normalize_disk_date("2023:05:20 14:30:00+02:00") == "2023-05-20T14:30:00"

    def test_strips_utc_z_marker(self):
        assert normalize_disk_date("2023:05:20 14:30:00Z") == "2023-05-20T14:30:00"

    def test_strips_fractional_timezone_offset(self):
        assert normalize_disk_date("2023:05:20 14:30:00+05:30") == "2023-05-20T14:30:00"

    def test_handles_dash_separators(self):
        assert normalize_disk_date("2023-05-20 14:30:00") == "2023-05-20T14:30:00"

    def test_handles_mixed_separators(self):
        assert normalize_disk_date("2023-05-20 14:30:00") == "2023-05-20T14:30:00"

    def test_trims_leading_whitespace(self):
        assert normalize_disk_date("  2023:05:20 14:30:00") == "2023-05-20T14:30:00"

    def test_trims_trailing_whitespace(self):
        assert normalize_disk_date("2023:05:20 14:30:00  ") == "2023-05-20T14:30:00"

    def test_trims_leading_and_trailing_whitespace(self):
        assert normalize_disk_date("  2023:05:20 14:30:00  ") == "2023-05-20T14:30:00"

    def test_returns_none_for_none(self):
        assert normalize_disk_date(None) is None

    def test_returns_none_for_empty_string(self):
        assert normalize_disk_date("") is None

    def test_returns_none_for_non_string(self):
        assert normalize_disk_date(12345) is None

    def test_returns_none_for_invalid_format(self):
        assert normalize_disk_date("invalid date") is None

    def test_returns_none_for_date_without_time(self):
        assert normalize_disk_date("2023:05:20") is None

    def test_returns_none_for_missing_date_components(self):
        assert normalize_disk_date("2023:05 14:30:00") is None

    def test_returns_none_for_boolean(self):
        assert normalize_disk_date(True) is None

    def test_handles_leap_year(self):
        assert normalize_disk_date("2024:02:29 12:00:00") == "2024-02-29T12:00:00"

    def test_handles_zero_padded_time(self):
        assert normalize_disk_date("2023:05:20 01:02:03") == "2023-05-20T01:02:03"

    def test_strips_subsecond_precision(self):
        assert normalize_disk_date("2023:05:20 14:30:00.123") == "2023-05-20T14:30:00"

    def test_strips_subseconds_and_timezone(self):
        assert normalize_disk_date("2024:09:02 20:14:59.925+02:00") == "2024-09-02T20:14:59"


class TestParsePhotoTakenTime:
    def test_formats_timestamp_1719935787(self):
        result = parse_photo_taken_time("1719935787")
        assert result["exif"] == "2024:07:02 15:56:27+00:00"
        assert result["iso"] == "2024-07-02T15:56:27"

    def test_formats_timestamp_1710899464(self):
        result = parse_photo_taken_time("1710899464")
        assert result["exif"] == "2024:03:20 01:51:04+00:00"
        assert result["iso"] == "2024-03-20T01:51:04"

    def test_formats_timestamp_1710994697(self):
        result = parse_photo_taken_time("1710994697")
        assert result["exif"] == "2024:03:21 04:18:17+00:00"
        assert result["iso"] == "2024-03-21T04:18:17"

    def test_formats_timestamp_1711192947(self):
        result = parse_photo_taken_time("1711192947")
        assert result["exif"] == "2024:03:23 11:22:27+00:00"
        assert result["iso"] == "2024-03-23T11:22:27"

    def test_formats_timestamp_1711016650(self):
        result = parse_photo_taken_time("1711016650")
        assert result["exif"] == "2024:03:21 10:24:10+00:00"
        assert result["iso"] == "2024-03-21T10:24:10"

    def test_pads_single_digit_month_and_day(self):
        result = parse_photo_taken_time("1704675601")
        assert result["exif"] == "2024:01:08 01:00:01+00:00"
        assert result["iso"] == "2024-01-08T01:00:01"

    def test_handles_midnight(self):
        result = parse_photo_taken_time("1704067200")
        assert result["exif"] == "2024:01:01 00:00:00+00:00"
        assert result["iso"] == "2024-01-01T00:00:00"

    def test_handles_end_of_day(self):
        result = parse_photo_taken_time("1704153599")
        assert result["exif"] == "2024:01:01 23:59:59+00:00"
        assert result["iso"] == "2024-01-01T23:59:59"

    def test_handles_epoch_zero(self):
        result = parse_photo_taken_time("0")
        assert result["exif"] == "1970:01:01 00:00:00+00:00"
        assert result["iso"] == "1970-01-01T00:00:00"

    def test_handles_old_1990_timestamp(self):
        result = parse_photo_taken_time("631152000")
        assert result["exif"] == "1990:01:01 00:00:00+00:00"
        assert result["iso"] == "1990-01-01T00:00:00"

    def test_raises_for_invalid_string(self):
        with pytest.raises(ValueError, match="Failed to parse photoTakenTime timestamp: invalid"):
            parse_photo_taken_time("invalid")

    def test_raises_for_empty_string(self):
        with pytest.raises(ValueError, match="Failed to parse photoTakenTime timestamp:"):
            parse_photo_taken_time("")

    def test_accepts_numeric_int(self):
        result = parse_photo_taken_time(1704067200)
        assert result["exif"] == "2024:01:01 00:00:00+00:00"
        assert result["iso"] == "2024-01-01T00:00:00"


class TestParseIsoDate:
    def test_parses_standard_iso_string(self):
        result = parse_iso_date("2024-03-15T14:30:45")
        assert result == {
            "year": 2024,
            "month": 3,
            "day": 15,
            "hour": 14,
            "minute": 30,
            "second": 45,
        }

    def test_returns_year_as_int(self):
        result = parse_iso_date("2024-01-01T00:00:00")
        assert isinstance(result["year"], int)
        assert result["year"] == 2024

    def test_returns_none_for_none(self):
        assert parse_iso_date(None) is None

    def test_returns_none_for_empty_string(self):
        assert parse_iso_date("") is None

    def test_returns_none_for_invalid_string(self):
        assert parse_iso_date("not a date") is None
