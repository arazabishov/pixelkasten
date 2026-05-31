"""
Tests for the export command (`pixelkasten export --to <dst>`).

Builds working-library fixtures on disk (real files + records in
.pixelkasten/) and asserts the exported layout. Heavy steps are not mocked
since these are pure file-system operations.
"""

import json
import os

import pytest

from pixelkasten.configuration import ExportOptions
from pixelkasten.commands.export import export


def _build_library(tmp_path, entries: list[dict]) -> str:
    """
    Build a working library at tmp_path/lib.

    Each entry: {"filename": "abc.heic", "dates": [...], "album": ...,
                 "proposed_album": ..., "group_id": ...}

    ``group_id`` defaults to the filename when not provided, making each
    entry a singleton group — matches the real emit contract where every
    record has a ``group_id`` field.
    """
    lib = tmp_path / "lib"
    pk = lib / ".pixelkasten"
    pk.mkdir(parents=True)
    for entry in entries:
        (lib / entry["filename"]).write_bytes(entry.get("content", b"\xff"))
        record = {
            "dates": entry.get("dates", []),
            "geo": entry.get("geo"),
            "album": entry.get("album"),
            "group_id": entry.get("group_id", entry["filename"]),
        }
        if "proposed_album" in entry:
            record["proposed_album"] = entry["proposed_album"]
        (pk / f"{entry['filename']}.pk.json").write_text(json.dumps(record))
    return str(lib)


def _listing(root: str) -> list[str]:
    """Sorted list of relative file paths under `root` (excluding empty)."""
    out: list[str] = []
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            out.append(os.path.relpath(os.path.join(dirpath, f), root))
    return sorted(out)


class TestExportTargets:
    def test_proposed_album_takes_precedence_over_init_album(self, tmp_path):
        lib = _build_library(
            tmp_path,
            [
                {
                    "filename": "abc.jpg",
                    "dates": ["2024-06-01T14:30:22"],
                    "album": "Original Album",
                    "proposed_album": "Agent's Choice",
                }
            ],
        )
        dst = str(tmp_path / "out")

        export(lib, dst, ExportOptions())

        # File lands under the agent's proposed album, not the init-time album
        expected = "2024/20240601-Agent's Choice/20240601-143022.jpg"
        assert _listing(dst) == [expected]

    def test_init_album_used_when_no_proposed_album(self, tmp_path):
        lib = _build_library(
            tmp_path,
            [
                {
                    "filename": "abc.jpg",
                    "dates": ["2024-06-01T14:30:22"],
                    "album": "Wedding 2019",
                }
            ],
        )
        dst = str(tmp_path / "out")

        export(lib, dst, ExportOptions())

        # Without a proposal, the init-time album is honored
        assert _listing(dst) == ["2024/20240601-Wedding 2019/20240601-143022.jpg"]

    def test_loose_with_date_goes_to_year_folder(self, tmp_path):
        lib = _build_library(
            tmp_path,
            [
                {"filename": "abc.jpg", "dates": ["2024-06-01T14:30:22"]},
            ],
        )
        dst = str(tmp_path / "out")

        export(lib, dst, ExportOptions())

        # No album anywhere -> top-level year folder
        assert _listing(dst) == ["2024/20240601-143022.jpg"]


class TestGroupBehavior:
    def test_group_members_co_locate_in_same_folder(self, tmp_path):
        lib = _build_library(
            tmp_path,
            [
                {
                    "filename": "aaaaaa.heic",
                    "group_id": "grp",
                    "dates": ["2024-06-01T14:30:22"],
                    "album": "Vacation",
                },
                {
                    "filename": "bbbbbb.mov",
                    "group_id": "grp",
                    "dates": ["2024-06-01T14:30:22"],
                    "album": "Vacation",
                },
            ],
        )
        dst = str(tmp_path / "out")

        export(lib, dst, ExportOptions())

        out = _listing(dst)
        # Both group members co-locate in the same album folder, named by timestamp
        assert out == [
            "2024/20240601-Vacation/20240601-143022.heic",
            "2024/20240601-Vacation/20240601-143022.mov",
        ]

    def test_propagates_proposed_album_to_siblings_without_it(self, tmp_path):
        # One member has proposed_album, the other doesn't — both should
        # end up in the proposed album folder because they share group_id.
        lib = _build_library(
            tmp_path,
            [
                {
                    "filename": "aaaaaa.heic",
                    "group_id": "grp",
                    "dates": ["2024-06-01T14:30:22"],
                    "proposed_album": "Berlin Trip",
                },
                {
                    "filename": "bbbbbb.mov",
                    "group_id": "grp",
                    "dates": ["2024-06-01T14:30:22"],
                },
            ],
        )
        dst = str(tmp_path / "out")

        export(lib, dst, ExportOptions())

        out = _listing(dst)
        # Both files live under the same album folder
        assert out == [
            "2024/20240601-Berlin Trip/20240601-143022.heic",
            "2024/20240601-Berlin Trip/20240601-143022.mov",
        ]

    def test_conflict_in_proposed_album_aborts_run(self, tmp_path):
        lib = _build_library(
            tmp_path,
            [
                {
                    "filename": "aaaaaa.heic",
                    "group_id": "grp",
                    "dates": ["2024-06-01T14:30:22"],
                    "proposed_album": "Alice's choice",
                },
                {
                    "filename": "bbbbbb.mov",
                    "group_id": "grp",
                    "dates": ["2024-06-01T14:30:22"],
                    "proposed_album": "Bob's choice",
                },
            ],
        )
        dst = str(tmp_path / "out")

        with pytest.raises(RuntimeError, match="disagreement"):
            export(lib, dst, ExportOptions())

        # Destination was never touched on conflict
        assert not os.path.exists(dst) or _listing(dst) == []

    def test_uses_min_date_across_group_for_album_folder(self, tmp_path):
        # Group members have different dates; folder uses the earliest.
        lib = _build_library(
            tmp_path,
            [
                {
                    "filename": "aaaaaa.heic",
                    "group_id": "grp",
                    "dates": ["2024-06-05T10:00:00"],
                    "album": "Trip",
                },
                {
                    "filename": "bbbbbb.mov",
                    "group_id": "grp",
                    "dates": ["2024-06-01T08:00:00"],
                    "album": "Trip",
                },
            ],
        )
        dst = str(tmp_path / "out")

        export(lib, dst, ExportOptions())

        out = _listing(dst)
        # Album folder is prefixed with the earliest date across the group
        assert out == [
            "2024/20240601-Trip/20240601-080000.mov",
            "2024/20240601-Trip/20240605-100000.heic",
        ]

    def test_collapses_all_groups_in_same_album_into_one_folder(self, tmp_path):
        # Two distinct groups (different stems) share an album. The folder
        # date must be the album-wide min, not each group's own min — so they
        # collapse into one folder instead of two.
        lib = _build_library(
            tmp_path,
            [
                {"filename": "aaa.jpg", "dates": ["2024-01-13T18:06:22"], "album": "Baku trip"},
                {"filename": "bbb.jpg", "dates": ["2024-01-01T12:00:00"], "album": "Baku trip"},
                {"filename": "ccc.jpg", "dates": ["2024-01-07T09:00:00"], "album": "Baku trip"},
            ],
        )
        dst = str(tmp_path / "out")

        export(lib, dst, ExportOptions())

        out = _listing(dst)
        # All three entries land in ONE folder, prefixed with 20240101 (the
        # album-wide earliest date), not each group's own date.
        assert out == [
            "2024/20240101-Baku trip/20240101-120000.jpg",
            "2024/20240101-Baku trip/20240107-090000.jpg",
            "2024/20240101-Baku trip/20240113-180622.jpg",
        ]


class TestCollisionHandling:
    def test_unrelated_assets_with_same_timestamp_get_dash_n_suffix(self, tmp_path):
        # Two unrelated stems with the same timestamp -> -1 suffix
        lib = _build_library(
            tmp_path,
            [
                {"filename": "aaa.jpg", "dates": ["2024-06-01T14:30:22"]},
                {"filename": "bbb.jpg", "dates": ["2024-06-01T14:30:22"]},
            ],
        )
        dst = str(tmp_path / "out")

        export(lib, dst, ExportOptions())

        out = _listing(dst)
        # First wins the bare timestamp name; second gets the -1 suffix
        assert out == [
            "2024/20240601-143022-1.jpg",
            "2024/20240601-143022.jpg",
        ]


class TestForceAndDryRun:
    def test_refuses_when_destination_is_nonempty(self, tmp_path):
        lib = _build_library(
            tmp_path,
            [{"filename": "abc.jpg", "dates": ["2024-06-01T14:30:22"]}],
        )
        dst = tmp_path / "out"
        dst.mkdir()
        (dst / "preexisting.txt").write_text("hi")

        with pytest.raises(RuntimeError, match="already exists"):
            export(str(lib), str(dst), ExportOptions())

    def test_force_overwrites_existing_destination(self, tmp_path):
        lib = _build_library(
            tmp_path,
            [{"filename": "abc.jpg", "dates": ["2024-06-01T14:30:22"]}],
        )
        dst = tmp_path / "out"
        dst.mkdir()
        (dst / "preexisting.txt").write_text("hi")

        export(str(lib), str(dst), ExportOptions(force=True))

        # Pre-existing file is gone after force-overwrite
        assert _listing(str(dst)) == ["2024/20240601-143022.jpg"]

    def test_dry_run_writes_nothing(self, tmp_path):
        lib = _build_library(
            tmp_path,
            [{"filename": "abc.jpg", "dates": ["2024-06-01T14:30:22"]}],
        )
        dst = tmp_path / "out"

        summary = export(str(lib), str(dst), ExportOptions(dry_run=True))

        # No files created
        assert not dst.exists()
        # The plan still reports the one copy that would have run
        assert len(summary.operations) == 1

    def test_working_library_is_untouched_after_export(self, tmp_path):
        lib = _build_library(
            tmp_path,
            [
                {
                    "filename": "abc.jpg",
                    "dates": ["2024-06-01T14:30:22"],
                    "album": "Wedding",
                    "proposed_album": "Berlin",
                }
            ],
        )
        # Snapshot the working library before
        before = _listing(lib)
        record_before = json.loads(
            open(os.path.join(lib, ".pixelkasten", "abc.jpg.pk.json")).read()
        )

        export(lib, str(tmp_path / "out"), ExportOptions())

        # File listing unchanged
        assert _listing(lib) == before
        # Record unchanged — proposed_album persists for re-runs
        record_after = json.loads(open(os.path.join(lib, ".pixelkasten", "abc.jpg.pk.json")).read())
        assert record_after == record_before


class TestInvalidAlbumNames:
    def test_rejects_invalid_album_path_separators(self, tmp_path):
        lib = _build_library(
            tmp_path,
            [
                {
                    "filename": "abc.jpg",
                    "dates": ["2024-06-01T14:30:22"],
                    "album": "Trip/with/slashes",
                }
            ],
        )
        dst = str(tmp_path / "out")

        with pytest.raises(RuntimeError, match="invalid album name"):
            export(lib, dst, ExportOptions())

        # Invalid names fail before export writes anything
        assert not os.path.exists(dst) or _listing(dst) == []
