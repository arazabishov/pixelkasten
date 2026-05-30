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
from pixelkasten.tools.exiftool import check_exiftool, read_metadata
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

    def test_root_level_archive_files_have_null_album(self, tmp_path):
        """
        Archive mode emits the same flat GUID layout as Takeout mode.
        Files at the source root have ``album=null`` (loose), no EXIF is
        written into the copies, but on-disk EXIF still lands in the
        record's ``dates``/``geo`` via reconcile.
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

        # Files at the source root are loose -> album=null
        for src, target in by_src.items():
            sidecar = _read_pk_sidecar(str(dest), target)
            assert sidecar["album"] is None, f"{src} record should have album=null"

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

    def test_dedupe_keeps_album_copy_when_loose_duplicate_exists(self, tmp_path):
        """
        Archive subfolders are treated as albums; the album/loose split
        makes --prefer meaningful in archive mode too. A file that appears
        both in an album folder and loose at the source root collapses to
        just the album copy (default --prefer=album).
        """
        source = tmp_path / "source"
        dest = tmp_path / "dest"
        source.mkdir()
        dest.mkdir()

        # Same file: one at the source root (loose), one inside an album folder.
        (source / "Trip").mkdir()
        shutil.copy2(FIXTURES_DIR / "no-metadata.jpg", source / "loose.jpg")
        shutil.copy2(FIXTURES_DIR / "no-metadata.jpg", source / "Trip" / "album.jpg")

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
        # The album copy wins; the loose copy is dropped
        assert survivors == ["album.jpg"]

    def test_subfolder_files_inherit_folder_name_as_album(self, tmp_path):
        """
        Archive subfolders propagate as the record's ``album`` field. A
        file at ``<source>/Wedding/photo.jpg`` lands with album="Wedding";
        a file at the source root lands with album=null.
        """
        source = tmp_path / "source"
        dest = tmp_path / "dest"
        source.mkdir()
        dest.mkdir()

        (source / "Wedding").mkdir()
        shutil.copy2(FIXTURES_DIR / "no-metadata.jpg", source / "Wedding" / "in_album.jpg")
        shutil.copy2(FIXTURES_DIR / "no-metadata.jpg", source / "at_root.jpg")

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
        # Subfolder file gets the folder name as album
        wedding_record = _read_pk_sidecar(str(dest), by_src["in_album.jpg"])
        assert wedding_record["album"] == "Wedding"
        # Root-level file stays loose
        root_record = _read_pk_sidecar(str(dest), by_src["at_root.jpg"])
        assert root_record["album"] is None

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
