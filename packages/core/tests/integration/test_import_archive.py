"""
Integration tests for `init --from-archive`: a flat archive of media files
without JSON sidecars.

The working library shape matches Takeout mode (flat GUID-named files +
.pixelkasten/ sidecars), but every sidecar has album=null and no EXIF is
written into copies. Dedupe breaks ties by lex-smallest media_path.

Requires exiftool installed (`brew install exiftool`).
"""

import json
import os
import shutil
from pathlib import Path

import pytest

from helpers import make_options, noop_progress
from pixelkasten.utils.exiftool import check_exiftool, read_metadata
from pixelkasten.commands.ingest import ingest

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "media"

VERIFY_TAGS = [
    "EXIF:DateTimeOriginal",
    "Composite:GPSLatitude",
    "Composite:GPSLongitude",
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


def _by_source_basename(manifest) -> dict[str, str]:
    return {
        os.path.basename(e.media_path): e.apply.target_path
        for e in manifest
        if e.apply is not None and e.apply.target_path is not None
    }


def _read_pk_sidecar(dest_root: str, target_path: str) -> dict:
    pk_path = os.path.join(dest_root, ".pixelkasten", os.path.basename(target_path) + ".pk.json")
    with open(pk_path) as f:
        return json.load(f)


class TestInitArchivePipeline:
    """End-to-end behavior of `pixelkasten init --from-archive`."""

    def test_emits_working_library_with_null_album(self, tmp_path):
        """
        Archive mode emits the same flat GUID layout as Takeout mode, but
        every .pk.json sidecar has album=null and no EXIF is written into
        the copies.
        """
        source = tmp_path / "source"
        dest = tmp_path / "dest"
        source.mkdir()
        dest.mkdir()

        # Mixed: one with full EXIF, one without
        shutil.copy2(FIXTURES_DIR / "with-datetime-and-gps.jpg", source / "with_exif.jpg")
        shutil.copy2(FIXTURES_DIR / "no-metadata.jpg", source / "no_exif.jpg")

        _run_result = ingest(
            make_options(
                source=str(source),
                destination=str(dest),
                mode="archive",
                skip_dedupe=True,
            ),
            progress=noop_progress,
        )
        manifest = _run_result.manifest

        by_src = _by_source_basename(manifest)
        assert set(by_src.keys()) == {"with_exif.jpg", "no_exif.jpg"}

        # Every sidecar has album=null in archive mode
        for src, target in by_src.items():
            sidecar = _read_pk_sidecar(str(dest), target)
            assert sidecar["album"] is None, f"{src} sidecar should have album=null"

        # File with on-disk EXIF preserves it; reconcile pulled dates into the sidecar
        with_exif_target = by_src["with_exif.jpg"]
        with_exif_sidecar = _read_pk_sidecar(str(dest), with_exif_target)
        assert with_exif_sidecar["dates"], "with_exif.jpg sidecar should record on-disk dates"
        assert with_exif_sidecar["geo"] is not None

        # File without on-disk EXIF has no geo in archive mode — there's no
        # sidecar to fall back to.
        no_exif_target = by_src["no_exif.jpg"]
        no_exif_sidecar = _read_pk_sidecar(str(dest), no_exif_target)
        assert no_exif_sidecar["geo"] is None

    def test_no_exif_is_written_into_copies(self, tmp_path):
        """
        Archive mode never queues write_tags because there's no sidecar
        source. A file that started without on-disk EXIF still has no EXIF
        in the destination copy.
        """
        source = tmp_path / "source"
        dest = tmp_path / "dest"
        source.mkdir()
        dest.mkdir()

        shutil.copy2(FIXTURES_DIR / "no-metadata.jpg", source / "naked.jpg")

        _run_result = ingest(
            make_options(
                source=str(source),
                destination=str(dest),
                mode="archive",
                skip_dedupe=True,
            ),
            progress=noop_progress,
        )
        manifest = _run_result.manifest

        target = _by_source_basename(manifest)["naked.jpg"]
        disk = read_metadata([target], VERIFY_TAGS)[target]

        # No EXIF was written — archive mode has nothing to write
        assert disk.get("EXIF:DateTimeOriginal") is None
        assert disk.get("Composite:GPSLatitude") is None

    def test_dedupe_picks_lex_smallest_source_path(self, tmp_path):
        """
        With two byte-identical files in archive mode, the one with the
        lex-smallest source path is kept; the other is deleted.
        """
        source = tmp_path / "source"
        dest = tmp_path / "dest"
        source.mkdir()
        dest.mkdir()

        # Two copies of the same file, names chosen so we know the winner
        shutil.copy2(FIXTURES_DIR / "no-metadata.jpg", source / "zebra.jpg")
        shutil.copy2(FIXTURES_DIR / "no-metadata.jpg", source / "alpha.jpg")

        _run_result = ingest(
            make_options(source=str(source), destination=str(dest), mode="archive"),
            progress=noop_progress,
        )
        manifest = _run_result.manifest

        survivors = [
            os.path.basename(e.media_path)
            for e in manifest
            if e.apply is not None and e.apply.target_path is not None
        ]
        # alpha.jpg wins on lex ordering
        assert survivors == ["alpha.jpg"]

    def test_groups_archive_live_photo_siblings_by_stem(self, tmp_path):
        """
        Two files sharing a base name (e.g., IMG_001.jpg and IMG_001.mov)
        in the same directory share a group_id and emit with the same stem.
        """
        source = tmp_path / "source"
        dest = tmp_path / "dest"
        source.mkdir()
        dest.mkdir()

        # Same stem, different extension — Live Photo-style sibling pair
        shutil.copy2(FIXTURES_DIR / "no-metadata.jpg", source / "IMG_001.jpg")
        # A non-real video, but emit doesn't care about content
        (source / "IMG_001.mov").write_bytes(b"fake-mov")

        _run_result = ingest(
            make_options(source=str(source), destination=str(dest), mode="archive"),
            progress=noop_progress,
        )
        manifest = _run_result.manifest

        # Both members get a target path; the .jpg is emitted (has handler);
        # the .mov is unsupported (no handler) and marked SKIPPED — but they
        # still share a group_id from the group stage.
        by_src = {os.path.basename(e.media_path): e for e in manifest}
        assert by_src["IMG_001.jpg"].group_id == by_src["IMG_001.mov"].group_id
