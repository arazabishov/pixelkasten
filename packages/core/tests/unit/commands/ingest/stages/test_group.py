"""Tests for the group stage — shared group_id for logical asset groups."""

from helpers import make_options
from pixelkasten.manifest import (
    Dedupe,
    DedupeResult,
    ManifestEntry,
    SidecarMatch,
    Source,
    Status,
)
from pixelkasten.commands.ingest.stages.group import group
from pixelkasten.commands.ingest.stages.link import _parse_name


def _entry(
    media_path,
    sidecar_path=None,
    dedupe_result=DedupeResult.KEEP,
    skip_dedupe=False,
):
    """Build a manifest entry for group tests, populating ``name`` the way
    link would in a real run."""
    dedupe = (
        None if skip_dedupe else Dedupe(status=Status.PROCESSED, result=dedupe_result, hash="abc")
    )
    sidecar = SidecarMatch(path=sidecar_path, confidence=3) if sidecar_path else None
    return ManifestEntry(
        media_path=media_path,
        source=Source(type="loose"),
        name=_parse_name(media_path),
        dedupe=dedupe,
        sidecar=sidecar,
    )


class TestGroup:
    def test_assigns_group_id_to_singleton_without_sidecar(self):
        manifest = [_entry("/source/photo.jpg")]
        group(manifest, make_options())

        # Singleton entries still get a group_id
        assert manifest[0].group_id is not None
        # And it should be a 32-char uuid hex
        assert len(manifest[0].group_id) == 32

    def test_shared_sidecar_yields_shared_group_id(self):
        manifest = [
            _entry("/source/live.heic", sidecar_path="/source/live.heic.json"),
            _entry("/source/live.mov", sidecar_path="/source/live.heic.json"),
        ]
        group(manifest, make_options())

        # Two entries pointing at the same sidecar share one group_id
        assert manifest[0].group_id == manifest[1].group_id
        assert manifest[0].group_id is not None

    def test_three_member_bundle_shares_one_group_id(self):
        manifest = [
            _entry("/source/img.heic", sidecar_path="/source/img.heic.json"),
            _entry("/source/img-edited.heic", sidecar_path="/source/img.heic.json"),
            _entry("/source/img.mov", sidecar_path="/source/img.heic.json"),
        ]
        group(manifest, make_options())

        # All three members of the bundle share the same group_id
        gid = manifest[0].group_id
        assert gid is not None
        assert manifest[1].group_id == gid
        assert manifest[2].group_id == gid

    def test_different_sidecars_yield_different_group_ids(self):
        manifest = [
            _entry("/source/a.heic", sidecar_path="/source/a.heic.json"),
            _entry("/source/b.heic", sidecar_path="/source/b.heic.json"),
        ]
        group(manifest, make_options())

        # Entries with distinct sidecars never share a group_id
        assert manifest[0].group_id is not None
        assert manifest[1].group_id is not None
        assert manifest[0].group_id != manifest[1].group_id

    def test_two_sidecarless_singletons_get_distinct_group_ids(self):
        manifest = [_entry("/source/a.jpg"), _entry("/source/b.jpg")]
        group(manifest, make_options())

        # Each singleton without a sidecar gets a unique group_id
        assert manifest[0].group_id is not None
        assert manifest[1].group_id is not None
        assert manifest[0].group_id != manifest[1].group_id

    def test_skips_entries_marked_for_deletion(self):
        manifest = [
            _entry("/source/delete.jpg", dedupe_result=DedupeResult.DELETE),
            _entry("/source/keep.jpg"),
        ]
        group(manifest, make_options())

        # Deleted entries are skipped entirely
        assert manifest[0].group_id is None
        # Surviving entries still get group_ids
        assert manifest[1].group_id is not None

    def test_empty_manifest_does_not_error(self):
        manifest: list[ManifestEntry] = []
        group(manifest, make_options())

        # No-op on an empty manifest
        assert manifest == []

    def test_treats_entries_without_dedupe_as_keepers(self):
        manifest = [_entry("/source/photo.jpg", skip_dedupe=True)]
        group(manifest, make_options())

        # can_keep() returns True when dedupe is None, so the entry is grouped
        assert manifest[0].group_id is not None


class TestGroupArchiveMode:
    def test_archive_groups_by_dir_and_parsed_name(self):
        manifest = [
            _entry("/archive/2024/IMG_001.heic"),
            _entry("/archive/2024/IMG_001.mov"),
            _entry("/archive/2024/IMG_002.heic"),
        ]
        group(manifest, make_options(mode="archive"))

        # Same dirname + stem -> same group_id (Live Photo style)
        assert manifest[0].group_id == manifest[1].group_id
        # Different stem -> different group_id
        assert manifest[2].group_id != manifest[0].group_id

    def test_archive_strips_edited_suffix_when_bucketing(self):
        manifest = [
            _entry("/archive/IMG_001.heic"),
            _entry("/archive/IMG_001-edited.heic"),
        ]
        group(manifest, make_options(mode="archive"))

        # The -edited variant is bucketed with the original
        assert manifest[0].group_id == manifest[1].group_id

    def test_archive_separates_by_directory(self):
        manifest = [
            _entry("/a/IMG_001.heic"),
            _entry("/b/IMG_001.heic"),
        ]
        group(manifest, make_options(mode="archive"))

        # Same stem but different directories -> different groups
        assert manifest[0].group_id != manifest[1].group_id

    def test_archive_strips_duplicate_marker_when_bucketing(self):
        # A file manager-created duplicate (Finder / Chrome / Explorer) ends
        # up next to the original. Archive bucketing should group them.
        manifest = [
            _entry("/archive/photo.jpg"),
            _entry("/archive/photo(1).jpg"),
        ]
        group(manifest, make_options(mode="archive"))

        # The (N) variant is bucketed with the original
        assert manifest[0].group_id == manifest[1].group_id

    def test_archive_singleton_gets_a_group_id(self):
        # Even without any siblings to group with, an archive entry should
        # still receive a fresh group_id so emit can use it.
        manifest = [_entry("/archive/lonely.jpg")]
        group(manifest, make_options(mode="archive"))

        assert manifest[0].group_id is not None
        assert len(manifest[0].group_id) == 32

    def test_archive_bucketing_follows_entry_name_not_media_path(self):
        # Pin the contract: group reads entry.name directly. If link
        # (or a test fixture) populated name with a value that differs
        # from what re-parsing media_path would produce, group uses the
        # field. Two entries with different basenames but the same
        # explicitly-set name end up in one bucket.
        a = _entry("/archive/first_basename.jpg")
        b = _entry("/archive/totally_different_basename.jpg")
        a.name = "shared-name"
        b.name = "shared-name"

        group([a, b], make_options(mode="archive"))

        # entry.name is the grouping key — same name in same dir -> same group
        assert a.group_id == b.group_id

    def test_archive_skips_entries_marked_for_deletion(self):
        # Dedupe-marked deletions never get a group_id, even in archive mode.
        manifest = [
            _entry("/archive/keep.jpg"),
            _entry("/archive/dup.jpg", dedupe_result=DedupeResult.DELETE),
        ]
        group(manifest, make_options(mode="archive"))

        # The keeper is grouped
        assert manifest[0].group_id is not None
        # The deletion candidate is skipped
        assert manifest[1].group_id is None
