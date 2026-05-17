"""
Tests for the emit stage.

Emit copies keepers to a flat <dst>/<file_id>.<ext> layout and writes a
per-asset record JSON into <dst>/.pixelkasten/. Tests run against a real
tmp filesystem (not mocked) so we can inspect the written records.

EXIF writes are mocked to avoid an exiftool dependency in unit tests; the
integration suite covers the real exiftool path.
"""

import json
import os
import re
from unittest.mock import patch

from helpers import make_options
from pixelkasten.manifest import (
    ApplyResult,
    Dedupe,
    DedupeResult,
    Geo,
    ManifestEntry,
    Metadata,
    SidecarMatch,
    Source,
    Status,
)
from pixelkasten.commands.ingest.stages.emit import emit

UUID_HEX = re.compile(r"^[0-9a-f]{32}$")


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
        sidecar=SidecarMatch(path=sidecar_path, confidence=3) if sidecar_path else None,
        group_id=group_id,
    )


def _emitted_file_id(apply_target_path: str) -> str:
    return os.path.splitext(os.path.basename(apply_target_path))[0]


def _read_record(dest, final_name) -> dict:
    with open(os.path.join(dest, ".pixelkasten", final_name + ".pk.json")) as f:
        return json.load(f)


class TestEmit:
    @patch("pixelkasten.commands.ingest.stages.emit.write_metadata")
    def test_emits_singleton_with_uuid_filename(self, mock_write_metadata, tmp_path):
        dest = str(tmp_path / "dest")
        src = _make_source_file(tmp_path, "photo.heic", b"image-bytes")
        manifest = [_entry(src, group_id="abc123", dates=["2024-06-01T14:30:22"])]

        emit(manifest, make_options(destination=dest))

        # File lands at <dest>/<uuid>.<ext>
        target = manifest[0].apply.target_path
        assert target is not None
        # Filename is a fresh uuid4 hex, not derived from group_id
        file_id = _emitted_file_id(target)
        assert UUID_HEX.match(file_id), file_id
        assert file_id != "abc123"
        # Content is preserved
        assert open(target, "rb").read() == b"image-bytes"
        # Apply result reflects a plain copy (no write_tags queued)
        assert manifest[0].apply.result == ApplyResult.COPIED

    @patch("pixelkasten.commands.ingest.stages.emit.write_metadata")
    def test_writes_record_with_four_fields_including_group_id(self, mock_write_metadata, tmp_path):
        dest = str(tmp_path / "dest")
        src = _make_source_file(tmp_path, "photo.heic")
        manifest = [
            _entry(
                src,
                group_id="grp-abc",
                dates=["2024-06-01T14:30:22"],
                geo=Geo(latitude=52.52, longitude=13.40, altitude=34.0),
                source_type="album",
                source_name="Wedding 2019",
            )
        ]

        emit(manifest, make_options(destination=dest))

        final_name = os.path.basename(manifest[0].apply.target_path)
        data = _read_record(dest, final_name)
        # All four record fields are present, including group_id
        assert data["dates"] == ["2024-06-01T14:30:22"]
        assert data["geo"] == {"latitude": 52.52, "longitude": 13.40, "altitude": 34.0}
        assert data["album"] == "Wedding 2019"
        assert data["group_id"] == "grp-abc"

    @patch("pixelkasten.commands.ingest.stages.emit.write_metadata")
    def test_record_has_empty_dates_when_metadata_absent(self, mock_write_metadata, tmp_path):
        dest = str(tmp_path / "dest")
        src = _make_source_file(tmp_path, "photo.jpg")
        manifest = [_entry(src, group_id="zzz")]

        emit(manifest, make_options(destination=dest))

        final_name = os.path.basename(manifest[0].apply.target_path)
        data = _read_record(dest, final_name)
        # No metadata -> empty dates, null geo, null album, group_id still set
        assert data["dates"] == []
        assert data["geo"] is None
        assert data["album"] is None
        assert data["group_id"] == "zzz"

    @patch("pixelkasten.commands.ingest.stages.emit.write_metadata")
    def test_record_geo_null_when_geo_absent(self, mock_write_metadata, tmp_path):
        dest = str(tmp_path / "dest")
        src = _make_source_file(tmp_path, "photo.jpg")
        manifest = [_entry(src, group_id="ggg", dates=["2024-01-01T00:00:00"])]

        emit(manifest, make_options(destination=dest))

        final_name = os.path.basename(manifest[0].apply.target_path)
        data = _read_record(dest, final_name)
        # Geo missing on the entry -> null in the record
        assert data["geo"] is None

    @patch("pixelkasten.commands.ingest.stages.emit.write_metadata")
    def test_record_album_null_for_loose_entries(self, mock_write_metadata, tmp_path):
        dest = str(tmp_path / "dest")
        src = _make_source_file(tmp_path, "photo.jpg")
        manifest = [_entry(src, group_id="lll", dates=["2024-01-01T00:00:00"])]

        emit(manifest, make_options(destination=dest))

        final_name = os.path.basename(manifest[0].apply.target_path)
        data = _read_record(dest, final_name)
        # Loose entry -> album is null even when source has no name
        assert data["album"] is None

    @patch("pixelkasten.commands.ingest.stages.emit.write_metadata")
    def test_group_members_get_distinct_filenames_sharing_group_id(
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

        # Both members land on disk under their own uuid filenames
        targets = [manifest[0].apply.target_path, manifest[1].apply.target_path]
        for t in targets:
            assert os.path.exists(t)
            assert UUID_HEX.match(_emitted_file_id(t))
        # Filenames are distinct (no shared stem any more)
        assert _emitted_file_id(targets[0]) != _emitted_file_id(targets[1])
        # But both records share the same group_id
        records = [_read_record(dest, os.path.basename(t)) for t in targets]
        assert records[0]["group_id"] == records[1]["group_id"] == "grp"

    @patch("pixelkasten.commands.ingest.stages.emit.write_metadata")
    def test_same_extension_siblings_get_distinct_filenames_no_underscore_suffix(
        self, mock_write_metadata, tmp_path
    ):
        # This is the case the original `_disambiguate` _N suffix was for:
        # two same-extension members of one group (e.g. an edited HEIC variant).
        # The new contract: each file gets its own uuid filename and the group
        # identity travels in the record, so no _2 suffix is needed.
        dest = str(tmp_path / "dest")
        a = _make_source_file(tmp_path, "a.heic", b"original")
        b = _make_source_file(tmp_path, "a-edited.heic", b"edited")
        manifest = [
            _entry(a, group_id="grp", dates=["2024-06-01T14:30:22"]),
            _entry(b, group_id="grp", dates=["2024-06-01T14:30:22"]),
        ]

        emit(manifest, make_options(destination=dest))

        targets = [manifest[0].apply.target_path, manifest[1].apply.target_path]
        # Both files exist and have distinct names
        assert os.path.exists(targets[0])
        assert os.path.exists(targets[1])
        assert targets[0] != targets[1]
        # No "_2" disambiguation suffix in either filename
        for t in targets:
            assert "_" not in os.path.basename(t)
        # Both records carry the shared group_id so downstream tools find them
        records = [_read_record(dest, os.path.basename(t)) for t in targets]
        assert records[0]["group_id"] == records[1]["group_id"] == "grp"

    @patch("pixelkasten.commands.ingest.stages.emit.write_metadata")
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
        assert called_path == manifest[0].apply.target_path
        assert called_tags == ["DateTimeOriginal=2024:06:01 14:30:22"]
        # Result reflects the write
        assert manifest[0].apply is not None
        assert manifest[0].apply.result == ApplyResult.WRITTEN

    @patch("pixelkasten.commands.ingest.stages.emit.write_metadata")
    def test_does_not_invoke_exiftool_when_write_tags_empty(self, mock_write_metadata, tmp_path):
        dest = str(tmp_path / "dest")
        src = _make_source_file(tmp_path, "photo.jpg")
        manifest = [_entry(src, group_id="aaa", dates=["2024-06-01T14:30:22"], write_tags=[])]

        emit(manifest, make_options(destination=dest))

        # No queued writes -> exiftool never invoked
        mock_write_metadata.assert_not_called()

    @patch("pixelkasten.commands.ingest.stages.emit.write_metadata")
    def test_skips_unsupported_entries(self, mock_write_metadata, tmp_path):
        dest = str(tmp_path / "dest")
        src = _make_source_file(tmp_path, "video.mkv", b"data")
        manifest = [_entry(src, group_id="mkv", metadata_status=Status.SKIPPED)]

        emit(manifest, make_options(destination=dest))

        # Unsupported format never reaches the working library — no file emitted
        assert manifest[0].apply.target_path is None
        # No artifacts left on disk for the skipped entry
        assert not list(
            f
            for f in os.listdir(dest)
            if not f.startswith(".") and os.path.isfile(os.path.join(dest, f))
        )
        # Apply field records the skip
        assert manifest[0].apply.status == Status.SKIPPED

    @patch("pixelkasten.commands.ingest.stages.emit.write_metadata")
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

        # With nothing to emit, the destination directory is never created
        assert not os.path.exists(dest)
        # And no apply state is set on the entry
        assert manifest[0].apply is None

    @patch("pixelkasten.commands.ingest.stages.emit.write_metadata")
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
