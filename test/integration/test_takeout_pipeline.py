"""
Integration tests for the takeout pipeline (scan → link → dedupe → reconcile → rename → apply).

Requires exiftool installed (`brew install exiftool`).
Uses real JPEG fixtures from test/fixtures/media/.

Ported from packages/core/test/integration/pipeline.test.js. Path expectations
use the no-month format: YYYY/yyyymmdd-hhmmss.ext (loose) and
YYYY/yyyymmdd - Album/yyyymmdd-hhmmss.ext (album).
"""

import json
import os
import shutil
from pathlib import Path

import pytest

from pixelkasten.core.exiftool import check_exiftool, read_metadata
from pixelkasten.pipeline import run_takeout_pipeline

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "media"

# EXIF tags used to verify pipeline writes.
VERIFY_TAGS = [
    "EXIF:DateTimeOriginal",
    "Composite:GPSLatitude",
    "Composite:GPSLongitude",
    "Composite:GPSAltitude",
]


# ---------------------------------------------------------------------------
# Skip all tests if exiftool is not installed.
# ---------------------------------------------------------------------------

try:
    check_exiftool()
    _has_exiftool = True
except RuntimeError:
    _has_exiftool = False

pytestmark = pytest.mark.skipif(
    not _has_exiftool,
    reason="exiftool not installed",
)


# ---------------------------------------------------------------------------
# Helper: build a Google Takeout directory structure.
# ---------------------------------------------------------------------------


def build_takeout(base_dir: Path, structure: dict) -> None:
    """
    Create a Google Takeout directory structure from a declarative spec.

    Args:
        base_dir: Root directory to create the structure in.
        structure: Dict mapping folder names to lists of entries.
            Each entry is either:
            - {"album": True} — creates metadata.json (marks folder as album)
            - {"media": str, "name": str, "sidecar": dict} — copies a fixture
              JPEG and creates a sidecar JSON file.

    Sidecar dict format:
        {"timestamp": str, "geo": {"latitude": float, "longitude": float, "altitude": float}}
    """
    for folder_name, entries in structure.items():
        folder_path = base_dir / folder_name
        folder_path.mkdir(parents=True, exist_ok=True)

        for entry in entries:
            if entry.get("album"):
                album_meta = {"title": folder_name, "description": ""}
                (folder_path / "metadata.json").write_text(json.dumps(album_meta))
            else:
                # Copy fixture JPEG to the target location.
                shutil.copy2(FIXTURES_DIR / entry["media"], folder_path / entry["name"])

                if entry.get("sidecar"):
                    sidecar = _build_sidecar(entry["name"], entry["sidecar"])
                    sidecar_path = (
                        folder_path / f"{entry['name']}.supplemental-metadata.json"
                    )
                    sidecar_path.write_text(json.dumps(sidecar))


def _build_sidecar(title: str, data: dict) -> dict:
    """Build a sidecar JSON object matching real Google Takeout structure."""
    geo = (
        {
            "latitude": data["geo"]["latitude"],
            "longitude": data["geo"]["longitude"],
            "altitude": data["geo"].get("altitude", 0),
            "latitudeSpan": 0.0,
            "longitudeSpan": 0.0,
        }
        if data.get("geo")
        else {
            "latitude": 0.0,
            "longitude": 0.0,
            "altitude": 0.0,
            "latitudeSpan": 0.0,
            "longitudeSpan": 0.0,
        }
    )

    photo_taken_time = {"timestamp": data["timestamp"]} if data.get("timestamp") else {}

    result = {
        "title": title,
        "description": "",
        "photoTakenTime": photo_taken_time,
        "geoData": geo,
    }

    # Google Takeout duplicates geo into geoDataExif when GPS is present.
    if data.get("geo"):
        result["geoDataExif"] = geo

    return result


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestTakeoutPipeline:
    """Integration tests for the full takeout pipeline."""

    def test_embeds_and_preserves_metadata(self, tmp_path):
        """
        Pipeline should embed metadata from sidecar into files that lack it,
        preserve metadata that already exists on disk, and partially fill
        missing fields (e.g., add GPS to a file that has timestamp but no GPS).
        """
        source = tmp_path / "source"
        dest = tmp_path / "dest"
        source.mkdir()
        dest.mkdir()

        build_takeout(
            source,
            {
                "Photos from 2024": [
                    {
                        # No EXIF -- both timestamp and GPS should be written.
                        "media": "no-metadata.jpg",
                        "name": "IMG_001.jpg",
                        "sidecar": {
                            "timestamp": "1711016650",
                            "geo": {
                                "latitude": 51.5007,
                                "longitude": -0.1246,
                                "altitude": 11,
                            },
                        },
                    },
                    {
                        # Has timestamp + GPS -- pipeline should not overwrite.
                        "media": "with-datetime-and-gps.jpg",
                        "name": "IMG_002.jpg",
                        "sidecar": {
                            "timestamp": "1719935787",
                            "geo": {
                                "latitude": 48.8584,
                                "longitude": 2.2945,
                                "altitude": 35,
                            },
                        },
                    },
                    {
                        # Has timestamp but no GPS -- only GPS should be written.
                        "media": "with-datetime-no-gps.jpg",
                        "name": "IMG_003.jpg",
                        "sidecar": {
                            "timestamp": "1710899464",
                            "geo": {
                                "latitude": 35.6762,
                                "longitude": 139.6503,
                                "altitude": 40,
                            },
                        },
                    },
                ],
            },
        )

        manifest = run_takeout_pipeline(
            {
                "source": str(source),
                "destination": str(dest),
                "prefer": "album",
                "fuzzy": True,
                "skip_dedupe": True,
            }
        )

        # Expected output paths (no-month format).
        # 1711016650 -> 2024-03-21T10:24:10 -> 2024/20240321-102410.jpg
        # 1719935787 -> 2024-07-02T15:56:27 -> 2024/20240702-155627.jpg (disk timestamp used)
        # 1710899464 -> 2024-03-20T01:51:04 -> 2024/20240320-015104.jpg (disk timestamp used)
        no_exif_file = str(dest / "2024" / "20240321-102410.jpg")
        full_exif_file = str(dest / "2024" / "20240702-155627.jpg")
        partial_exif_file = str(dest / "2024" / "20240320-015104.jpg")

        disk_metadata = read_metadata(
            [no_exif_file, full_exif_file, partial_exif_file],
            VERIFY_TAGS,
        )

        # -- No-EXIF file: was empty, should now have timestamp + GPS from sidecar --

        no_exif_meta = disk_metadata.get(no_exif_file)
        assert no_exif_meta is not None, "No-EXIF file should exist in output"

        # Verify timestamp was written from sidecar.
        assert "2024:03:21" in no_exif_meta.get("EXIF:DateTimeOriginal", ""), (
            f"No-EXIF DateTimeOriginal should contain 2024:03:21, "
            f"got: {no_exif_meta.get('EXIF:DateTimeOriginal')}"
        )

        # Verify GPS was written from sidecar.
        assert abs(no_exif_meta["Composite:GPSLatitude"] - 51.5007) < 0.01
        assert abs(no_exif_meta["Composite:GPSLongitude"] - (-0.1246)) < 0.01

        # -- Full-EXIF file: already had metadata, should be unchanged --

        full_exif_meta = disk_metadata.get(full_exif_file)
        assert full_exif_meta is not None, "Full-EXIF file should exist in output"

        # Verify original timestamp was preserved (not overwritten by sidecar).
        assert "2024:07:02" in full_exif_meta.get("EXIF:DateTimeOriginal", ""), (
            f"Full-EXIF DateTimeOriginal should contain 2024:07:02, "
            f"got: {full_exif_meta.get('EXIF:DateTimeOriginal')}"
        )

        # Verify original GPS was preserved.
        assert abs(full_exif_meta["Composite:GPSLatitude"] - 48.8584) < 0.01
        assert abs(full_exif_meta["Composite:GPSLongitude"] - 2.2945) < 0.01

        # -- Partial-EXIF file: had timestamp but no GPS, should gain GPS from sidecar --

        partial_exif_meta = disk_metadata.get(partial_exif_file)
        assert partial_exif_meta is not None, "Partial-EXIF file should exist in output"

        # Verify original timestamp was preserved.
        assert "2024:03:20" in partial_exif_meta.get("EXIF:DateTimeOriginal", ""), (
            f"Partial-EXIF DateTimeOriginal should contain 2024:03:20, "
            f"got: {partial_exif_meta.get('EXIF:DateTimeOriginal')}"
        )

        # Verify GPS was written from sidecar.
        assert abs(partial_exif_meta["Composite:GPSLatitude"] - 35.6762) < 0.01
        assert abs(partial_exif_meta["Composite:GPSLongitude"] - 139.6503) < 0.01

        # -- Verify CSV report reflects per-file statuses --

        report_path = dest / "report.csv"
        assert report_path.exists(), "Report CSV should exist"
        report_content = report_path.read_text()
        report_rows = report_content.strip().split("\n")

        # No-EXIF file was embedded (metadata written from sidecar).
        no_exif_row = next(r for r in report_rows if "IMG_001.jpg" in r)
        assert "embedded" in no_exif_row, "No-EXIF file should have 'embedded' status"

        # Full-EXIF file was only copied (already had metadata).
        full_exif_row = next(r for r in report_rows if "IMG_002.jpg" in r)
        assert "copied" in full_exif_row, "Full-EXIF file should have 'copied' status"

        # Partial-EXIF file was embedded (GPS written from sidecar).
        partial_exif_row = next(r for r in report_rows if "IMG_003.jpg" in r)
        assert "embedded" in partial_exif_row, (
            "Partial-EXIF file should have 'embedded' status"
        )

    def test_deduplicates_album_over_loose(self, tmp_path):
        """
        When the same file exists in an album and as a loose copy, the album
        copy should be kept and the loose copy should be deduplicated.
        """
        source = tmp_path / "source"
        dest = tmp_path / "dest"
        source.mkdir()
        dest.mkdir()

        build_takeout(
            source,
            {
                "Vacation": [
                    {"album": True},
                    {
                        "media": "no-metadata.jpg",
                        "name": "IMG_001.jpg",
                        "sidecar": {
                            "timestamp": "1711016650",
                            "geo": {
                                "latitude": 51.5007,
                                "longitude": -0.1246,
                                "altitude": 11,
                            },
                        },
                    },
                ],
                "Photos from 2024": [
                    {
                        # Byte-identical copy -- same fixture, same hash.
                        "media": "no-metadata.jpg",
                        "name": "IMG_001.jpg",
                        "sidecar": {
                            "timestamp": "1711016650",
                            "geo": {
                                "latitude": 51.5007,
                                "longitude": -0.1246,
                                "altitude": 11,
                            },
                        },
                    },
                ],
            },
        )

        manifest = run_takeout_pipeline(
            {
                "source": str(source),
                "destination": str(dest),
                "prefer": "album",
                "fuzzy": True,
            }
        )

        # Album copy should be at: 2024/20240321 - Vacation/20240321-102410.jpg
        album_file = str(dest / "2024" / "20240321 - Vacation" / "20240321-102410.jpg")
        album_metadata = read_metadata([album_file], VERIFY_TAGS)
        album_file_meta = album_metadata.get(album_file)

        # Verify the album copy exists with embedded metadata.
        assert album_file_meta is not None, "Album copy should exist in output"
        assert "2024:03:21" in album_file_meta.get("EXIF:DateTimeOriginal", ""), (
            "Album copy should have timestamp embedded"
        )
        assert abs(album_file_meta["Composite:GPSLatitude"] - 51.5007) < 0.01

        # Verify the loose copy was removed by dedup (no JPEGs directly in year folder).
        year_folder = dest / "2024"
        loose_jpegs = [
            f for f in year_folder.iterdir() if f.is_file() and f.suffix == ".jpg"
        ]
        assert len(loose_jpegs) == 0, (
            "No loose JPEGs should exist directly in the year folder"
        )

        # Verify report: one embedded (album winner), one deleted (loose duplicate).
        report_content = (dest / "report.csv").read_text()
        report_rows = report_content.strip().split("\n")

        embedded_rows = [r for r in report_rows if "embedded" in r]
        deleted_rows = [r for r in report_rows if "deleted" in r]

        assert len(embedded_rows) == 1, "Exactly one file should be embedded"
        assert len(deleted_rows) == 1, "Exactly one file should be deleted"

    def test_copies_sidecar_when_skip_embed(self, tmp_path):
        """
        When skip_embed is set, the pipeline should copy the file without
        embedding metadata and copy the sidecar JSON alongside it.
        """
        source = tmp_path / "source"
        dest = tmp_path / "dest"
        source.mkdir()
        dest.mkdir()

        build_takeout(
            source,
            {
                "Photos from 2024": [
                    {
                        "media": "no-metadata.jpg",
                        "name": "IMG_001.jpg",
                        "sidecar": {
                            "timestamp": "1711016650",
                            "geo": {
                                "latitude": 51.5007,
                                "longitude": -0.1246,
                                "altitude": 11,
                            },
                        },
                    },
                ],
            },
        )

        manifest = run_takeout_pipeline(
            {
                "source": str(source),
                "destination": str(dest),
                "prefer": "album",
                "fuzzy": True,
                "skip_embed": True,
            }
        )

        # File should still be renamed based on sidecar timestamp.
        copied_file = str(dest / "2024" / "20240321-102410.jpg")
        disk_metadata = read_metadata([copied_file], VERIFY_TAGS)
        copied_file_meta = disk_metadata.get(copied_file)

        # Verify the file was copied.
        assert copied_file_meta is not None, "Copied file should exist"

        # Verify no timestamp was written (skip_embed prevents metadata embedding).
        assert copied_file_meta.get("EXIF:DateTimeOriginal") is None, (
            "DateTimeOriginal should not be present when skip_embed is set"
        )

        # Verify no GPS was written.
        assert copied_file_meta.get("Composite:GPSLatitude") is None, (
            "GPSLatitude should not be present when skip_embed is set"
        )

        # Verify the sidecar JSON was copied alongside the media file.
        copied_sidecar_path = dest / "2024" / "20240321-102410.jpg.json"
        assert copied_sidecar_path.exists(), (
            "Sidecar JSON should be copied alongside media"
        )

        copied_sidecar = json.loads(copied_sidecar_path.read_text())
        assert copied_sidecar["photoTakenTime"]["timestamp"] == "1711016650", (
            "Sidecar should be copied with correct content"
        )

    def test_dry_run_produces_no_output(self, tmp_path):
        """
        In dry-run mode, the pipeline should compute the plan but not write
        any files to the destination directory.
        """
        source = tmp_path / "source"
        dest = tmp_path / "dest"
        source.mkdir()
        dest.mkdir()

        build_takeout(
            source,
            {
                "Photos from 2024": [
                    {
                        "media": "no-metadata.jpg",
                        "name": "IMG_001.jpg",
                        "sidecar": {"timestamp": "1711016650"},
                    },
                ],
            },
        )

        manifest = run_takeout_pipeline(
            {
                "source": str(source),
                "destination": str(dest),
                "prefer": "album",
                "fuzzy": True,
                "dry_run": True,
            }
        )

        # Verify destination is empty (dry run writes nothing).
        dest_entries = list(dest.iterdir())
        assert len(dest_entries) == 0, "Destination should be empty in dry-run mode"

    def test_copies_unsupported_formats_without_embedding(self, tmp_path):
        """
        Unsupported formats (e.g., .avi) should be copied to the destination
        with their original filename but without any metadata embedding or
        renaming.
        """
        source = tmp_path / "source"
        dest = tmp_path / "dest"
        source.mkdir()
        dest.mkdir()

        build_takeout(
            source,
            {
                "Photos from 2024": [
                    {
                        "media": "no-metadata.jpg",
                        "name": "IMG_001.jpg",
                        "sidecar": {
                            "timestamp": "1711016650",
                            "geo": {
                                "latitude": 51.5007,
                                "longitude": -0.1246,
                                "altitude": 11,
                            },
                        },
                    },
                ],
            },
        )

        # Add an unsupported .avi file alongside the JPEG.
        avi_dir = source / "Photos from 2024"
        (avi_dir / "video.avi").write_bytes(b"dummy avi content for testing")
        avi_sidecar = {
            "title": "video.avi",
            "description": "",
            "photoTakenTime": {"timestamp": "1711016650", "formatted": "test"},
            "geoData": {
                "latitude": 0.0,
                "longitude": 0.0,
                "altitude": 0.0,
                "latitudeSpan": 0.0,
                "longitudeSpan": 0.0,
            },
        }
        (avi_dir / "video.avi.supplemental-metadata.json").write_text(
            json.dumps(avi_sidecar)
        )

        manifest = run_takeout_pipeline(
            {
                "source": str(source),
                "destination": str(dest),
                "prefer": "album",
                "fuzzy": True,
                "skip_dedupe": True,
            }
        )

        # Verify the JPEG was renamed and embedded as usual.
        jpeg_file = str(dest / "2024" / "20240321-102410.jpg")
        jpeg_metadata = read_metadata([jpeg_file], VERIFY_TAGS)
        assert jpeg_metadata.get(jpeg_file) is not None, (
            "JPEG should be in renamed output path"
        )

        # Verify the .avi was copied with its original filename (unsupported formats skip rename).
        avi_file = dest / "video.avi"
        assert avi_file.exists(), "AVI should be copied to destination"
        assert avi_file.read_bytes() == b"dummy avi content for testing", (
            "AVI should be copied with original content"
        )

        # Verify report shows the .avi as "copied".
        report_content = (dest / "report.csv").read_text()
        avi_row = next(
            (row for row in report_content.strip().split("\n") if "video.avi" in row),
            None,
        )
        assert avi_row is not None, "Report should mention the AVI file"
        assert "copied" in avi_row, "AVI should have 'copied' status in report"
