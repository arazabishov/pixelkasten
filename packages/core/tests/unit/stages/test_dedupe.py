import hashlib

from helpers import make_options
from pixelkasten.stages.dedupe import dedupe_hash, dedupe_resolve


def _entry(media_path, source_type, source_name=None, hash_val="hash1"):
    """Helper to create a manifest entry with dedupe pending status."""
    source = {"type": source_type}
    if source_name:
        source["name"] = source_name
    return {
        "mediaPath": media_path,
        "source": source,
        "dedupe": {"hash": hash_val, "status": "pending"},
    }


class TestDedupeResolve:
    class TestUniqueFiles:
        def test_marks_all_unique_files_as_keep(self):
            manifest = [
                _entry("/tmp/p1.jpg", "loose", hash_val="hash1"),
                _entry("/tmp/p2.jpg", "album", "Vacation", hash_val="hash2"),
                _entry("/tmp/p3.jpg", "loose", hash_val="hash3"),
            ]
            dedupe_resolve(manifest)
            assert all(e["dedupe"]["status"] == "keep" for e in manifest)

        def test_marks_unique_regardless_of_preference(self):
            for prefer in ["album", "loose"]:
                for source_type in ["album", "loose"]:
                    m = [_entry("/tmp/p.jpg", source_type, hash_val="h1")]
                    dedupe_resolve(m, make_options(prefer=prefer))
                    assert m[0]["dedupe"]["status"] == "keep"

    class TestPreferAlbum:
        def test_keeps_album_deletes_loose(self):
            manifest = [
                _entry("/tmp/album/p.jpg", "album", "Vacation", hash_val="h1"),
                _entry("/tmp/loose/p.jpg", "loose", hash_val="h1"),
            ]
            dedupe_resolve(manifest, make_options(prefer="album"))
            assert manifest[0]["dedupe"]["status"] == "keep"
            assert manifest[1]["dedupe"]["status"] == "delete"

        def test_keeps_multiple_albums_deletes_loose(self):
            manifest = [
                _entry("/tmp/a1/p.jpg", "album", "A1", hash_val="h1"),
                _entry("/tmp/a2/p.jpg", "album", "A2", hash_val="h1"),
                _entry("/tmp/loose/p.jpg", "loose", hash_val="h1"),
            ]
            dedupe_resolve(manifest, make_options(prefer="album"))
            assert manifest[0]["dedupe"]["status"] == "keep"
            assert manifest[1]["dedupe"]["status"] == "keep"
            assert manifest[2]["dedupe"]["status"] == "delete"

        def test_handles_multiple_loose_duplicates(self):
            manifest = [
                _entry("/tmp/a/p.jpg", "album", "A", hash_val="h1"),
                _entry("/tmp/l1/p.jpg", "loose", hash_val="h1"),
                _entry("/tmp/l2/p.jpg", "loose", hash_val="h1"),
            ]
            dedupe_resolve(manifest, make_options(prefer="album"))
            assert manifest[0]["dedupe"]["status"] == "keep"
            assert manifest[1]["dedupe"]["status"] == "delete"
            assert manifest[2]["dedupe"]["status"] == "delete"

    class TestPreferLoose:
        def test_keeps_loose_deletes_album(self):
            manifest = [
                _entry("/tmp/a/p.jpg", "album", "A", hash_val="h1"),
                _entry("/tmp/l/p.jpg", "loose", hash_val="h1"),
            ]
            dedupe_resolve(manifest, make_options(prefer="loose"))
            assert manifest[0]["dedupe"]["status"] == "delete"
            assert manifest[1]["dedupe"]["status"] == "keep"

        def test_keeps_multiple_loose_deletes_album(self):
            manifest = [
                _entry("/tmp/a/p.jpg", "album", "A", hash_val="h1"),
                _entry("/tmp/l1/p.jpg", "loose", hash_val="h1"),
                _entry("/tmp/l2/p.jpg", "loose", hash_val="h1"),
            ]
            dedupe_resolve(manifest, make_options(prefer="loose"))
            assert manifest[0]["dedupe"]["status"] == "delete"
            assert manifest[1]["dedupe"]["status"] == "keep"
            assert manifest[2]["dedupe"]["status"] == "keep"

        def test_deletes_all_albums_when_mixed(self):
            manifest = [
                _entry("/tmp/a1/p.jpg", "album", "A1", hash_val="h1"),
                _entry("/tmp/a2/p.jpg", "album", "A2", hash_val="h1"),
                _entry("/tmp/l/p.jpg", "loose", hash_val="h1"),
            ]
            dedupe_resolve(manifest, make_options(prefer="loose"))
            assert manifest[0]["dedupe"]["status"] == "delete"
            assert manifest[1]["dedupe"]["status"] == "delete"
            assert manifest[2]["dedupe"]["status"] == "keep"

    class TestSameTypeDuplicates:
        def test_keeps_all_when_all_albums(self):
            manifest = [
                _entry("/tmp/a1/p.jpg", "album", "A1", hash_val="h1"),
                _entry("/tmp/a2/p.jpg", "album", "A2", hash_val="h1"),
            ]
            dedupe_resolve(manifest, make_options(prefer="album"))
            assert all(e["dedupe"]["status"] == "keep" for e in manifest)

        def test_keeps_all_when_all_loose(self):
            manifest = [
                _entry("/tmp/l1/p.jpg", "loose", hash_val="h1"),
                _entry("/tmp/l2/p.jpg", "loose", hash_val="h1"),
            ]
            dedupe_resolve(manifest, make_options(prefer="album"))
            assert all(e["dedupe"]["status"] == "keep" for e in manifest)

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
            assert manifest[0]["dedupe"]["status"] == "keep"
            assert manifest[1]["dedupe"]["status"] == "delete"
            # Group h2: same
            assert manifest[2]["dedupe"]["status"] == "keep"
            assert manifest[3]["dedupe"]["status"] == "delete"
            # Group h3: unique, keep
            assert manifest[4]["dedupe"]["status"] == "keep"

    class TestEdgeCases:
        def test_handles_empty_manifest(self):
            manifest = []
            dedupe_resolve(manifest)
            assert len(manifest) == 0

        def test_handles_single_file(self):
            manifest = [_entry("/tmp/p.jpg", "loose")]
            dedupe_resolve(manifest)
            assert manifest[0]["dedupe"]["status"] == "keep"


class TestDedupeHash:
    def test_computes_sha256_for_files(self, tmp_path):
        f = tmp_path / "test.jpg"
        f.write_bytes(b"hello world")

        manifest = [{"mediaPath": str(f)}]
        dedupe_hash(manifest)

        expected = hashlib.sha256(b"hello world").hexdigest()
        assert manifest[0]["dedupe"]["hash"] == expected
        assert manifest[0]["dedupe"]["status"] == "pending"

    def test_handles_read_error(self):
        manifest = [{"mediaPath": "/nonexistent/file.jpg"}]
        dedupe_hash(manifest)

        assert manifest[0]["dedupe"]["hash"] is None
        assert manifest[0]["dedupe"]["status"] == "error"
        assert "reason" in manifest[0]["dedupe"]
