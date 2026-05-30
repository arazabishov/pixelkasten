"""
Integration test for the emit → propose → export chain when two members of
one logical group share an extension (e.g. an original HEIC + its edited
variant). This is the case the original ``_disambiguate`` ``_N`` suffix
was for; the new contract (records carry ``group_id``, filenames are
independently unique) must preserve group identity all the way through
to the export.

Three unit tests covered pieces of the chain before this — emit produced
``_N``, propose used filename stems, export bucketed by stem — and all
three happened to be on a happy path that bypassed the collision. This
test exercises the full chain and would have caught the silent bug those
unit tests missed.
"""

import json
import os
import shutil
from pathlib import Path

import pytest

from helpers import make_options, noop_progress
from pixelkasten.configuration import ExportOptions
from pixelkasten.commands.ingest import ingest
from pixelkasten.commands.export import export as run_export
from pixelkasten.commands.propose import propose
from pixelkasten.tools.exiftool import check_exiftool

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "media"


try:
    check_exiftool()
    _has_exiftool = True
except RuntimeError:
    _has_exiftool = False

pytestmark = pytest.mark.skipif(not _has_exiftool, reason="exiftool not installed")


def _build_takeout_with_edited_variant(source: Path) -> None:
    """A Takeout fixture with an original + an ``-edited`` variant sharing one sidecar.

    Both files are JPEGs in the same album folder; the link stage matches the
    edited variant to the same sidecar as the original (Google's truncated
    ``-edited`` suffix convention), so they end up in the same group.
    """
    folder = source / "Photos from 2024"
    folder.mkdir(parents=True)
    shutil.copy2(FIXTURES_DIR / "with-datetime-and-gps.jpg", folder / "IMG_001.jpg")
    shutil.copy2(FIXTURES_DIR / "with-datetime-no-gps.jpg", folder / "IMG_001-edited.jpg")
    sidecar = {
        "title": "IMG_001.jpg",
        "description": "",
        "photoTakenTime": {"timestamp": "1719935787"},  # 2024-07-02 15:56:27
        "geoData": {
            "latitude": 48.86,
            "longitude": 2.29,
            "altitude": 35,
            "latitudeSpan": 0.0,
            "longitudeSpan": 0.0,
        },
        "geoDataExif": {
            "latitude": 48.86,
            "longitude": 2.29,
            "altitude": 35,
            "latitudeSpan": 0.0,
            "longitudeSpan": 0.0,
        },
    }
    (folder / "IMG_001.jpg.supplemental-metadata.json").write_text(json.dumps(sidecar))


def _list_media(lib: Path) -> list[str]:
    """All emitted media filenames at the top of the working library."""
    media_exts = {".jpg", ".jpeg", ".heic", ".png", ".mp4", ".mov", ".mp"}
    return sorted(
        f
        for f in os.listdir(lib)
        if not f.startswith(".") and os.path.splitext(f)[1].lower() in media_exts
    )


def _read_record(lib: Path, media_name: str) -> dict:
    with open(lib / ".pixelkasten" / f"{media_name}.pk.json") as f:
        return json.load(f)


class TestSameExtensionGroupChain:
    """End-to-end: emit + propose + export with a same-extension collision."""

    def test_same_extension_group_propagates_through_propose_and_export(self, tmp_path):
        source = tmp_path / "source"
        lib = tmp_path / "lib"
        export_dir = tmp_path / "export"
        source.mkdir()
        lib.mkdir()
        _build_takeout_with_edited_variant(source)

        # 1. import -> working library with two .jpg files sharing a group_id
        ingest(
            make_options(source=str(source), destination=str(lib), skip_dedupe=True),
            progress=noop_progress,
        )

        media = _list_media(lib)
        # Verify both same-extension files landed in the working library
        assert len(media) == 2, f"expected 2 emitted files, got {media!r}"

        # Verify both records share the same group_id (the contract that
        # propose and export rely on)
        records = [_read_record(lib, name) for name in media]
        group_ids = {r["group_id"] for r in records}
        assert len(group_ids) == 1, (
            f"both members of the same Takeout group should share group_id, got {group_ids!r}"
        )
        # The shared group_id is a non-empty string
        (shared_group_id,) = group_ids
        assert shared_group_id

        # 2. propose on one member -> both records get proposed_album
        propose(str(lib / media[0]), "Paris weekend")
        records_after = [_read_record(lib, name) for name in media]
        # Verify propagation: both members carry the same proposed_album
        assert all(r.get("proposed_album") == "Paris weekend" for r in records_after), (
            f"propose should propagate to all group siblings; got {records_after!r}"
        )

        # 3. export -> both files land in the same album folder
        run_export(str(lib), str(export_dir), ExportOptions())

        exported_files: list[str] = []
        for dirpath, _dirs, fns in os.walk(str(export_dir)):
            for f in fns:
                exported_files.append(os.path.relpath(os.path.join(dirpath, f), str(export_dir)))

        # Verify both files live under the proposed album's folder
        album_files = [f for f in exported_files if "Paris weekend" in f]
        assert len(album_files) == 2, (
            f"both group members should land in the proposed album folder; got {exported_files!r}"
        )
