"""
Tests for the link stage — ported from packages/core/test/stages/link.test.js.

These tests are the specification for Google Takeout sidecar matching.
Every edge case encodes real-world filename truncation behavior.
"""

from helpers import make_options
from pixelkasten.stages.link import link


def _link_and_map(raw, **overrides):
    """Helper: run link() and return a dict keyed by media_path."""
    result = link(raw, make_options(**overrides))
    return {e.media_path: e for e in result["manifest"]}, result["stats"]


class TestMetadataNormalizationAndMatching:
    RAW = {
        "files_media": [
            "/tmp/3D06C8D1-7637-4625-BEBE-C3D916AEF50D.jpg",
            "/tmp/PXL_20241231_114900266.jpg",
            "/tmp/PXL_20241231_114910784.MP.jpg",
            "/tmp/camphoto_33463914(4).jpg",
            "/tmp/camphoto_33463914.MP(4).jpg",
            "/tmp/29407C9C-7528-4FF1-AD5F-08EAA7F9738E-98855-000",
        ],
        "files_metadata": [
            "/tmp/3D06C8D1-7637-4625-BEBE-C3D916AEF50D.jpg.suppl.json",
            "/tmp/PXL_20241231_114900266.jpg.supplemental-metada.json",
            "/tmp/PXL_20241231_114910784.MP.jpg.supplemental-met.json",
            "/tmp/camphoto_33463914.jpg.supplemental-metadata(4).json",
            "/tmp/camphoto_33463914.MP.jpg.supplemental-metadata(4).json",
            "/tmp/29407C9C-7528-4FF1-AD5F-08EAA7F9738E-98855-000.json",
        ],
        "files_metadata_albums": [],
    }

    def test_matches_suppl_json(self):
        m, _ = _link_and_map(self.RAW)
        entry = m["/tmp/3D06C8D1-7637-4625-BEBE-C3D916AEF50D.jpg"]
        assert entry.sidecar.path == "/tmp/3D06C8D1-7637-4625-BEBE-C3D916AEF50D.jpg.suppl.json"

    def test_matches_supplemental_metada_json(self):
        m, _ = _link_and_map(self.RAW)
        entry = m["/tmp/PXL_20241231_114900266.jpg"]
        assert entry.sidecar.path == "/tmp/PXL_20241231_114900266.jpg.supplemental-metada.json"

    def test_matches_supplemental_met_with_double_extension(self):
        m, _ = _link_and_map(self.RAW)
        entry = m["/tmp/PXL_20241231_114910784.MP.jpg"]
        assert entry.sidecar.path == "/tmp/PXL_20241231_114910784.MP.jpg.supplemental-met.json"

    def test_matches_supplemental_metadata_with_duplicate_marker(self):
        m, _ = _link_and_map(self.RAW)
        entry = m["/tmp/camphoto_33463914(4).jpg"]
        assert entry.sidecar.path == "/tmp/camphoto_33463914.jpg.supplemental-metadata(4).json"

    def test_matches_supplemental_metadata_with_duplicate_and_double_ext(self):
        m, _ = _link_and_map(self.RAW)
        entry = m["/tmp/camphoto_33463914.MP(4).jpg"]
        assert entry.sidecar.path == "/tmp/camphoto_33463914.MP.jpg.supplemental-metadata(4).json"

    def test_matches_filename_without_extension(self):
        m, _ = _link_and_map(self.RAW)
        entry = m["/tmp/29407C9C-7528-4FF1-AD5F-08EAA7F9738E-98855-000"]
        assert entry.sidecar.path == "/tmp/29407C9C-7528-4FF1-AD5F-08EAA7F9738E-98855-000.json"


class TestExactMatching:
    RAW = {
        "files_media": [
            "/tmp/IMG_0076.PNG",
            "/tmp/IMG_0784.MOV",
            "/tmp/FA79581F10E4.jpeg",
        ],
        "files_metadata": [
            "/tmp/IMG_0076.PNG.supplemental-metadata.json",
            "/tmp/IMG_0784.MOV.supplemental-metadata.json",
            "/tmp/FA79581F10E4.jpeg..json",
        ],
        "files_metadata_albums": [],
    }

    def test_matches_png(self):
        m, _ = _link_and_map(self.RAW)
        assert m["/tmp/IMG_0076.PNG"].sidecar.path == "/tmp/IMG_0076.PNG.supplemental-metadata.json"

    def test_matches_mov(self):
        m, _ = _link_and_map(self.RAW)
        assert m["/tmp/IMG_0784.MOV"].sidecar.path == "/tmp/IMG_0784.MOV.supplemental-metadata.json"

    def test_matches_double_dot_extension(self):
        m, _ = _link_and_map(self.RAW)
        assert m["/tmp/FA79581F10E4.jpeg"].sidecar.path == "/tmp/FA79581F10E4.jpeg..json"


class TestTruncatedFilenamesFuzzyMatching:
    RAW = {
        "files_media": [
            "/tmp/988555-0000.mov",
            "/tmp/C3D916AEF50.jpg",
            "/tmp/a2345678901234567890123456789012345678901.jpg",
            "/tmp/b23456789012345678901234567890123456789012.jpg",
            "/tmp/c234567890123456789012345678901234567890123.jpg",
            "/tmp/d2345678901234567890123456789012345678901234.jpg",
            "/tmp/e23456789012345678901234567890123456789012345.jpg",
            "/tmp/f234567890123456789012345678901234567890123456.jpg",
            "/tmp/g2345678901234567890123456789012345678901234567.jpg",
            "/tmp/h2345678901234567890123456789012345678901234567.jpg",
            "/tmp/i2345678901234567890123456789012345678901234567.jpg",
        ],
        "files_metadata": [
            "/tmp/988555-000.json",
            "/tmp/C3D916AEF50D.jpg.suppl.json",
            "/tmp/a2345678901234567890123456789012345678901.jpg.json",
            "/tmp/b23456789012345678901234567890123456789012.jpg.json",
            "/tmp/c234567890123456789012345678901234567890123.jp.json",
            "/tmp/d2345678901234567890123456789012345678901234.j.json",
            "/tmp/e23456789012345678901234567890123456789012345..json",
            "/tmp/f234567890123456789012345678901234567890123456.json",
            "/tmp/g234567890123456789012345678901234567890123456.json",
            "/tmp/h234567890123456789012345678901234567890123456.json",
            "/tmp/i234567890123456789012345678901234567890123456.json",
        ],
        "files_metadata_albums": [],
    }

    def test_matches_truncated_video(self):
        m, _ = _link_and_map(self.RAW, fuzzy_threshold=0)
        assert m["/tmp/988555-0000.mov"].sidecar.path == "/tmp/988555-000.json"

    def test_matches_truncated_jpg(self):
        m, _ = _link_and_map(self.RAW, fuzzy_threshold=0)
        assert m["/tmp/C3D916AEF50.jpg"].sidecar.path == "/tmp/C3D916AEF50D.jpg.suppl.json"

    def test_matches_systematic_truncation_cases(self):
        m, _ = _link_and_map(self.RAW, fuzzy_threshold=0)
        cases = ["a", "b", "c", "d", "e", "f", "g", "h", "i"]
        for c in cases:
            media = next(f for f in self.RAW["files_media"] if f"/{c}" in f)
            metadata = next(f for f in self.RAW["files_metadata"] if f"/{c}" in f)
            entry = m[media]
            assert entry.sidecar is not None, f"No match for case {c}"
            assert entry.sidecar.path == metadata, f"Mismatch for case {c}"


class TestDuplicateFiles:
    RAW = {
        "files_media": ["/tmp/1804928587.jpg", "/tmp/1804928587(1).jpg"],
        "files_metadata": [
            "/tmp/1804928587.jpg.supplemental-metadata.json",
            "/tmp/1804928587.jpg.supplemental-metadata(1).json",
        ],
        "files_metadata_albums": [],
    }

    def test_matches_original(self):
        m, _ = _link_and_map(self.RAW)
        assert (
            m["/tmp/1804928587.jpg"].sidecar.path
            == "/tmp/1804928587.jpg.supplemental-metadata.json"
        )

    def test_matches_duplicate_marker(self):
        m, _ = _link_and_map(self.RAW)
        assert (
            m["/tmp/1804928587(1).jpg"].sidecar.path
            == "/tmp/1804928587.jpg.supplemental-metadata(1).json"
        )


class TestDistanceBasedFuzzyMatchingWithDuplicates:
    RAW = {
        "files_media": [
            "/tmp/IMG_0449.MP4",
            "/tmp/IMG_0449(1).HEIC",
            "/tmp/IMG_0449(1).MP4",
            "/tmp/IMG_0450.MP4",
            "/tmp/IMG_0450(1).HEIC",
            "/tmp/IMG_0450(1).MP4",
        ],
        "files_metadata": [
            "/tmp/IMG_0449.HEIC.supplemental-metadata.json",
            "/tmp/IMG_0449.HEIC.supplemental-metadata(1).json",
            "/tmp/IMG_0450.HEIC.supplemental-metadata.json",
            "/tmp/IMG_0450.HEIC.supplemental-metadata(1).json",
        ],
        "files_metadata_albums": [],
    }

    def test_matches_no_marker_0449_mp4(self):
        m, _ = _link_and_map(self.RAW)
        assert (
            m["/tmp/IMG_0449.MP4"].sidecar.path == "/tmp/IMG_0449.HEIC.supplemental-metadata.json"
        )

    def test_matches_marker_1_0449_heic(self):
        m, _ = _link_and_map(self.RAW)
        assert (
            m["/tmp/IMG_0449(1).HEIC"].sidecar.path
            == "/tmp/IMG_0449.HEIC.supplemental-metadata(1).json"
        )

    def test_matches_marker_1_0449_mp4(self):
        m, _ = _link_and_map(self.RAW)
        assert (
            m["/tmp/IMG_0449(1).MP4"].sidecar.path
            == "/tmp/IMG_0449.HEIC.supplemental-metadata(1).json"
        )

    def test_matches_no_marker_0450_mp4(self):
        m, _ = _link_and_map(self.RAW)
        assert (
            m["/tmp/IMG_0450.MP4"].sidecar.path == "/tmp/IMG_0450.HEIC.supplemental-metadata.json"
        )

    def test_matches_marker_1_0450_heic(self):
        m, _ = _link_and_map(self.RAW)
        assert (
            m["/tmp/IMG_0450(1).HEIC"].sidecar.path
            == "/tmp/IMG_0450.HEIC.supplemental-metadata(1).json"
        )

    def test_matches_marker_1_0450_mp4(self):
        m, _ = _link_and_map(self.RAW)
        assert (
            m["/tmp/IMG_0450(1).MP4"].sidecar.path
            == "/tmp/IMG_0450.HEIC.supplemental-metadata(1).json"
        )


class TestDistanceThresholdPreventsFalseMatches:
    RAW = {
        "files_media": [
            "/tmp/IMG_0449.MP4",
            "/tmp/IMG_0449(1).HEIC",
            "/tmp/IMG_0449(1).MP4",
        ],
        "files_metadata": ["/tmp/IMG_0449.HEIC.supplemental-metadata(1).json"],
        "files_metadata_albums": [],
    }

    def test_no_match_when_no_corresponding_metadata(self):
        m, _ = _link_and_map(self.RAW)
        assert m["/tmp/IMG_0449.MP4"].sidecar is None

    def test_matches_heic_with_marker(self):
        m, _ = _link_and_map(self.RAW)
        assert (
            m["/tmp/IMG_0449(1).HEIC"].sidecar.path
            == "/tmp/IMG_0449.HEIC.supplemental-metadata(1).json"
        )

    def test_matches_mp4_with_marker(self):
        m, _ = _link_and_map(self.RAW)
        assert (
            m["/tmp/IMG_0449(1).MP4"].sidecar.path
            == "/tmp/IMG_0449.HEIC.supplemental-metadata(1).json"
        )


class TestEditedFiles:
    RAW = {
        "files_media": [
            "/tmp/photo.jpg",
            "/tmp/photo-edited.jpg",
            "/tmp/IMG_1234.PNG",
            "/tmp/IMG_1234-edited.PNG",
            "/tmp/IMG_1809 Copy.JPG",
            "/tmp/IMG_1809 Copy-edited.JPG",
            "/tmp/j23456789012345678901234567890123456-edited.jpg",
        ],
        "files_metadata": [
            "/tmp/photo.jpg.json",
            "/tmp/IMG_1234.PNG.json",
            "/tmp/IMG_1809 Copy.JPG.supplemental-metadata.json",
            "/tmp/j2345678901234567890123456789012345678901.jpg.json",
        ],
        "files_metadata_albums": [],
    }

    def test_matches_edited_to_original(self):
        m, _ = _link_and_map(self.RAW)
        assert m["/tmp/photo-edited.jpg"].sidecar.path == "/tmp/photo.jpg.json"

    def test_matches_edited_png(self):
        m, _ = _link_and_map(self.RAW)
        assert m["/tmp/IMG_1234-edited.PNG"].sidecar.path == "/tmp/IMG_1234.PNG.json"

    def test_matches_copy_edited(self):
        m, _ = _link_and_map(self.RAW)
        assert (
            m["/tmp/IMG_1809 Copy-edited.JPG"].sidecar.path
            == "/tmp/IMG_1809 Copy.JPG.supplemental-metadata.json"
        )

    def test_matches_edited_with_truncation(self):
        m, _ = _link_and_map(self.RAW)
        assert (
            m["/tmp/j23456789012345678901234567890123456-edited.jpg"].sidecar.path
            == "/tmp/j2345678901234567890123456789012345678901.jpg.json"
        )


class TestComplexExtensionsAndCollisions:
    RAW = {
        "files_media": [
            "/tmp/11491078.MP.jpg",
            "/tmp/11491078.MP",
            "/tmp/IMG_0785.HEIC",
            "/tmp/11491078.MP-edited.jpg",
        ],
        "files_metadata": [
            "/tmp/11491078.MP.jpg.supplemental-met.json",
            "/tmp/IMG_0785.HEIC.supplemental-metadata.json",
        ],
        "files_metadata_albums": [],
    }

    def test_matches_double_extension(self):
        m, _ = _link_and_map(self.RAW)
        assert (
            m["/tmp/11491078.MP.jpg"].sidecar.path == "/tmp/11491078.MP.jpg.supplemental-met.json"
        )

    def test_matches_prefix_collision(self):
        m, _ = _link_and_map(self.RAW)
        assert m["/tmp/11491078.MP"].sidecar.path == "/tmp/11491078.MP.jpg.supplemental-met.json"

    def test_matches_live_photo_heic(self):
        m, _ = _link_and_map(self.RAW)
        assert (
            m["/tmp/IMG_0785.HEIC"].sidecar.path == "/tmp/IMG_0785.HEIC.supplemental-metadata.json"
        )

    def test_matches_edited_double_extension(self):
        m, _ = _link_and_map(self.RAW)
        assert (
            m["/tmp/11491078.MP-edited.jpg"].sidecar.path
            == "/tmp/11491078.MP.jpg.supplemental-met.json"
        )


class TestAlbumSourceDetection:
    RAW = {
        "files_media": [
            "/tmp/My Album/IMG_0076.PNG",
            "/tmp/Vacation 2024/photo.jpg",
            "/tmp/loose.jpg",
        ],
        "files_metadata": [],
        "files_metadata_albums": [
            "/tmp/My Album/metadata.json",
            "/tmp/Vacation 2024/metadata.json",
        ],
    }

    def test_identifies_album_sources(self):
        m, _ = _link_and_map(self.RAW)
        assert m["/tmp/My Album/IMG_0076.PNG"].source.type == "album"
        assert m["/tmp/My Album/IMG_0076.PNG"].source.name == "My Album"
        assert m["/tmp/Vacation 2024/photo.jpg"].source.type == "album"
        assert m["/tmp/Vacation 2024/photo.jpg"].source.name == "Vacation 2024"

    def test_identifies_loose_files(self):
        m, _ = _link_and_map(self.RAW)
        assert m["/tmp/loose.jpg"].source.type == "loose"


class TestDirectoryIsolation:
    def test_does_not_match_across_sibling_directories(self):
        raw = {
            "files_media": ["/Photos/Vacation.jpg"],
            "files_metadata": ["/Photos/Vacation 2024/IMG_123.json"],
            "files_metadata_albums": [],
        }
        m, _ = _link_and_map(raw)
        assert m["/Photos/Vacation.jpg"].sidecar is None


class TestStatisticsAndReporting:
    RAW = {
        "files_media": ["/tmp/matched.jpg", "/tmp/unmatched.jpg"],
        "files_metadata": ["/tmp/matched.jpg.json", "/tmp/unused.json"],
        "files_metadata_albums": [],
    }

    def test_reports_unmatched_media(self):
        _, stats = _link_and_map(self.RAW)
        assert "/tmp/unmatched.jpg" in stats["unmatched_media_files"]
        assert len(stats["unmatched_media_files"]) == 1

    def test_reports_unmatched_metadata(self):
        _, stats = _link_and_map(self.RAW)
        assert "/tmp/unused.json" in stats["unmatched_metadata_files"]
        assert len(stats["unmatched_metadata_files"]) == 1


class TestExtensionSpecificMatching:
    RAW = {
        "files_media": ["/tmp/IMG_0267.JPG", "/tmp/IMG_0523.MOV", "/tmp/IMG_0525.PNG"],
        "files_metadata": [
            "/tmp/IMG_0267.HEIC.supplemental-metadata.json",
            "/tmp/IMG_0267.JPG.supplemental-metadata.json",
            "/tmp/IMG_0523.HEIC.supplemental-metadata.json",
            "/tmp/IMG_0523.MOV.supplemental-metadata.json",
            "/tmp/IMG_0525.HEIC.supplemental-metadata.json",
            "/tmp/IMG_0525.PNG.supplemental-metadata.json",
        ],
        "files_metadata_albums": [],
    }

    def test_jpg_matches_jpg_not_heic(self):
        m, _ = _link_and_map(self.RAW)
        assert m["/tmp/IMG_0267.JPG"].sidecar.path == "/tmp/IMG_0267.JPG.supplemental-metadata.json"

    def test_mov_matches_mov_not_heic(self):
        m, _ = _link_and_map(self.RAW)
        assert m["/tmp/IMG_0523.MOV"].sidecar.path == "/tmp/IMG_0523.MOV.supplemental-metadata.json"

    def test_png_matches_png_not_heic(self):
        m, _ = _link_and_map(self.RAW)
        assert m["/tmp/IMG_0525.PNG"].sidecar.path == "/tmp/IMG_0525.PNG.supplemental-metadata.json"

    def test_heic_metadata_left_unmatched(self):
        _, stats = _link_and_map(self.RAW)
        assert "/tmp/IMG_0267.HEIC.supplemental-metadata.json" in stats["unmatched_metadata_files"]
        assert "/tmp/IMG_0523.HEIC.supplemental-metadata.json" in stats["unmatched_metadata_files"]
        assert "/tmp/IMG_0525.HEIC.supplemental-metadata.json" in stats["unmatched_metadata_files"]
        assert len(stats["unmatched_metadata_files"]) == 3


class TestSafetyAgainstFalsePositives:
    RAW = {
        "files_media": ["/tmp/IMG_123.jpg", "/tmp/IMG_1234.jpg"],
        "files_metadata": ["/tmp/IMG_123.json"],
        "files_metadata_albums": [],
    }

    def test_matches_exact_short_name(self):
        m, _ = _link_and_map(self.RAW)
        assert m["/tmp/IMG_123.jpg"].sidecar.path == "/tmp/IMG_123.json"

    def test_does_not_fuzzy_match_short_prefix(self):
        m, _ = _link_and_map(self.RAW)
        assert m["/tmp/IMG_1234.jpg"].sidecar is None


class TestTruncatedEditedSuffixes:
    RAW = {
        "files_media": [
            "/tmp/IMG_100-edited.jpg",
            "/tmp/IMG_200-edite.jpg",
            "/tmp/IMG_300-edit.jpg",
            "/tmp/IMG_400-edi.jpg",
            "/tmp/IMG_500.MP-edited.jpg",
        ],
        "files_metadata": [
            "/tmp/IMG_100.json",
            "/tmp/IMG_200.json",
            "/tmp/IMG_300.json",
            "/tmp/IMG_400.json",
            "/tmp/IMG_500.MP.jpg.json",
        ],
        "files_metadata_albums": [],
    }

    def test_matches_full_edited(self):
        m, _ = _link_and_map(self.RAW)
        assert m["/tmp/IMG_100-edited.jpg"].sidecar.path == "/tmp/IMG_100.json"

    def test_matches_truncated_edite(self):
        m, _ = _link_and_map(self.RAW)
        assert m["/tmp/IMG_200-edite.jpg"].sidecar.path == "/tmp/IMG_200.json"

    def test_matches_truncated_edit(self):
        m, _ = _link_and_map(self.RAW)
        assert m["/tmp/IMG_300-edit.jpg"].sidecar.path == "/tmp/IMG_300.json"

    def test_matches_truncated_edi(self):
        m, _ = _link_and_map(self.RAW)
        assert m["/tmp/IMG_400-edi.jpg"].sidecar.path == "/tmp/IMG_400.json"

    def test_matches_edited_with_embedded_extension(self):
        m, _ = _link_and_map(self.RAW)
        assert m["/tmp/IMG_500.MP-edited.jpg"].sidecar.path == "/tmp/IMG_500.MP.jpg.json"


class TestTruncatedLivePhotoWithSharedSidecar:
    RAW = {
        "files_media": [
            "/tmp/3D06C8D1-7637-4625-BEBE-C3D916AEF50D.mp4",
            "/tmp/3D06C8D1-7637-4625-BEBE-C3D916AEF50.heic",
        ],
        "files_metadata": ["/tmp/3D06C8D1-7637-4625-BEBE-C3D916AEF50D.json"],
        "files_metadata_albums": [],
    }

    def test_matches_exact_mp4(self):
        m, _ = _link_and_map(self.RAW, fuzzy_threshold=0)
        assert (
            m["/tmp/3D06C8D1-7637-4625-BEBE-C3D916AEF50D.mp4"].sidecar.path
            == "/tmp/3D06C8D1-7637-4625-BEBE-C3D916AEF50D.json"
        )

    def test_matches_truncated_heic(self):
        m, _ = _link_and_map(self.RAW, fuzzy_threshold=0)
        assert (
            m["/tmp/3D06C8D1-7637-4625-BEBE-C3D916AEF50.heic"].sidecar.path
            == "/tmp/3D06C8D1-7637-4625-BEBE-C3D916AEF50D.json"
        )


class TestFuzzyMatchingDisabled:
    RAW = {
        "files_media": [
            "/tmp/exact-match.jpg",
            "/tmp/truncated-media-file-name-that-is-very-long.jpg",
        ],
        "files_metadata": [
            "/tmp/exact-match.jpg.json",
            "/tmp/truncated-media-file-name-that-is-very-long-and.json",
        ],
        "files_metadata_albums": [],
    }

    def test_exact_matches_still_work(self):
        m, _ = _link_and_map(self.RAW, fuzzy_threshold=0, fuzzy=False)
        assert m["/tmp/exact-match.jpg"].sidecar.path == "/tmp/exact-match.jpg.json"

    def test_truncated_does_not_match(self):
        m, _ = _link_and_map(self.RAW, fuzzy_threshold=0, fuzzy=False)
        assert m["/tmp/truncated-media-file-name-that-is-very-long.jpg"].sidecar is None


class TestExtensionCaseInsensitivity:
    RAW = {
        "files_media": ["/tmp/IMAGE.JPG", "/tmp/photo.PNG", "/tmp/VIDEO.MOV"],
        "files_metadata": [
            "/tmp/IMAGE.jpg.json",
            "/tmp/photo.png.supplemental-metadata.json",
            "/tmp/VIDEO.mov.supplemental-metadata.json",
        ],
        "files_metadata_albums": [],
    }

    def test_jpg_case_insensitive(self):
        m, _ = _link_and_map(self.RAW)
        assert m["/tmp/IMAGE.JPG"].sidecar.path == "/tmp/IMAGE.jpg.json"

    def test_png_case_insensitive(self):
        m, _ = _link_and_map(self.RAW)
        assert m["/tmp/photo.PNG"].sidecar.path == "/tmp/photo.png.supplemental-metadata.json"

    def test_mov_case_insensitive(self):
        m, _ = _link_and_map(self.RAW)
        assert m["/tmp/VIDEO.MOV"].sidecar.path == "/tmp/VIDEO.mov.supplemental-metadata.json"


class TestOsPathPreservesFilenames:
    def test_double_extension_preserved(self):
        """Verify os.path.splitext preserves .MP in photo.MP.jpg."""
        import os.path

        name, ext = os.path.splitext("photo.MP.jpg")
        assert name == "photo.MP"
        assert ext == ".jpg"

    def test_duplicate_marker_preserved(self):
        """Verify os.path doesn't normalize (1) in filenames."""
        import os.path

        base = os.path.basename("/tmp/photo(1).jpg")
        assert base == "photo(1).jpg"
