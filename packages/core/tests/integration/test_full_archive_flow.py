"""
End-to-end integration test for the archive flow without an agent:
    init --from-archive  →  apply --to <dst>

A flat archive has no JSON sidecars, so every export sidecar has album=null
and the export ends up in date folders (or Unsorted/ for files without a
parseable date).
"""

import os
import shutil
from pathlib import Path

import pytest

from helpers import make_options, noop_progress
from pixelkasten.configuration import ExportOptions, Hooks
from pixelkasten.commands.import_.run import run_import
from pixelkasten.commands.export import export as run_export
from pixelkasten.utils.exiftool import check_exiftool

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
    def test_archive_init_then_apply_produces_date_folders(self, tmp_path):
        source = tmp_path / "source"
        lib = tmp_path / "lib"
        export = tmp_path / "export"
        source.mkdir()
        lib.mkdir()

        # File with on-disk EXIF -> emit picks up its date during reconcile;
        # apply routes it to a year folder.
        shutil.copy2(FIXTURES_DIR / "with-datetime-and-gps.jpg", source / "with_exif.jpg")

        run_import(
            make_options(
                source=str(source),
                destination=str(lib),
                mode="archive",
                skip_dedupe=True,
            ),
            hooks=Hooks(),
            progress=noop_progress,
        )

        run_export(str(lib), str(export), ExportOptions())

        files = _listing(str(export))
        # The file with EXIF dates lands in the year folder
        assert any(f.startswith("2024/") and f.endswith(".jpg") for f in files)
        # Archive mode never produces an album folder (album field is always null)
        assert all("-" not in os.path.dirname(f) or f.startswith("Unsorted/") for f in files)
