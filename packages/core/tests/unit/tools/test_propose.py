"""Tests for tools/propose.py — write proposed_album to group siblings."""

import json
import os

import pytest

from pixelkasten.tools.propose import propose


def _make_library_with_group(tmp_path, members: list[str]) -> str:
    """Build a working library where every entry in `members` shares a stem."""
    lib = tmp_path / "lib"
    pk = lib / ".pixelkasten"
    pk.mkdir(parents=True)
    for name in members:
        (lib / name).write_bytes(b"\xff")
        (pk / f"{name}.pk.json").write_text(json.dumps({"dates": [], "geo": None, "album": None}))
    return str(lib)


def _read_sidecar(library: str, name: str) -> dict:
    with open(os.path.join(library, ".pixelkasten", f"{name}.pk.json")) as f:
        return json.load(f)


class TestPropose:
    def test_writes_proposed_album_for_singleton(self, tmp_path):
        lib = _make_library_with_group(tmp_path, ["abc.jpg"])

        updated = propose(os.path.join(lib, "abc.jpg"), "Vacation 2024")

        # Exactly one sidecar updated
        assert len(updated) == 1
        # The proposed_album field is set on the sidecar
        assert _read_sidecar(lib, "abc.jpg")["proposed_album"] == "Vacation 2024"

    def test_propagates_to_all_group_siblings(self, tmp_path):
        lib = _make_library_with_group(tmp_path, ["live.heic", "live.mov", "live-edited.heic"])
        # live-edited.heic has a different stem; only live.heic and live.mov share

        updated = propose(os.path.join(lib, "live.heic"), "Berlin 2024")

        # The two siblings sharing the stem are both updated
        assert len(updated) == 2
        assert _read_sidecar(lib, "live.heic")["proposed_album"] == "Berlin 2024"
        assert _read_sidecar(lib, "live.mov")["proposed_album"] == "Berlin 2024"
        # The edited variant has a different stem and is not touched
        assert "proposed_album" not in _read_sidecar(lib, "live-edited.heic")

    def test_clear_removes_proposed_album(self, tmp_path):
        lib = _make_library_with_group(tmp_path, ["a.jpg"])
        # First set the value
        propose(os.path.join(lib, "a.jpg"), "Some Album")
        assert "proposed_album" in _read_sidecar(lib, "a.jpg")

        # Then clear it
        updated = propose(os.path.join(lib, "a.jpg"), None)

        assert len(updated) == 1
        # proposed_album is gone from the sidecar
        assert "proposed_album" not in _read_sidecar(lib, "a.jpg")

    def test_clear_is_idempotent_when_no_proposed_album(self, tmp_path):
        lib = _make_library_with_group(tmp_path, ["a.jpg"])

        updated = propose(os.path.join(lib, "a.jpg"), None)

        # Clearing a never-set value still reports the sidecar as visited
        assert len(updated) == 1
        # And the field remains absent
        assert "proposed_album" not in _read_sidecar(lib, "a.jpg")

    def test_overwrites_existing_proposal(self, tmp_path):
        lib = _make_library_with_group(tmp_path, ["a.jpg"])
        propose(os.path.join(lib, "a.jpg"), "First")
        propose(os.path.join(lib, "a.jpg"), "Second")

        # The later proposal wins
        assert _read_sidecar(lib, "a.jpg")["proposed_album"] == "Second"

    def test_raises_when_file_stem_not_in_library_root(self, tmp_path):
        lib = _make_library_with_group(tmp_path, ["a.jpg"])
        # Drop a file in a subdir of the library with a stem that doesn't appear
        # at the root. propose walks up to the library and looks for siblings
        # there — none should be found.
        sub = os.path.join(lib, "scratch")
        os.makedirs(sub)
        ghost = os.path.join(sub, "ghost.jpg")
        open(ghost, "wb").close()

        with pytest.raises(RuntimeError, match="No working-library file"):
            propose(ghost, "Album")

    def test_rejects_empty_album_name(self, tmp_path):
        lib = _make_library_with_group(tmp_path, ["a.jpg"])
        with pytest.raises(ValueError, match="non-empty"):
            propose(os.path.join(lib, "a.jpg"), "   ")

    def test_rejects_literal_null_album_name(self, tmp_path):
        lib = _make_library_with_group(tmp_path, ["a.jpg"])
        with pytest.raises(ValueError, match="reserved"):
            propose(os.path.join(lib, "a.jpg"), "null")
