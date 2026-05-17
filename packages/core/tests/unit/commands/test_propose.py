"""Tests for commands/propose.py — write proposed_album to group siblings."""

import json
import os

import pytest

from pixelkasten.commands.propose import propose


def _make_library(tmp_path, members: dict[str, str]) -> str:
    """Build a working library where ``members`` maps filename -> group_id.

    Members with the same group_id are siblings; emit no longer uses the
    filename stem for grouping, so the test fixture mirrors the real
    contract: each record carries a ``group_id`` field.
    """
    lib = tmp_path / "lib"
    pk = lib / ".pixelkasten"
    pk.mkdir(parents=True)
    for name, group_id in members.items():
        (lib / name).write_bytes(b"\xff")
        (pk / f"{name}.pk.json").write_text(
            json.dumps({"dates": [], "geo": None, "album": None, "group_id": group_id})
        )
    return str(lib)


def _read_record(library: str, name: str) -> dict:
    with open(os.path.join(library, ".pixelkasten", f"{name}.pk.json")) as f:
        return json.load(f)


class TestPropose:
    def test_writes_proposed_album_for_singleton(self, tmp_path):
        lib = _make_library(tmp_path, {"abc.jpg": "grp-1"})

        updated = propose(os.path.join(lib, "abc.jpg"), "Vacation 2024")

        # Exactly one record updated
        assert len(updated) == 1
        # The proposed_album field is set on the record
        assert _read_record(lib, "abc.jpg")["proposed_album"] == "Vacation 2024"

    def test_propagates_to_all_group_siblings(self, tmp_path):
        lib = _make_library(
            tmp_path,
            {
                "live-image.heic": "grp-live",
                "live-video.mov": "grp-live",
                "different.heic": "grp-other",
            },
        )

        updated = propose(os.path.join(lib, "live-image.heic"), "Berlin 2024")

        # Both members of grp-live are updated, regardless of filename stem
        assert len(updated) == 2
        assert _read_record(lib, "live-image.heic")["proposed_album"] == "Berlin 2024"
        assert _read_record(lib, "live-video.mov")["proposed_album"] == "Berlin 2024"
        # The other group is not touched
        assert "proposed_album" not in _read_record(lib, "different.heic")

    def test_propagates_to_siblings_with_unrelated_filenames(self, tmp_path):
        # Critical case: emit's new contract is that filenames are independently
        # unique (uuid4), so siblings of one logical asset no longer share a
        # filename stem. Propose must still propagate via group_id.
        lib = _make_library(
            tmp_path,
            {
                "aaaaaa.heic": "grp-live",  # the "original" HEIC
                "bbbbbb.heic": "grp-live",  # the edited HEIC variant
                "cccccc.mov": "grp-live",  # the Live Photo video
            },
        )

        updated = propose(os.path.join(lib, "aaaaaa.heic"), "Wedding")

        # All three siblings update even though no two share a stem
        assert len(updated) == 3
        for name in ("aaaaaa.heic", "bbbbbb.heic", "cccccc.mov"):
            assert _read_record(lib, name)["proposed_album"] == "Wedding"

    def test_clear_removes_proposed_album(self, tmp_path):
        lib = _make_library(tmp_path, {"a.jpg": "g"})
        # First set the value
        propose(os.path.join(lib, "a.jpg"), "Some Album")
        assert "proposed_album" in _read_record(lib, "a.jpg")

        # Then clear it
        updated = propose(os.path.join(lib, "a.jpg"), None)

        assert len(updated) == 1
        # proposed_album is gone from the record
        assert "proposed_album" not in _read_record(lib, "a.jpg")

    def test_clear_is_idempotent_when_no_proposed_album(self, tmp_path):
        lib = _make_library(tmp_path, {"a.jpg": "g"})

        updated = propose(os.path.join(lib, "a.jpg"), None)

        # Clearing a never-set value still reports the record as visited
        assert len(updated) == 1
        # And the field remains absent
        assert "proposed_album" not in _read_record(lib, "a.jpg")

    def test_overwrites_existing_proposal(self, tmp_path):
        lib = _make_library(tmp_path, {"a.jpg": "g"})
        propose(os.path.join(lib, "a.jpg"), "First")
        propose(os.path.join(lib, "a.jpg"), "Second")

        # The later proposal wins
        assert _read_record(lib, "a.jpg")["proposed_album"] == "Second"

    def test_raises_when_record_missing_group_id(self, tmp_path):
        lib = tmp_path / "lib"
        pk = lib / ".pixelkasten"
        pk.mkdir(parents=True)
        (lib / "a.jpg").write_bytes(b"\xff")
        # Pre-1.0 record missing the group_id field
        (pk / "a.jpg.pk.json").write_text(json.dumps({"dates": [], "geo": None, "album": None}))

        # propose surfaces the missing field rather than silently producing
        # a singleton group; the user is told to re-import.
        with pytest.raises(RuntimeError, match="no group_id"):
            propose(os.path.join(str(lib), "a.jpg"), "Album")

    def test_rejects_empty_album_name(self, tmp_path):
        lib = _make_library(tmp_path, {"a.jpg": "g"})
        with pytest.raises(ValueError, match="non-empty"):
            propose(os.path.join(lib, "a.jpg"), "   ")

    def test_rejects_literal_null_album_name(self, tmp_path):
        lib = _make_library(tmp_path, {"a.jpg": "g"})
        with pytest.raises(ValueError, match="reserved"):
            propose(os.path.join(lib, "a.jpg"), "null")
