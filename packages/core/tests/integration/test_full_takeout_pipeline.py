"""
End-to-end integration test for the Takeout flow without an agent:
    init --from-takeout  →  apply --to <dst>

Verifies that the pure-pipeline path produces an organized export with
year/album folders and timestamped filenames. EXIF writes during init are
exercised; the export step copies (not moves) and leaves the working
library untouched.

Requires exiftool installed.
"""

import json
import os
import shutil
from pathlib import Path

import pytest

from helpers import make_options, noop_progress
from pixelkasten.configuration import ApplyOptions, Hooks
from pixelkasten.pipeline import run_pipeline
from pixelkasten.stages.export import apply_export
from pixelkasten.tools.exiftool import check_exiftool

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "media"


try:
    check_exiftool()
    _has_exiftool = True
except RuntimeError:
    _has_exiftool = False

pytestmark = pytest.mark.skipif(not _has_exiftool, reason="exiftool not installed")


def _build_takeout(source: Path, structure: dict) -> None:
    for folder_name, entries in structure.items():
        folder_path = source / folder_name
        folder_path.mkdir(parents=True, exist_ok=True)
        for entry in entries:
            if entry.get("album"):
                (folder_path / "metadata.json").write_text(
                    json.dumps({"title": folder_name, "description": ""})
                )
                continue
            shutil.copy2(FIXTURES_DIR / entry["media"], folder_path / entry["name"])
            sidecar = {
                "title": entry["name"],
                "description": "",
                "photoTakenTime": {"timestamp": entry["sidecar"]["timestamp"]},
                "geoData": {
                    "latitude": entry["sidecar"]["geo"]["latitude"],
                    "longitude": entry["sidecar"]["geo"]["longitude"],
                    "altitude": entry["sidecar"]["geo"].get("altitude", 0),
                    "latitudeSpan": 0.0,
                    "longitudeSpan": 0.0,
                },
                "geoDataExif": {
                    "latitude": entry["sidecar"]["geo"]["latitude"],
                    "longitude": entry["sidecar"]["geo"]["longitude"],
                    "altitude": entry["sidecar"]["geo"].get("altitude", 0),
                    "latitudeSpan": 0.0,
                    "longitudeSpan": 0.0,
                },
            }
            (folder_path / f"{entry['name']}.supplemental-metadata.json").write_text(
                json.dumps(sidecar)
            )


def _listing(root: str) -> list[str]:
    out: list[str] = []
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            out.append(os.path.relpath(os.path.join(dirpath, f), root))
    return sorted(out)


class TestFullTakeoutPipeline:
    def test_init_then_apply_produces_album_and_year_folders(self, tmp_path):
        source = tmp_path / "source"
        lib = tmp_path / "lib"
        export = tmp_path / "export"
        source.mkdir()
        lib.mkdir()

        _build_takeout(
            source,
            {
                "Vacation 2024": [
                    {"album": True},
                    {
                        "media": "no-metadata.jpg",
                        "name": "IMG_001.jpg",
                        "sidecar": {
                            "timestamp": "1711016650",  # 2024-03-21 10:24:10
                            "geo": {"latitude": 51.5, "longitude": -0.1},
                        },
                    },
                ],
                "Photos from 2024": [
                    {
                        "media": "with-datetime-and-gps.jpg",
                        "name": "IMG_LOOSE.jpg",
                        "sidecar": {
                            "timestamp": "1719935787",  # 2024-07-02 15:56:27
                            "geo": {"latitude": 48.86, "longitude": 2.29},
                        },
                    },
                ],
            },
        )

        run_pipeline(
            make_options(source=str(source), destination=str(lib)),
            hooks=Hooks(),
            progress=noop_progress,
        )

        apply_export(str(lib), str(export), ApplyOptions())

        files = _listing(str(export))
        # Album entry lands in the year/<YYYYMMDD>-<album>/ folder
        assert "2024/20240321-Vacation 2024/20240321-102410.jpg" in files
        # Loose entry lands in the year folder
        assert "2024/20240702-155627.jpg" in files
        # No Unsorted bucket created when every entry has a date
        assert all(not f.startswith("Unsorted/") for f in files)

    def test_working_library_is_untouched_after_apply(self, tmp_path):
        source = tmp_path / "source"
        lib = tmp_path / "lib"
        export = tmp_path / "export"
        source.mkdir()
        lib.mkdir()

        _build_takeout(
            source,
            {
                "Photos from 2024": [
                    {
                        "media": "no-metadata.jpg",
                        "name": "IMG_001.jpg",
                        "sidecar": {
                            "timestamp": "1711016650",
                            "geo": {"latitude": 51.5, "longitude": -0.1},
                        },
                    },
                ],
            },
        )

        run_pipeline(
            make_options(source=str(source), destination=str(lib)),
            hooks=Hooks(),
            progress=noop_progress,
        )
        before = _listing(str(lib))

        apply_export(str(lib), str(export), ApplyOptions())

        # Working library file layout is identical after the export
        assert _listing(str(lib)) == before
