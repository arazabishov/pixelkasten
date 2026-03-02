"""
Tests for the handlers module — ported from packages/core/test/handlers/.

Tests run end-to-end (no mocking of normalize_disk_date) since the
functions are pure and fast. Test expectations use normalized ISO strings.
"""

import pytest

from pixelkasten.core.handlers import (
    ExifHandler,
    QuickTimeHandler,
    all_known_media_extensions,
    exif_handler,
    handlers,
    parse_composite_geo,
    quicktime_handler,
    supported_extensions,
    unsupported_media_extensions,
)


# ---------------------------------------------------------------------------
# parse_composite_geo
# ---------------------------------------------------------------------------


class TestParseCompositeGeo:
    def test_returns_geo_when_lat_and_lon_present(self):
        raw = {
            "Composite:GPSLatitude": 40.7128,
            "Composite:GPSLongitude": -74.006,
            "Composite:GPSAltitude": 10,
        }

        result = parse_composite_geo(raw)

        assert result == {"latitude": 40.7128, "longitude": -74.006, "altitude": 10}

    def test_returns_none_when_lat_missing(self):
        raw = {"Composite:GPSLongitude": -74.006}

        assert parse_composite_geo(raw) is None

    def test_returns_none_when_lon_missing(self):
        raw = {"Composite:GPSLatitude": 40.7128}

        assert parse_composite_geo(raw) is None

    def test_zero_is_valid_coordinate(self):
        # 0 is a valid coordinate (equator/prime meridian) — unlike sidecar
        raw = {
            "Composite:GPSLatitude": 0,
            "Composite:GPSLongitude": 0,
        }

        result = parse_composite_geo(raw)

        assert result is not None
        assert result["latitude"] == 0
        assert result["longitude"] == 0

    def test_includes_altitude_when_present(self):
        raw = {
            "Composite:GPSLatitude": 40.7128,
            "Composite:GPSLongitude": -74.006,
            "Composite:GPSAltitude": 10,
        }

        assert parse_composite_geo(raw)["altitude"] == 10

    def test_altitude_is_none_when_absent(self):
        raw = {
            "Composite:GPSLatitude": 40.7128,
            "Composite:GPSLongitude": -74.006,
        }

        assert parse_composite_geo(raw)["altitude"] is None


# ---------------------------------------------------------------------------
# ExifHandler
# ---------------------------------------------------------------------------


class TestExifHandler:
    # --- parse ---

    def test_extracts_timestamp_from_datetime_original(self):
        result = exif_handler.parse({
            "EXIF:DateTimeOriginal": "2023:05:20 14:30:00",
        })

        assert result.timestamp == "2023-05-20T14:30:00"

    def test_extracts_and_normalizes_all_dates(self):
        result = exif_handler.parse({
            "EXIF:DateTimeOriginal": "2023:05:20 14:30:00",
            "EXIF:CreateDate": "2023:05:20 14:30:01",
            "Composite:GPSDateTime": "2023:05:20 14:30:02",
            "EXIF:ModifyDate": "2023:05:20 14:30:03",
            "File:FileCreateDate": "2023:05:20 14:30:04",
            "File:FileModifyDate": "2023:05:20 14:30:05",
        })

        assert len(result.dates) == 6

        # Dates are in priority order and normalized
        assert result.dates == [
            "2023-05-20T14:30:00",
            "2023-05-20T14:30:01",
            "2023-05-20T14:30:02",
            "2023-05-20T14:30:03",
            "2023-05-20T14:30:04",
            "2023-05-20T14:30:05",
        ]

    def test_filters_out_none_dates(self):
        result = exif_handler.parse({
            "EXIF:DateTimeOriginal": "2023:05:20 14:30:00",
            "EXIF:CreateDate": "invalid",
            "EXIF:ModifyDate": "2023:05:20 14:30:03",
        })

        # Only valid dates included
        assert len(result.dates) == 2
        assert result.dates == ["2023-05-20T14:30:00", "2023-05-20T14:30:03"]

    def test_returns_none_timestamp_when_empty(self):
        result = exif_handler.parse({})

        assert result.timestamp is None
        assert result.dates == []

    def test_extracts_geo_data(self):
        result = exif_handler.parse({
            "Composite:GPSLatitude": 40.7128,
            "Composite:GPSLongitude": -74.006,
            "Composite:GPSAltitude": 10,
        })

        assert result.geo == {
            "latitude": 40.7128,
            "longitude": -74.006,
            "altitude": 10,
        }

    def test_returns_none_geo_when_absent(self):
        result = exif_handler.parse({
            "EXIF:DateTimeOriginal": "2023:05:20 14:30:00",
        })

        assert result.geo is None

    # --- timestamp ---

    def test_returns_subsec_datetime_original_tag(self):
        result = exif_handler.timestamp("2023:05:20 14:30:00+00:00")

        assert result == ["SubSecDateTimeOriginal=2023:05:20 14:30:00+00:00"]

    # --- geo ---

    def test_returns_all_gps_tags(self):
        result = exif_handler.geo({
            "latitude": 40.7128,
            "longitude": -74.006,
            "altitude": 10,
        })

        assert len(result) == 4
        assert result[0] == "Composite:GPSLatitude=40.7128"
        assert result[1] == "Composite:GPSLongitude=-74.006"
        assert result[2] == "GPSAltitude=10"
        assert result[3] == "GPSAltitudeRef=10"

    def test_handles_negative_altitude(self):
        result = exif_handler.geo({
            "latitude": 40.7128,
            "longitude": -74.006,
            "altitude": -5,
        })

        assert result[2] == "GPSAltitude=-5"
        assert result[3] == "GPSAltitudeRef=-5"

    # --- readTags ---

    def test_includes_exif_date_tags(self):
        tags = exif_handler.read_tags

        assert "EXIF:DateTimeOriginal" in tags
        assert "EXIF:CreateDate" in tags
        assert "EXIF:ModifyDate" in tags
        assert "Composite:GPSDateTime" in tags
        assert "File:FileCreateDate" in tags
        assert "File:FileModifyDate" in tags

    def test_includes_composite_geo_tags(self):
        tags = exif_handler.read_tags

        assert "Composite:GPSAltitude" in tags
        assert "Composite:GPSLatitude" in tags
        assert "Composite:GPSLongitude" in tags


# ---------------------------------------------------------------------------
# QuickTimeHandler
# ---------------------------------------------------------------------------


class TestQuickTimeHandler:
    # --- parse ---

    def test_extracts_timestamp_from_creation_date(self):
        result = quicktime_handler.parse({
            "QuickTime:CreationDate": "2024:03:15 10:30:00",
        })

        assert result.timestamp == "2024-03-15T10:30:00"

    def test_extracts_and_normalizes_all_dates(self):
        result = quicktime_handler.parse({
            "QuickTime:CreationDate": "2024:03:15 10:30:00",
            "QuickTime:CreateDate": "2024:03:15 10:30:01",
            "QuickTime:GPSDateTime": "2024:03:15 10:30:02",
            "QuickTime:ModifyDate": "2024:03:15 10:30:03",
            "File:FileCreateDate": "2024:03:15 10:30:04+02:00",
            "File:FileModifyDate": "2024:03:15 10:30:05+02:00",
        })

        assert len(result.dates) == 6

        # Dates normalized (timezone stripped from File: tags)
        assert result.dates == [
            "2024-03-15T10:30:00",
            "2024-03-15T10:30:01",
            "2024-03-15T10:30:02",
            "2024-03-15T10:30:03",
            "2024-03-15T10:30:04",
            "2024-03-15T10:30:05",
        ]

    def test_filters_out_none_dates(self):
        result = quicktime_handler.parse({
            "QuickTime:CreationDate": "2024:03:15 10:30:00",
            "QuickTime:CreateDate": "invalid",
            "QuickTime:ModifyDate": "2024:03:15 10:30:03",
        })

        assert len(result.dates) == 2
        assert result.dates == ["2024-03-15T10:30:00", "2024-03-15T10:30:03"]

    def test_returns_none_timestamp_when_empty(self):
        result = quicktime_handler.parse({})

        assert result.timestamp is None
        assert result.dates == []

    def test_extracts_geo_data(self):
        result = quicktime_handler.parse({
            "Composite:GPSLatitude": 37.7749,
            "Composite:GPSLongitude": -122.4194,
            "Composite:GPSAltitude": 50,
        })

        assert result.geo == {
            "latitude": 37.7749,
            "longitude": -122.4194,
            "altitude": 50,
        }

    def test_returns_none_geo_when_absent(self):
        result = quicktime_handler.parse({
            "QuickTime:CreationDate": "2024:03:15 10:30:00",
        })

        assert result.geo is None

    # --- timestamp ---

    def test_returns_creation_date_tag(self):
        result = quicktime_handler.timestamp("2024:03:15 10:30:00+00:00")

        assert result == ["CreationDate=2024:03:15 10:30:00+00:00"]

    # --- geo ---

    def test_returns_gps_coordinates_tag(self):
        result = quicktime_handler.geo({
            "latitude": 37.7749,
            "longitude": -122.4194,
            "altitude": 50,
        })

        assert len(result) == 1
        assert result[0] == "Keys:GPSCoordinates=37.7749, -122.4194, 50"

    def test_handles_negative_coordinates(self):
        result = quicktime_handler.geo({
            "latitude": -33.8688,
            "longitude": 151.2093,
            "altitude": -10,
        })

        assert result[0] == "Keys:GPSCoordinates=-33.8688, 151.2093, -10"

    # --- readTags ---

    def test_includes_quicktime_date_tags(self):
        tags = quicktime_handler.read_tags

        assert "QuickTime:CreationDate" in tags
        assert "QuickTime:CreateDate" in tags
        assert "QuickTime:ModifyDate" in tags
        assert "File:FileCreateDate" in tags
        assert "File:FileModifyDate" in tags

    def test_includes_composite_geo_tags(self):
        tags = quicktime_handler.read_tags

        assert "Composite:GPSAltitude" in tags
        assert "Composite:GPSLatitude" in tags
        assert "Composite:GPSLongitude" in tags


# ---------------------------------------------------------------------------
# Handler registry
# ---------------------------------------------------------------------------


class TestHandlerRegistry:
    def test_jpg_maps_to_exif_handler(self):
        assert handlers[".jpg"] is exif_handler
        assert handlers[".jpeg"] is exif_handler
        assert handlers[".heic"] is exif_handler
        assert handlers[".png"] is exif_handler

    def test_mp4_maps_to_quicktime_handler(self):
        assert handlers[".mp4"] is quicktime_handler
        assert handlers[".mov"] is quicktime_handler

    def test_mp_maps_to_exif_handler(self):
        assert handlers[".mp"] is exif_handler

    def test_supported_extensions_includes_all_handler_keys(self):
        assert supported_extensions == set(handlers.keys())

    def test_unsupported_extensions_are_not_in_handler_map(self):
        for ext in unsupported_media_extensions:
            assert ext not in handlers

    def test_all_known_is_union_of_supported_and_unsupported(self):
        assert all_known_media_extensions == supported_extensions | unsupported_media_extensions
