"""
Integration tests for EXIF reading and reverse geocoding.

Requires exiftool installed (`brew install exiftool`).
Uses real JPEG fixtures from the Node.js test suite.
"""

from pathlib import Path
import pytest

from pixelkasten.exif import (
    check_exiftool,
    read_exif,
    reverse_geocode,
)

# Test fixtures: real JPEGs with stamped metadata.
FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "media"


@pytest.fixture
def fixture_paths():
    """Returns a dict of fixture name → Path for each test JPEG."""
    return {
        "no_metadata": FIXTURES_DIR / "no-metadata.jpg",
        "datetime_and_gps": FIXTURES_DIR / "with-datetime-and-gps.jpg",
        "datetime_no_gps": FIXTURES_DIR / "with-datetime-no-gps.jpg",
        "gps_no_datetime": FIXTURES_DIR / "with-gps-no-datetime.jpg",
    }


class TestCheckExiftool:
    def test_does_not_raise_when_installed(self):
        # Should not raise — exiftool is a prerequisite for integration tests.
        check_exiftool()


class TestReadExif:
    def test_reads_timestamp_from_jpeg(self, fixture_paths):
        result = read_exif([fixture_paths["datetime_and_gps"]])

        key = str(fixture_paths["datetime_and_gps"])
        exif = result[key]

        # Fixture has DateTimeOriginal="2024:07:02 15:56:27".
        assert exif["timestamp"] is not None
        assert exif["timestamp"].startswith("2024-07-02T15:56:27")

    def test_reads_gps_from_jpeg(self, fixture_paths):
        result = read_exif([fixture_paths["datetime_and_gps"]])

        key = str(fixture_paths["datetime_and_gps"])
        exif = result[key]

        # Fixture has GPS at Eiffel Tower (48.8584, 2.2945).
        assert exif["gps"] is not None
        assert abs(exif["gps"]["latitude"] - 48.8584) < 0.01
        assert abs(exif["gps"]["longitude"] - 2.2945) < 0.01

    def test_returns_none_gps_when_no_gps_tags(self, fixture_paths):
        result = read_exif([fixture_paths["datetime_no_gps"]])

        key = str(fixture_paths["datetime_no_gps"])
        exif = result[key]

        # Has timestamp but no GPS.
        assert exif["timestamp"] is not None
        assert exif["gps"] is None

    def test_returns_none_timestamp_when_no_datetime_tags(self, fixture_paths):
        result = read_exif([fixture_paths["gps_no_datetime"]])

        key = str(fixture_paths["gps_no_datetime"])
        exif = result[key]

        # Has GPS but no timestamp.
        assert exif["timestamp"] is None
        assert exif["gps"] is not None

    def test_returns_all_none_for_no_metadata(self, fixture_paths):
        result = read_exif([fixture_paths["no_metadata"]])

        key = str(fixture_paths["no_metadata"])
        exif = result[key]

        assert exif["timestamp"] is None
        assert exif["gps"] is None
        assert exif["camera"] is None

    def test_batch_reads_multiple_files(self, fixture_paths):
        all_paths = list(fixture_paths.values())

        result = read_exif(all_paths)

        # Should have one result per file.
        assert len(result) == 4


class TestReverseGeocode:
    def test_resolves_gps_to_location(self, fixture_paths):
        # First read EXIF to get GPS data.
        result = read_exif([fixture_paths["datetime_and_gps"]])

        locations = reverse_geocode(result)

        key = str(fixture_paths["datetime_and_gps"])
        assert key in locations

        loc = locations[key]
        # Eiffel Tower GPS should resolve to somewhere in Ile-de-France, France.
        assert loc["country"] == "FR"
        assert "Ile-de-France" in loc["region"]

    def test_skips_entries_without_gps(self, fixture_paths):
        result = read_exif([fixture_paths["datetime_no_gps"]])

        locations = reverse_geocode(result)

        # No GPS → no location.
        assert len(locations) == 0
