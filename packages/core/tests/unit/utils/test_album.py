"""Tests for album-name validation and proposed_album conflict detection."""

from pixelkasten.utils.album import (
    check_album_conflicts,
    check_album_name,
)


class TestCheckAlbumName:
    def test_accepts_a_plain_name(self):
        # A normal album name is a valid folder name
        assert check_album_name("Wedding 2019") is True

    def test_rejects_empty_or_whitespace(self):
        # Empty and whitespace-only names can't be folder names
        assert check_album_name("") is False
        assert check_album_name("   ") is False

    def test_rejects_path_separators(self):
        # Slashes and backslashes would split into nested folders
        assert check_album_name("Trip/with/slashes") is False
        assert check_album_name("back\\slash") is False

    def test_rejects_control_characters(self):
        # Control characters aren't safe in a folder name
        assert check_album_name("bad\x00name") is False


class TestCheckAlbumConflicts:
    def test_reports_nothing_when_groups_agree(self):
        # Members agreeing (or partially null) is not a conflict
        groups = {"g1": {"Berlin"}, "g2": set()}

        # No group has two distinct proposals
        assert check_album_conflicts(groups) == []

    def test_reports_group_with_two_distinct_proposals(self):
        groups = {"g1": {"Alice", "Bob"}}

        result = check_album_conflicts(groups)

        # The conflicting group is reported with its sorted proposals
        assert result == [("g1", ["Alice", "Bob"])]
