"""
End-to-end integration test for the archive flow without an agent:
    import --from-archive  →  export --to <dst>

Archive mode has no Google Takeout JSON sidecars, but subfolder names
under the source root propagate as ``album``. Files at the source root
stay loose (album=null) and end up in date-named year folders; files in
subfolders end up in ``<YYYY>/<YYYYMMDD>-<folder>/`` album folders.
"""

import os
import shutil
from pathlib import Path

import pytest

from helpers import make_options, noop_progress
from pixelkasten.configuration import ExportOptions
from pixelkasten.commands.ingest import ingest
from pixelkasten.commands.export import export as run_export
from pixelkasten.tools.exiftool import check_exiftool

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "media"


try:
    check_exiftool()
    _has_exiftool = True
except RuntimeError:
    _has_exiftool = False

pytestmark = pytest.mark.skipif(not _has_exiftool, reason="exiftool not installed")


def _listing(root: str) -> list[str]:
    out: list[str] = []
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            out.append(os.path.relpath(os.path.join(dirpath, f), root))
    return sorted(out)


class TestFullArchivePipeline:
    def test_root_level_archive_file_exports_to_year_folder(self, tmp_path):
        source = tmp_path / "source"
        lib = tmp_path / "lib"
        export = tmp_path / "export"
        source.mkdir()
        lib.mkdir()

        # File at the source root -> loose; reconcile pulls its EXIF date;
        # export routes it to a year folder (no album subdirectory).
        shutil.copy2(FIXTURES_DIR / "with-datetime-and-gps.jpg", source / "with_exif.jpg")

        ingest(
            make_options(
                source=str(source),
                destination=str(lib),
                mode="archive",
                skip_dedupe=True,
            ),
            progress=noop_progress,
        )

        run_export(str(lib), str(export), ExportOptions())

        files = _listing(str(export))

        # Lands in a plain year folder, not an album subfolder
        year_dir = os.path.join("2024", "")
        assert any(f.startswith(year_dir) and "-" not in os.path.dirname(f) for f in files)

    def test_subfolder_archive_file_exports_to_album_folder(self, tmp_path):
        source = tmp_path / "source"
        lib = tmp_path / "lib"
        export = tmp_path / "export"
        source.mkdir()
        lib.mkdir()

        # File in a subfolder -> the folder name propagates as album;
        # export routes it to `<YYYY>/<YYYYMMDD>-<folder>/`.
        (source / "Wedding").mkdir()
        shutil.copy2(
            FIXTURES_DIR / "with-datetime-and-gps.jpg",
            source / "Wedding" / "photo.jpg",
        )

        ingest(
            make_options(
                source=str(source),
                destination=str(lib),
                mode="archive",
                skip_dedupe=True,
            ),
            progress=noop_progress,
        )

        run_export(str(lib), str(export), ExportOptions())

        files = _listing(str(export))

        # Lands under an album folder named after the source subfolder
        year_dir = os.path.join("2024", "")
        assert any(
            f.startswith(year_dir) and os.path.dirname(f).endswith("-Wedding") for f in files
        )
