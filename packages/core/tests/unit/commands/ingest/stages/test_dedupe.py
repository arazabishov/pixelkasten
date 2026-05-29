import hashlib

from helpers import make_options
from pixelkasten.commands.ingest.state import Dedupe, DedupeResult, IngestEntry, Source
from pixelkasten.pipeline import Status
from pixelkasten.commands.ingest.stages.dedupe import dedupe_hash, dedupe_resolve


def _entry(media_path, source_type, source_name=None, hash_val="hash1"):
    """Helper to create a manifest entry with dedupe pending status."""
    source = Source(type=source_type, name=source_name)
    return IngestEntry(
        media_path=media_path,
        source=source,
        dedupe=Dedupe(status=Status.PENDING, hash=hash_val),
    )


class TestDedupeResolve:
    class TestUniqueFiles:
        def test_marks_all_unique_files_as_keep(self):
            manifest = [
                _entry("/tmp/p1.jpg", "loose", hash_val="hash1"),
                _entry("/tmp/p2.jpg", "album", "Vacation", hash_val="hash2"),
                _entry("/tmp/p3.jpg", "loose", hash_val="hash3"),
            ]
            dedupe_resolve(manifest, make_options())
            for e in manifest:
                assert e.dedupe is not None
                assert e.dedupe.result == DedupeResult.KEEP

        def test_marks_unique_regardless_of_preference(self):
            for prefer in ["album", "loose"]:
                for source_type in ["album", "loose"]:
                    m = [_entry("/tmp/p.jpg", source_type, hash_val="h1")]
                    dedupe_resolve(m, make_options(prefer=prefer))
                    assert m[0].dedupe is not None
                    assert m[0].dedupe.result == DedupeResult.KEEP

    class TestPreferAlbum:
        def test_keeps_album_deletes_loose(self):
            manifest = [
                _entry("/tmp/album/p.jpg", "album", "Vacation", hash_val="h1"),
                _entry("/tmp/loose/p.jpg", "loose", hash_val="h1"),
            ]
            dedupe_resolve(manifest, make_options(prefer="album"))
            assert manifest[0].dedupe is not None
            assert manifest[0].dedupe.result == DedupeResult.KEEP
            assert manifest[1].dedupe is not None
            assert manifest[1].dedupe.result == DedupeResult.DELETE

        def test_keeps_multiple_albums_deletes_loose(self):
            manifest = [
                _entry("/tmp/a1/p.jpg", "album", "A1", hash_val="h1"),
                _entry("/tmp/a2/p.jpg", "album", "A2", hash_val="h1"),
                _entry("/tmp/loose/p.jpg", "loose", hash_val="h1"),
            ]
            dedupe_resolve(manifest, make_options(prefer="album"))
            assert manifest[0].dedupe is not None
            assert manifest[0].dedupe.result == DedupeResult.KEEP
            assert manifest[1].dedupe is not None
            assert manifest[1].dedupe.result == DedupeResult.KEEP
            assert manifest[2].dedupe is not None
            assert manifest[2].dedupe.result == DedupeResult.DELETE

        def test_handles_multiple_loose_duplicates(self):
            manifest = [
                _entry("/tmp/a/p.jpg", "album", "A", hash_val="h1"),
                _entry("/tmp/l1/p.jpg", "loose", hash_val="h1"),
                _entry("/tmp/l2/p.jpg", "loose", hash_val="h1"),
            ]
            dedupe_resolve(manifest, make_options(prefer="album"))
            assert manifest[0].dedupe is not None
            assert manifest[0].dedupe.result == DedupeResult.KEEP
            assert manifest[1].dedupe is not None
            assert manifest[1].dedupe.result == DedupeResult.DELETE
            assert manifest[2].dedupe is not None
            assert manifest[2].dedupe.result == DedupeResult.DELETE

    class TestPreferLoose:
        def test_keeps_loose_deletes_album(self):
            manifest = [
                _entry("/tmp/a/p.jpg", "album", "A", hash_val="h1"),
                _entry("/tmp/l/p.jpg", "loose", hash_val="h1"),
            ]
            dedupe_resolve(manifest, make_options(prefer="loose"))
            assert manifest[0].dedupe is not None
            assert manifest[0].dedupe.result == DedupeResult.DELETE
            assert manifest[1].dedupe is not None
            assert manifest[1].dedupe.result == DedupeResult.KEEP

        def test_keeps_multiple_loose_deletes_album(self):
            manifest = [
                _entry("/tmp/a/p.jpg", "album", "A", hash_val="h1"),
                _entry("/tmp/l1/p.jpg", "loose", hash_val="h1"),
                _entry("/tmp/l2/p.jpg", "loose", hash_val="h1"),
            ]
            dedupe_resolve(manifest, make_options(prefer="loose"))
            assert manifest[0].dedupe is not None
            assert manifest[0].dedupe.result == DedupeResult.DELETE
            assert manifest[1].dedupe is not None
            assert manifest[1].dedupe.result == DedupeResult.KEEP
            assert manifest[2].dedupe is not None
            assert manifest[2].dedupe.result == DedupeResult.KEEP

        def test_deletes_all_albums_when_mixed(self):
            manifest = [
                _entry("/tmp/a1/p.jpg", "album", "A1", hash_val="h1"),
                _entry("/tmp/a2/p.jpg", "album", "A2", hash_val="h1"),
                _entry("/tmp/l/p.jpg", "loose", hash_val="h1"),
            ]
            dedupe_resolve(manifest, make_options(prefer="loose"))
            assert manifest[0].dedupe is not None
            assert manifest[0].dedupe.result == DedupeResult.DELETE
            assert manifest[1].dedupe is not None
            assert manifest[1].dedupe.result == DedupeResult.DELETE
            assert manifest[2].dedupe is not None
            assert manifest[2].dedupe.result == DedupeResult.KEEP

    class TestSameTypeDuplicates:
        def test_keeps_all_when_all_albums(self):
            manifest = [
                _entry("/tmp/a1/p.jpg", "album", "A1", hash_val="h1"),
                _entry("/tmp/a2/p.jpg", "album", "A2", hash_val="h1"),
            ]
            dedupe_resolve(manifest, make_options(prefer="album"))
            for e in manifest:
                assert e.dedupe is not None
                assert e.dedupe.result == DedupeResult.KEEP

        def test_keeps_all_when_all_loose(self):
            manifest = [
                _entry("/tmp/l1/p.jpg", "loose", hash_val="h1"),
                _entry("/tmp/l2/p.jpg", "loose", hash_val="h1"),
            ]
            dedupe_resolve(manifest, make_options(prefer="album"))
            for e in manifest:
                assert e.dedupe is not None
                assert e.dedupe.result == DedupeResult.KEEP

    class TestMultipleHashGroups:
        def test_handles_independent_groups(self):
            manifest = [
                _entry("/tmp/a1/p1.jpg", "album", "A", hash_val="h1"),
                _entry("/tmp/l1/p1.jpg", "loose", hash_val="h1"),
                _entry("/tmp/a2/p2.jpg", "album", "B", hash_val="h2"),
                _entry("/tmp/l2/p2.jpg", "loose", hash_val="h2"),
                _entry("/tmp/l3/p3.jpg", "loose", hash_val="h3"),
            ]
            dedupe_resolve(manifest, make_options(prefer="album"))
            # Group h1: album keep, loose delete
            assert manifest[0].dedupe is not None
            assert manifest[0].dedupe.result == DedupeResult.KEEP
            assert manifest[1].dedupe is not None
            assert manifest[1].dedupe.result == DedupeResult.DELETE
            # Group h2: same
            assert manifest[2].dedupe is not None
            assert manifest[2].dedupe.result == DedupeResult.KEEP
            assert manifest[3].dedupe is not None
            assert manifest[3].dedupe.result == DedupeResult.DELETE
            # Group h3: unique, keep
            assert manifest[4].dedupe is not None
            assert manifest[4].dedupe.result == DedupeResult.KEEP

    class TestEdgeCases:
        def test_handles_empty_manifest(self):
            manifest = []
            dedupe_resolve(manifest, make_options())
            assert len(manifest) == 0

        def test_handles_single_file(self):
            manifest = [_entry("/tmp/p.jpg", "loose")]
            dedupe_resolve(manifest, make_options())
            assert manifest[0].dedupe is not None
            assert manifest[0].dedupe.result == DedupeResult.KEEP


class TestDedupeHash:
    def test_computes_sha256_for_files(self, tmp_path):
        f = tmp_path / "test.jpg"
        f.write_bytes(b"hello world")

        manifest = [IngestEntry(media_path=str(f), source=Source(type="loose"))]
        dedupe_hash(manifest)

        expected = hashlib.sha256(b"hello world").hexdigest()
        assert manifest[0].dedupe is not None
        assert manifest[0].dedupe.hash == expected
        assert manifest[0].dedupe.status == Status.PENDING

    def test_handles_read_error(self):
        manifest = [IngestEntry(media_path="/nonexistent/file.jpg", source=Source(type="loose"))]
        dedupe_hash(manifest)

        assert manifest[0].dedupe is not None
        assert manifest[0].dedupe.hash is None
        assert manifest[0].dedupe.status == Status.ERROR
        assert manifest[0].dedupe.error is not None


class TestDedupeArchiveMode:
    def test_archive_uniform_loose_keeps_all(self):
        # Archive entries at the source root come out as ``loose``. When
        # all duplicates in a group are loose, the dedupe rule (shared
        # with Takeout) keeps every copy — there's nothing to discriminate
        # by. This is a known mild over-retention for flat-root dumps.
        manifest = [
            _entry("/photos/zebra.jpg", "loose", hash_val="h1"),
            _entry("/photos/alpha.jpg", "loose", hash_val="h1"),
            _entry("/photos/middle.jpg", "loose", hash_val="h1"),
        ]
        dedupe_resolve(manifest, make_options(mode="archive"))

        # All three duplicates survive (uniform-loose → keep all)
        winners = [
            e.media_path for e in manifest if e.dedupe and e.dedupe.result == DedupeResult.KEEP
        ]
        assert set(winners) == {"/photos/alpha.jpg", "/photos/middle.jpg", "/photos/zebra.jpg"}

    def test_archive_prefer_album_deletes_loose_copy(self):
        # With archive subfolders carrying ``source.type=album``, the
        # --prefer flag is meaningful in archive mode too: a duplicate
        # that exists both in an album folder and loose at the root
        # collapses to just the album copy.
        manifest = [
            _entry("/photos/b.jpg", "loose", hash_val="h"),
            _entry("/photos/Trip/a.jpg", "album", "Trip", hash_val="h"),
        ]
        dedupe_resolve(manifest, make_options(mode="archive", prefer="album"))

        winners = [
            e.media_path for e in manifest if e.dedupe and e.dedupe.result == DedupeResult.KEEP
        ]
        assert winners == ["/photos/Trip/a.jpg"]

    def test_archive_uniform_albums_across_folders_keep_all(self):
        # Same hash in two album subfolders represents intentional
        # cross-folder organization (Wedding album + Honeymoon album).
        # Both copies survive so export can place each in its folder.
        manifest = [
            _entry("/photos/Wedding/x.jpg", "album", "Wedding", hash_val="h"),
            _entry("/photos/Honeymoon/x.jpg", "album", "Honeymoon", hash_val="h"),
        ]
        dedupe_resolve(manifest, make_options(mode="archive"))

        winners = [
            e.media_path for e in manifest if e.dedupe and e.dedupe.result == DedupeResult.KEEP
        ]
        assert set(winners) == {"/photos/Wedding/x.jpg", "/photos/Honeymoon/x.jpg"}

    def test_archive_keeps_uniques(self):
        manifest = [
            _entry("/photos/a.jpg", "loose", hash_val="h1"),
            _entry("/photos/b.jpg", "loose", hash_val="h2"),
        ]
        dedupe_resolve(manifest, make_options(mode="archive"))

        # Hash-unique entries are always kept
        for e in manifest:
            assert e.dedupe is not None
            assert e.dedupe.result == DedupeResult.KEEP
