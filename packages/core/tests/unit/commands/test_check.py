"""
Tests for the check command (`pixelkasten check <library>`).

Builds working-library record fixtures on disk and asserts the reported
conflicts and invalid album names.
"""

import json

from pixelkasten.commands.check import check


def _build_library(tmp_path, records: list[dict]) -> str:
    """Build a working library at tmp_path/lib from a list of record dicts."""
    lib = tmp_path / "lib"
    pk = lib / ".pixelkasten"
    pk.mkdir(parents=True)
    for i, record in enumerate(records):
        name = record.get("filename", f"file{i}.jpg")
        (pk / f"{name}.pk.json").write_text(json.dumps(record))
    return str(lib)


def test_reports_ok_for_a_clean_library(tmp_path):
    lib = _build_library(
        tmp_path,
        [
            {"group_id": "g1", "proposed_album": "Berlin"},
            {"group_id": "g2", "proposed_album": "Wedding 2019"},
        ],
    )

    report = check(lib)

    # A library with agreeing, valid proposals is ready to export
    assert report["ok"] is True


def test_reports_conflict_when_group_members_disagree(tmp_path):
    lib = _build_library(
        tmp_path,
        [
            {"filename": "a", "group_id": "g1", "proposed_album": "Alice"},
            {"filename": "b", "group_id": "g1", "proposed_album": "Bob"},
        ],
    )

    report = check(lib)

    # The group with two distinct proposals is surfaced
    assert report["conflicts"] == [{"group_id": "g1", "proposals": ["Alice", "Bob"]}]

    # A conflict makes the library not ready
    assert report["ok"] is False


def test_reports_invalid_album_name(tmp_path):
    lib = _build_library(
        tmp_path,
        [{"group_id": "g1", "proposed_album": "Trip/with/slashes"}],
    )

    report = check(lib)

    # The unsafe folder name is surfaced
    assert report["invalid_album_names"] == ["Trip/with/slashes"]

    # An invalid name makes the library not ready
    assert report["ok"] is False


def test_reports_invalid_import_album_name_when_it_is_the_target(tmp_path):
    lib = _build_library(
        tmp_path,
        [{"group_id": "g1", "album": "Trip/with/slashes"}],
    )

    report = check(lib)

    # Invalid import-time album names are surfaced when no proposal overrides them
    assert report["invalid_album_names"] == ["Trip/with/slashes"]


def test_ignores_invalid_import_album_name_when_proposal_overrides_it(tmp_path):
    lib = _build_library(
        tmp_path,
        [{"group_id": "g1", "album": "Trip/with/slashes", "proposed_album": "Trip"}],
    )

    report = check(lib)

    # Export will use the valid proposal, so the fallback import album is irrelevant
    assert report["ok"] is True


def test_ignores_records_without_a_proposed_album(tmp_path):
    lib = _build_library(
        tmp_path,
        [
            {"group_id": "g1", "proposed_album": "Berlin"},
            {"group_id": "g2"},
        ],
    )

    report = check(lib)

    # Records that carry no proposal don't contribute conflicts
    assert report["ok"] is True


def test_raises_when_records_directory_is_missing(tmp_path):
    lib = tmp_path / "empty"
    lib.mkdir()

    raised = False
    try:
        check(str(lib))
    except FileNotFoundError:
        raised = True

    # A library with no .pixelkasten/ is a usage error, not an empty report
    assert raised is True
