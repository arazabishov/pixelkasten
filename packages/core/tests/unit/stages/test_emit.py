"""
Tests for the emit stage.

Emit copies keepers to a flat <dst>/<group_id>.<ext> layout and writes a
per-asset sidecar JSON into <dst>/.pixelkasten/. Tests run against a real
tmp filesystem (not mocked) so we can inspect the written sidecars.

EXIF writes are mocked to avoid an exiftool dependency in unit tests; the
integration suite covers the real exiftool path.
"""

import json
import os
from unittest.mock import patch

from helpers import make_options
from pixelkasten.manifest import (
    ApplyResult,
    Dedupe,
    DedupeResult,
    Geo,
    ManifestEntry,
    Metadata,
    Sidecar,
    Source,
    Status,
)
from pixelkasten.stages.emit import emit


def _make_source_file(tmp_path, name, content=b"fixture") -> str:
    path = tmp_path / "src" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return str(path)


def _entry(
    media_path,
    group_id="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    dates=None,
    geo=None,
    write_tags=None,
    metadata_status=Status.PROCESSED,
    source_type="loose",
    source_name=None,
    sidecar_path=None,
    dedupe_result=DedupeResult.KEEP,
):
    """Build a manifest entry positioned just before emit runs."""
    metadata = None
    if dates is not None or geo is not None or write_tags is not None:
        metadata = Metadata(
            status=metadata_status,
            dates=dates or [],
            write_tags=write_tags or [],
            geo=geo,
        )
    if metadata_status == Status.SKIPPED and metadata is None:
        metadata = Metadata(status=Status.SKIPPED, error="unsupported")
    return ManifestEntry(
        media_path=media_path,
        source=Source(type=source_type, name=source_name),
        dedupe=Dedupe(status=Status.PROCESSED, result=dedupe_result, hash="abc"),
        metadata=metadata,
        sidecar=Sidecar(path=sidecar_path, confidence=3) if sidecar_path else None,
        group_id=group_id,
    )


def _read_sidecar(dest, final_name) -> dict:
    with open(os.path.join(dest, ".pixelkasten", final_name + ".pk.json")) as f:
        return json.load(f)


class TestEmit:
    @patch("pixelkasten.stages.emit.write_metadata")
    def test_emits_singleton_with_guid_filename(self, mock_write_metadata, tmp_path):
        dest = str(tmp_path / "dest")
        src = _make_source_file(tmp_path, "photo.heic", b"image-bytes")
        manifest = [_entry(src, group_id="abc123", dates=["2024-06-01T14:30:22"])]

        emit(manifest, make_options(destination=dest))

        # File lands at <dest>/<group_id>.<ext>
        copied = os.path.join(dest, "abc123.heic")
        assert os.path.exists(copied)
        # Content is preserved
        assert open(copied, "rb").read() == b"image-bytes"
        # apply field records the destination path
        assert manifest[0].apply is not None
        assert manifest[0].apply.target_path == copied
        assert manifest[0].apply.result == ApplyResult.COPIED

    @patch("pixelkasten.stages.emit.write_metadata")
    def test_writes_sidecar_with_three_fields(self, mock_write_metadata, tmp_path):
        dest = str(tmp_path / "dest")
        src = _make_source_file(tmp_path, "photo.heic")
        manifest = [
            _entry(
                src,
                group_id="aaa",
                dates=["2024-06-01T14:30:22"],
                geo=Geo(latitude=52.52, longitude=13.40, altitude=34.0),
                source_type="album",
                source_name="Wedding 2019",
            )
        ]

        emit(manifest, make_options(destination=dest))

        data = _read_sidecar(dest, "aaa.heic")
        # All three init-time fields are present
        assert data["dates"] == ["2024-06-01T14:30:22"]
        assert data["geo"] == {"latitude": 52.52, "longitude": 13.40, "altitude": 34.0}
        assert data["album"] == "Wedding 2019"

    @patch("pixelkasten.stages.emit.write_metadata")
    def test_sidecar_has_empty_dates_when_metadata_absent(self, mock_write_metadata, tmp_path):
        dest = str(tmp_path / "dest")
        src = _make_source_file(tmp_path, "photo.jpg")
        manifest = [_entry(src, group_id="zzz")]

        emit(manifest, make_options(destination=dest))

        data = _read_sidecar(dest, "zzz.jpg")
        # No metadata -> empty dates, null geo, null album
        assert data["dates"] == []
        assert data["geo"] is None
        assert data["album"] is None

    @patch("pixelkasten.stages.emit.write_metadata")
    def test_sidecar_geo_null_when_geo_absent(self, mock_write_metadata, tmp_path):
        dest = str(tmp_path / "dest")
        src = _make_source_file(tmp_path, "photo.jpg")
        manifest = [_entry(src, group_id="ggg", dates=["2024-01-01T00:00:00"])]

        emit(manifest, make_options(destination=dest))

        data = _read_sidecar(dest, "ggg.jpg")
        # Geo missing on the entry -> null in the sidecar
        assert data["geo"] is None

    @patch("pixelkasten.stages.emit.write_metadata")
    def test_sidecar_album_null_for_loose_entries(self, mock_write_metadata, tmp_path):
        dest = str(tmp_path / "dest")
        src = _make_source_file(tmp_path, "photo.jpg")
        manifest = [_entry(src, group_id="lll", dates=["2024-01-01T00:00:00"])]

        emit(manifest, make_options(destination=dest))

        data = _read_sidecar(dest, "lll.jpg")
        # Loose entry -> album is null even when source has no name
        assert data["album"] is None

    @patch("pixelkasten.stages.emit.write_metadata")
    def test_multi_member_group_shares_stem_with_distinct_extensions(
        self, mock_write_metadata, tmp_path
    ):
        dest = str(tmp_path / "dest")
        heic = _make_source_file(tmp_path, "live.heic", b"image")
        mov = _make_source_file(tmp_path, "live.mov", b"video")
        manifest = [
            _entry(heic, group_id="grp", dates=["2024-06-01T14:30:22"]),
            _entry(mov, group_id="grp", dates=["2024-06-01T14:30:22"]),
        ]

        emit(manifest, make_options(destination=dest))

        # Both members share the stem, only the extension differs
        assert os.path.exists(os.path.join(dest, "grp.heic"))
        assert os.path.exists(os.path.join(dest, "grp.mov"))
        # Each gets its own sidecar in .pixelkasten/
        assert os.path.exists(os.path.join(dest, ".pixelkasten", "grp.heic.pk.json"))
        assert os.path.exists(os.path.join(dest, ".pixelkasten", "grp.mov.pk.json"))

    @patch("pixelkasten.stages.emit.write_metadata")
    def test_same_extension_collision_within_group_gets_underscore_suffix(
        self, mock_write_metadata, tmp_path
    ):
        dest = str(tmp_path / "dest")
        a = _make_source_file(tmp_path, "a.heic", b"original")
        b = _make_source_file(tmp_path, "a-edited.heic", b"edited")
        manifest = [
            _entry(a, group_id="grp", dates=["2024-06-01T14:30:22"]),
            _entry(b, group_id="grp", dates=["2024-06-01T14:30:22"]),
        ]

        emit(manifest, make_options(destination=dest))

        # First member keeps the bare stem
        assert os.path.exists(os.path.join(dest, "grp.heic"))
        # The colliding second member is suffixed _2
        assert os.path.exists(os.path.join(dest, "grp_2.heic"))
        # Each gets its own sidecar
        assert os.path.exists(os.path.join(dest, ".pixelkasten", "grp.heic.pk.json"))
        assert os.path.exists(os.path.join(dest, ".pixelkasten", "grp_2.heic.pk.json"))

    @patch("pixelkasten.stages.emit.write_metadata")
    def test_invokes_exiftool_when_write_tags_present(self, mock_write_metadata, tmp_path):
        dest = str(tmp_path / "dest")
        src = _make_source_file(tmp_path, "photo.jpg")
        manifest = [
            _entry(
                src,
                group_id="aaa",
                dates=["2024-06-01T14:30:22"],
                write_tags=["DateTimeOriginal=2024:06:01 14:30:22"],
            )
        ]

        emit(manifest, make_options(destination=dest))

        # exiftool wrapper is invoked on the destination copy, with the queued tags
        assert mock_write_metadata.call_count == 1
        called_path, called_tags = mock_write_metadata.call_args_list[0][0]
        assert called_path == os.path.join(dest, "aaa.jpg")
        assert called_tags == ["DateTimeOriginal=2024:06:01 14:30:22"]
        # Result reflects the write
        assert manifest[0].apply is not None
        assert manifest[0].apply.result == ApplyResult.WRITTEN

    @patch("pixelkasten.stages.emit.write_metadata")
    def test_does_not_invoke_exiftool_when_write_tags_empty(self, mock_write_metadata, tmp_path):
        dest = str(tmp_path / "dest")
        src = _make_source_file(tmp_path, "photo.jpg")
        manifest = [_entry(src, group_id="aaa", dates=["2024-06-01T14:30:22"], write_tags=[])]

        emit(manifest, make_options(destination=dest))

        # No queued writes -> exiftool never invoked
        mock_write_metadata.assert_not_called()

    @patch("pixelkasten.stages.emit.write_metadata")
    def test_skips_unsupported_entries(self, mock_write_metadata, tmp_path):
        dest = str(tmp_path / "dest")
        src = _make_source_file(tmp_path, "video.mkv", b"data")
        manifest = [_entry(src, group_id="mkv", metadata_status=Status.SKIPPED)]

        emit(manifest, make_options(destination=dest))

        # Unsupported format never reaches the working library
        assert not os.path.exists(os.path.join(dest, "mkv.mkv"))
        # No sidecar written for the skipped entry
        assert not os.path.exists(os.path.join(dest, ".pixelkasten", "mkv.mkv.pk.json"))
        # Apply field records the skip
        assert manifest[0].apply is not None
        assert manifest[0].apply.status == Status.SKIPPED

    @patch("pixelkasten.stages.emit.write_metadata")
    def test_skips_entries_marked_for_deletion(self, mock_write_metadata, tmp_path):
        dest = str(tmp_path / "dest")
        src = _make_source_file(tmp_path, "dup.jpg")
        manifest = [
            _entry(
                src,
                group_id="dup",
                dates=["2024-06-01T14:30:22"],
                dedupe_result=DedupeResult.DELETE,
            ),
        ]

        emit(manifest, make_options(destination=dest))

        # Deleted entries are not copied
        assert not os.path.exists(os.path.join(dest, "dup.jpg"))
        # And no apply state is set on them
        assert manifest[0].apply is None

    @patch("pixelkasten.stages.emit.write_metadata")
    def test_records_apply_error_when_copy_fails(self, mock_write_metadata, tmp_path):
        dest = str(tmp_path / "dest")
        manifest = [
            _entry(
                "/does/not/exist.jpg",
                group_id="missing",
                dates=["2024-06-01T14:30:22"],
            )
        ]

        emit(manifest, make_options(destination=dest))

        # Copy failure surfaces on the apply field with the error
        assert manifest[0].apply is not None
        assert manifest[0].apply.status == Status.ERROR
        assert manifest[0].apply.error
