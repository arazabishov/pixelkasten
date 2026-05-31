"""
Integration tests for `init --from-takeout`: scan → link → dedupe → reconcile → group → emit.

These run the full pipeline against a real tmp filesystem and verify the
working-library shape: GUID-named copies at the destination root and a
companion sidecar JSON under .pixelkasten/.

Requires exiftool installed (`brew install exiftool`).
"""

import json
import os
import shutil
from pathlib import Path

import pytest

from helpers import make_options, noop_progress
from pixelkasten.tools.exiftool import check_exiftool, read_metadata
from pixelkasten.commands.ingest import ingest

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "media"

VERIFY_TAGS = [
    "EXIF:DateTimeOriginal",
    "Composite:GPSLatitude",
    "Composite:GPSLongitude",
    "Composite:GPSAltitude",
]


try:
    check_exiftool()
    _has_exiftool = True
except RuntimeError:
    _has_exiftool = False

pytestmark = pytest.mark.skipif(
    not _has_exiftool,
    reason="exiftool not installed",
)


def build_takeout(base_dir: Path, structure: dict) -> None:
    """Create a Google Takeout directory structure from a declarative spec."""
    for folder_name, entries in structure.items():
        folder_path = base_dir / folder_name
        folder_path.mkdir(parents=True, exist_ok=True)

        for entry in entries:
            if entry.get("album"):
                album_meta = {"title": folder_name, "description": ""}
                (folder_path / "metadata.json").write_text(json.dumps(album_meta))
            else:
                shutil.copy2(FIXTURES_DIR / entry["media"], folder_path / entry["name"])

                if entry.get("sidecar"):
                    sidecar = _build_sidecar(entry["name"], entry["sidecar"])
                    sidecar_path = folder_path / f"{entry['name']}.supplemental-metadata.json"
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

    if data.get("geo"):
        result["geoDataExif"] = geo

    return result


def _by_source_basename(manifest) -> dict[str, str]:
    """Map source filename -> emitted destination path via entry.apply."""
    return {
        os.path.basename(e.media_path): e.apply.target_path
        for e in manifest
        if e.apply is not None and e.apply.target_path is not None
    }


def _read_pk_sidecar(dest_root: str, target_path: str) -> dict:
    pk_path = os.path.join(dest_root, ".pixelkasten", os.path.basename(target_path) + ".pk.json")
    with open(pk_path) as f:
        return json.load(f)


class TestInitTakeoutPipeline:
    """End-to-end behavior of `pixelkasten init --from-takeout`."""

    def test_writes_exif_and_pk_sidecars_for_takeout_input(self, tmp_path):
        """
        For Takeout input, pipeline writes EXIF into copies (when missing on
        disk) and emits a .pk.json sidecar with sidecar-derived dates and geo
        for every keeper.
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

        _run_result = ingest(
            make_options(source=str(source), destination=str(dest), skip_dedupe=True),
            progress=noop_progress,
        )
        manifest = _run_result.manifest

        by_src = _by_source_basename(manifest)

        # All three source files land in the working library
        assert set(by_src.keys()) == {"IMG_001.jpg", "IMG_002.jpg", "IMG_003.jpg"}

        # Each emitted path is flat at <dest>/<guid>.jpg
        for src, target in by_src.items():
            assert os.path.dirname(target) == str(dest), (
                f"{src} should be at the destination root, got {target}"
            )

        disk_metadata = read_metadata(list(by_src.values()), VERIFY_TAGS)

        # -- No-EXIF source: timestamp and GPS now present from sidecar --
        img1_meta = disk_metadata.get(by_src["IMG_001.jpg"])
        assert "2024:03:21" in img1_meta.get("EXIF:DateTimeOriginal", ""), (
            f"IMG_001 should have sidecar timestamp written; got {img1_meta.get('EXIF:DateTimeOriginal')}"
        )
        assert abs(img1_meta["Composite:GPSLatitude"] - 51.5007) < 0.01

        # -- Full-EXIF source: original timestamp preserved, not overwritten --
        img2_meta = disk_metadata.get(by_src["IMG_002.jpg"])
        assert "2024:07:02" in img2_meta.get("EXIF:DateTimeOriginal", "")
        assert abs(img2_meta["Composite:GPSLatitude"] - 48.8584) < 0.01

        # -- Partial-EXIF source: timestamp kept, GPS added from sidecar --
        img3_meta = disk_metadata.get(by_src["IMG_003.jpg"])
        assert "2024:03:20" in img3_meta.get("EXIF:DateTimeOriginal", "")
        assert abs(img3_meta["Composite:GPSLatitude"] - 35.6762) < 0.01

        # -- Every emitted file has a .pk.json sidecar with dates + geo --
        for src, target in by_src.items():
            sidecar = _read_pk_sidecar(str(dest), target)
            assert sidecar["dates"], f"{src} sidecar should have dates"
            assert sidecar["geo"] is not None, f"{src} sidecar should have geo"
            # Loose entries (Photos from YYYY) have album = null
            assert sidecar["album"] is None

    def test_dedupe_keeps_album_copy_when_loose_duplicate_exists(self, tmp_path):
        """
        When the same file exists in an album and as a loose copy, dedupe
        keeps the album one. Only the survivor is emitted; its sidecar
        records the album name.
        """
        source = tmp_path / "source"
        dest = tmp_path / "dest"
        source.mkdir()
        dest.mkdir()

        sidecar = {
            "timestamp": "1711016650",
            "geo": {"latitude": 51.5007, "longitude": -0.1246, "altitude": 11},
        }

        build_takeout(
            source,
            {
                "Vacation": [
                    {"album": True},
                    {"media": "no-metadata.jpg", "name": "IMG_001.jpg", "sidecar": sidecar},
                ],
                "Photos from 2024": [
                    {"media": "no-metadata.jpg", "name": "IMG_001.jpg", "sidecar": sidecar},
                ],
            },
        )

        _run_result = ingest(
            make_options(source=str(source), destination=str(dest)),
            progress=noop_progress,
        )
        manifest = _run_result.manifest

        emitted = [e for e in manifest if e.apply and e.apply.target_path]

        # Only one survivor copied
        assert len(emitted) == 1
        # Its sidecar records the album name (album-source winner)
        sidecar = _read_pk_sidecar(str(dest), emitted[0].apply.target_path)
        assert sidecar["album"] == "Vacation"

        # No stray .jpg files in the destination root beyond the survivor
        jpgs = [p for p in os.listdir(str(dest)) if p.endswith(".jpg")]
        assert len(jpgs) == 1

    def test_skip_metadata_write_suppresses_exif_but_still_writes_pk_sidecar(self, tmp_path):
        """
        With --skip-metadata-write the file is copied and a .pk.json sidecar
        is still written (using dates read from the Takeout JSON), but no
        EXIF is written into the copy.
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

        _run_result = ingest(
            make_options(source=str(source), destination=str(dest), skip_metadata_write=True),
            progress=noop_progress,
        )
        manifest = _run_result.manifest

        target = _by_source_basename(manifest)["IMG_001.jpg"]
        disk = read_metadata([target], VERIFY_TAGS)[target]

        # File was copied
        assert os.path.exists(target)
        # But no EXIF was written into it
        assert disk.get("EXIF:DateTimeOriginal") is None
        assert disk.get("Composite:GPSLatitude") is None

        # .pk.json sidecar still records dates and geo from the Takeout JSON
        sidecar = _read_pk_sidecar(str(dest), target)
        assert sidecar["dates"], "Record should contain the date from the Takeout JSON"
        assert sidecar["geo"] is not None

    def test_dry_run_writes_nothing(self, tmp_path):
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

        ingest(
            make_options(source=str(source), destination=str(dest), dry_run=True),
            progress=noop_progress,
        )

        # Dry-run leaves the destination untouched
        assert list(dest.iterdir()) == []

    def test_unsupported_formats_are_skipped_not_emitted(self, tmp_path):
        """
        Files without a metadata handler (e.g., .avi) are marked SKIPPED in
        reconcile and are not emitted to the working library.
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

        (source / "Photos from 2024" / "video.avi").write_bytes(b"dummy avi content")

        _run_result = ingest(
            make_options(source=str(source), destination=str(dest), skip_dedupe=True),
            progress=noop_progress,
        )
        manifest = _run_result.manifest

        # The .avi never lands in the working library
        emitted_basenames = {
            os.path.basename(p) for p in os.listdir(str(dest)) if not p.startswith(".")
        }
        avi_files = {p for p in emitted_basenames if p.endswith(".avi")}
        assert avi_files == set()

        # And the manifest entry for it records SKIPPED on apply
        avi_entry = next(e for e in manifest if e.media_path.endswith("video.avi"))
        assert avi_entry.apply is not None
        from pixelkasten.types import Status as _Status

        assert avi_entry.apply.status == _Status.SKIPPED

        # The supported JPEG was emitted normally
        by_src = _by_source_basename(manifest)
        assert "IMG_001.jpg" in by_src
        assert os.path.exists(by_src["IMG_001.jpg"])
