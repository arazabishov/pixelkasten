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
from pixelkasten.commands.import_.group import group


def _entry(
    media_path,
    sidecar_path=None,
    dedupe_result=DedupeResult.KEEP,
    skip_dedupe=False,
):
    """Build a manifest entry for group tests."""
    dedupe = (
        None if skip_dedupe else Dedupe(status=Status.PROCESSED, result=dedupe_result, hash="abc")
    )
    sidecar = SidecarMatch(path=sidecar_path, confidence=3) if sidecar_path else None
    return ManifestEntry(
        media_path=media_path,
        source=Source(type="loose"),
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
    def test_archive_groups_by_dir_and_stripped_stem(self):
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
