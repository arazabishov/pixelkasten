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


def _entry(
    media_path,
    sidecar_path=None,
    dedupe_result=DedupeResult.KEEP,
    skip_dedupe=False,
):
    """Build a manifest entry positioned just before group runs."""
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
    def test_groups_live_photo_pair_by_shared_stem(self):
        # Live Photo image + video: same dir, same stem, different extension.
        manifest = [
            _entry("/archive/IMG_1234.HEIC"),
            _entry("/archive/IMG_1234.MOV"),
        ]
        group(manifest, make_options(mode="archive"))

        # Shared stem in the same directory yields a shared group_id
        assert manifest[0].group_id == manifest[1].group_id
        assert manifest[0].group_id is not None

    def test_groups_raw_and_jpeg_capture_by_shared_stem(self):
        # DSLR/mirrorless RAW+JPEG capture: same logical photo, two files.
        manifest = [
            _entry("/archive/IMG_1234.CR2"),
            _entry("/archive/IMG_1234.JPG"),
        ]
        group(manifest, make_options(mode="archive"))

        # Shared stem groups the capture together
        assert manifest[0].group_id == manifest[1].group_id

    def test_separates_distinct_content_with_duplicate_marker(self):
        # Two distinct files (browser collision rename, manual duplicate, etc.)
        # that happen to share a base name. Dedupe collapsed any identical
        # content; if both survive here, they hold distinct content and must
        # not share a group.
        manifest = [
            _entry("/archive/photo.jpg"),
            _entry("/archive/photo(1).jpg"),
        ]
        group(manifest, make_options(mode="archive"))

        # (N) is NOT stripped — each file gets its own group_id
        assert manifest[0].group_id != manifest[1].group_id

    def test_lone_edited_filename_keeps_literal_stem(self):
        # An -edited-suffixed filename has no special handling in archive mode;
        # it buckets by its literal stem like any other file.
        manifest = [_entry("/archive/vacation-edited.jpg")]
        group(manifest, make_options(mode="archive"))

        # Single entry → single group; the literal stem is the key
        assert manifest[0].group_id is not None

    def test_unrelated_stems_in_same_dir_stay_separate(self):
        # Two files with distinct stems in the same directory must not be
        # grouped together, even when one has an -edited suffix that could
        # superficially relate to some hypothetical sibling.
        manifest = [
            _entry("/archive/vacation-edited.jpg"),
            _entry("/archive/sunset.jpg"),
        ]
        group(manifest, make_options(mode="archive"))

        # Each file keeps its literal stem; no incidental grouping
        assert manifest[0].group_id != manifest[1].group_id

    def test_separates_same_stem_across_directories(self):
        # Same stem in different directories — distinct assets.
        manifest = [
            _entry("/a/photo.jpg"),
            _entry("/b/photo.jpg"),
        ]
        group(manifest, make_options(mode="archive"))

        # Directory is part of the key
        assert manifest[0].group_id != manifest[1].group_id

    def test_archive_singleton_gets_a_group_id(self):
        # Even without any siblings to group with, an archive entry should
        # still receive a fresh group_id so emit can use it.
        manifest = [_entry("/archive/lonely.jpg")]
        group(manifest, make_options(mode="archive"))

        # 32-char uuid hex assigned to the singleton
        assert manifest[0].group_id is not None
        assert len(manifest[0].group_id) == 32

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
