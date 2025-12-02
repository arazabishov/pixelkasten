import { test, describe } from "node:test";
import { strictEqual, ok } from "node:assert";
import { link } from "../../src/stages/link.js";

describe("link", () => {
  describe("metadata normalization & matching", () => {
    const rawCollections = {
      filesMedia: [
        "/tmp/3D06C8D1-7637-4625-BEBE-C3D916AEF50D.jpg",
        "/tmp/PXL_20241231_114900266.jpg",
        "/tmp/PXL_20241231_114910784.MP.jpg",
        "/tmp/camphoto_33463914(4).jpg",
        "/tmp/camphoto_33463914.MP(4).jpg",
        "/tmp/29407C9C-7528-4FF1-AD5F-08EAA7F9738E-98855-000",
      ],
      filesMetadata: [
        "/tmp/3D06C8D1-7637-4625-BEBE-C3D916AEF50D.jpg.suppl.json",
        "/tmp/PXL_20241231_114900266.jpg.supplemental-metada.json",
        "/tmp/PXL_20241231_114910784.MP.jpg.supplemental-met.json",
        "/tmp/camphoto_33463914.jpg.supplemental-metadata(4).json",
        "/tmp/camphoto_33463914.MP.jpg.supplemental-metadata(4).json",
        "/tmp/29407C9C-7528-4FF1-AD5F-08EAA7F9738E-98855-000.json",
      ],
      filesMetadataAlbums: [],
    };

    const { manifest } = link(rawCollections, { fuzzyThreshold: 40 });
    const map = new Map(manifest.map((entry) => [entry.mediaPath, entry]));

    test("should match .suppl.json metadata files", () => {
      const entry = map.get("/tmp/3D06C8D1-7637-4625-BEBE-C3D916AEF50D.jpg");

      // Verify .suppl.json metadata files are matched correctly
      strictEqual(entry.jsonPath, "/tmp/3D06C8D1-7637-4625-BEBE-C3D916AEF50D.jpg.suppl.json");
    });

    test("should match .supplemental-metada.json metadata files", () => {
      const entry = map.get("/tmp/PXL_20241231_114900266.jpg");

      // Verify .supplemental-metada.json files are matched
      strictEqual(entry.jsonPath, "/tmp/PXL_20241231_114900266.jpg.supplemental-metada.json");
    });

    test("should match .supplemental-met.json metadata files with two file extensions", () => {
      const entry = map.get("/tmp/PXL_20241231_114910784.MP.jpg");
      strictEqual(entry.jsonPath, "/tmp/PXL_20241231_114910784.MP.jpg.supplemental-met.json");
    });

    test("should match .supplemental-metadata(N).json with duplicate markers", () => {
      const entry = map.get("/tmp/camphoto_33463914(4).jpg");
      strictEqual(entry.jsonPath, "/tmp/camphoto_33463914.jpg.supplemental-metadata(4).json");
    });

    test("should match .supplemental-metadata(N).json with duplicate markers and two extensions", () => {
      const entry = map.get("/tmp/camphoto_33463914.MP(4).jpg");
      strictEqual(entry.jsonPath, "/tmp/camphoto_33463914.MP.jpg.supplemental-metadata(4).json");
    });

    test("should match filename without extension if the only extension is .json", () => {
      const entry = map.get("/tmp/29407C9C-7528-4FF1-AD5F-08EAA7F9738E-98855-000");
      strictEqual(entry.jsonPath, "/tmp/29407C9C-7528-4FF1-AD5F-08EAA7F9738E-98855-000.json");
    });
  });

  describe("exact matching", () => {
    const rawCollections = {
      filesMedia: ["/tmp/IMG_0076.PNG", "/tmp/IMG_0784.MOV", "/tmp/FA79581F10E4.jpeg"],
      filesMetadata: [
        "/tmp/IMG_0076.PNG.supplemental-metadata.json",
        "/tmp/IMG_0784.MOV.supplemental-metadata.json",
        "/tmp/FA79581F10E4.jpeg..json",
      ],
      filesMetadataAlbums: [],
    };

    const { manifest } = link(rawCollections, { fuzzyThreshold: 40 });
    const map = new Map(manifest.map((entry) => [entry.mediaPath, entry]));

    test("should match exact metadata - IMG_0076.PNG", () => {
      const entry = map.get("/tmp/IMG_0076.PNG");

      // Verify exact metadata match
      strictEqual(entry.jsonPath, "/tmp/IMG_0076.PNG.supplemental-metadata.json");
    });

    test("should match exact metadata - IMG_0784.MOV", () => {
      const entry = map.get("/tmp/IMG_0784.MOV");
      strictEqual(entry.jsonPath, "/tmp/IMG_0784.MOV.supplemental-metadata.json");
    });

    test("should match double-dot extension - FA7958", () => {
      const entry = map.get("/tmp/FA79581F10E4.jpeg");
      strictEqual(entry.jsonPath, "/tmp/FA79581F10E4.jpeg..json");
    });
  });

  describe("truncated filenames (fuzzy matching)", () => {
    const rawCollections = {
      filesMedia: [
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
      filesMetadata: [
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
      filesMetadataAlbums: [],
    };

    // Use fuzzyThreshold: 0 to allow fuzzy matching on short synthetic test names
    const { manifest } = link(rawCollections, { fuzzyThreshold: 0 });
    const map = new Map(manifest.map((entry) => [entry.mediaPath, entry]));

    test("should match truncated metadata - 988555 video", () => {
      const entry = map.get("/tmp/988555-0000.mov");

      // Verify truncated video filename matches
      strictEqual(entry.jsonPath, "/tmp/988555-000.json");
    });

    test("should match truncated metadata - C3D916", () => {
      const entry = map.get("/tmp/C3D916AEF50.jpg");
      strictEqual(entry.jsonPath, "/tmp/C3D916AEF50D.jpg.suppl.json");
    });

    test("should match systematic truncation cases (a-i)", () => {
      // We iterate through the systematic cases to ensure all matched
      const cases = ["a", "b", "c", "d", "e", "f", "g", "h", "i"];
      for (const c of cases) {
        const media = rawCollections.filesMedia.find((f) => f.includes(`/${c}`));
        const metadata = rawCollections.filesMetadata.find((f) => f.includes(`/${c}`));
        const entry = map.get(media);
        ok(entry, `Entry for case ${c} not found`);
        strictEqual(entry.jsonPath, metadata, `Mismatch for case ${c}`);
      }
    });
  });

  describe("duplicate files", () => {
    const rawCollections = {
      filesMedia: ["/tmp/1804928587.jpg", "/tmp/1804928587(1).jpg"],
      filesMetadata: [
        "/tmp/1804928587.jpg.supplemental-metadata.json",
        "/tmp/1804928587.jpg.supplemental-metadata(1).json",
      ],
      filesMetadataAlbums: [],
    };

    const { manifest } = link(rawCollections, { fuzzyThreshold: 40 });
    const map = new Map(manifest.map((entry) => [entry.mediaPath, entry]));

    test("should match duplicate marker - original", () => {
      const entry = map.get("/tmp/1804928587.jpg");

      // Verify original file without duplicate marker matches
      strictEqual(entry.jsonPath, "/tmp/1804928587.jpg.supplemental-metadata.json");
    });

    test("should match duplicate marker - (1)", () => {
      const entry = map.get("/tmp/1804928587(1).jpg");
      strictEqual(entry.jsonPath, "/tmp/1804928587.jpg.supplemental-metadata(1).json");
    });
  });

  describe("distance-based fuzzy matching with duplicate markers", () => {
    const rawCollections = {
      filesMedia: [
        "/tmp/IMG_0449.MP4",
        "/tmp/IMG_0449(1).HEIC",
        "/tmp/IMG_0449(1).MP4",
        "/tmp/IMG_0450.MP4",
        "/tmp/IMG_0450(1).HEIC",
        "/tmp/IMG_0450(1).MP4",
      ],
      filesMetadata: [
        "/tmp/IMG_0449.HEIC.supplemental-metadata.json",
        "/tmp/IMG_0449.HEIC.supplemental-metadata(1).json",
        "/tmp/IMG_0450.HEIC.supplemental-metadata.json",
        "/tmp/IMG_0450.HEIC.supplemental-metadata(1).json",
      ],
      filesMetadataAlbums: [],
    };

    const { manifest } = link(rawCollections, { fuzzyThreshold: 40 });
    const map = new Map(manifest.map((entry) => [entry.mediaPath, entry]));

    test("should match file without marker to metadata without marker - IMG_0449.MP4", () => {
      const entry = map.get("/tmp/IMG_0449.MP4");

      // Verify file without marker matches metadata without marker (distance 0)
      // instead of metadata with (1) marker (distance 3)
      strictEqual(entry.jsonPath, "/tmp/IMG_0449.HEIC.supplemental-metadata.json");
    });

    test("should match file with (1) marker to metadata with (1) marker - IMG_0449(1).HEIC", () => {
      const entry = map.get("/tmp/IMG_0449(1).HEIC");

      // Verify file with marker matches metadata with same marker (distance 0)
      strictEqual(entry.jsonPath, "/tmp/IMG_0449.HEIC.supplemental-metadata(1).json");
    });

    test("should match file with (1) marker to metadata with (1) marker - IMG_0449(1).MP4", () => {
      const entry = map.get("/tmp/IMG_0449(1).MP4");

      // Verify MP4 variant with marker also matches correctly (distance 0)
      strictEqual(entry.jsonPath, "/tmp/IMG_0449.HEIC.supplemental-metadata(1).json");
    });

    test("should match file without marker to metadata without marker - IMG_0450.MP4", () => {
      const entry = map.get("/tmp/IMG_0450.MP4");

      // Verify second example also matches correctly
      strictEqual(entry.jsonPath, "/tmp/IMG_0450.HEIC.supplemental-metadata.json");
    });

    test("should match file with (1) marker to metadata with (1) marker - IMG_0450(1).HEIC", () => {
      const entry = map.get("/tmp/IMG_0450(1).HEIC");

      // Verify second HEIC variant matches correctly
      strictEqual(entry.jsonPath, "/tmp/IMG_0450.HEIC.supplemental-metadata(1).json");
    });

    test("should match file with (1) marker to metadata with (1) marker - IMG_0450(1).MP4", () => {
      const entry = map.get("/tmp/IMG_0450(1).MP4");

      // Verify second MP4 variant matches correctly
      strictEqual(entry.jsonPath, "/tmp/IMG_0450.HEIC.supplemental-metadata(1).json");
    });
  });

  describe("distance threshold prevents false matches", () => {
    const rawCollections = {
      filesMedia: ["/tmp/IMG_0449.MP4", "/tmp/IMG_0449(1).HEIC", "/tmp/IMG_0449(1).MP4"],
      filesMetadata: ["/tmp/IMG_0449.HEIC.supplemental-metadata(1).json"],
      filesMetadataAlbums: [],
    };

    const { manifest } = link(rawCollections, { fuzzyThreshold: 40 });
    const map = new Map(manifest.map((entry) => [entry.mediaPath, entry]));

    test("should NOT match when no corresponding metadata exists - IMG_0449.MP4", () => {
      const entry = map.get("/tmp/IMG_0449.MP4");

      // IMG_0449.MP4 has no corresponding metadata file (only (1) variant exists)
      // Should not match to IMG_0449(1).HEIC metadata (distance would be 3)
      strictEqual(entry.jsonPath, undefined);
    });

    test("should match when corresponding metadata exists - IMG_0449(1).HEIC", () => {
      const entry = map.get("/tmp/IMG_0449(1).HEIC");

      // Verify (1) variant matches correctly
      strictEqual(entry.jsonPath, "/tmp/IMG_0449.HEIC.supplemental-metadata(1).json");
    });

    test("should match when corresponding metadata exists - IMG_0449(1).MP4", () => {
      const entry = map.get("/tmp/IMG_0449(1).MP4");

      // Verify (1) variant MP4 also matches correctly
      strictEqual(entry.jsonPath, "/tmp/IMG_0449.HEIC.supplemental-metadata(1).json");
    });
  });

  describe("edited files", () => {
    const rawCollections = {
      filesMedia: [
        "/tmp/photo.jpg",
        "/tmp/photo-edited.jpg",
        "/tmp/IMG_1234.PNG",
        "/tmp/IMG_1234-edited.PNG",
        "/tmp/IMG_1809 Copy.JPG",
        "/tmp/IMG_1809 Copy-edited.JPG",
        "/tmp/j23456789012345678901234567890123456-edited.jpg",
      ],
      filesMetadata: [
        "/tmp/photo.jpg.json",
        "/tmp/IMG_1234.PNG.json",
        "/tmp/IMG_1809 Copy.JPG.supplemental-metadata.json",
        "/tmp/j2345678901234567890123456789012345678901.jpg.json",
      ],
      filesMetadataAlbums: [],
    };

    const { manifest } = link(rawCollections, { fuzzyThreshold: 40 });
    const map = new Map(manifest.map((entry) => [entry.mediaPath, entry]));

    test("should match photo-edited to original metadata", () => {
      const entry = map.get("/tmp/photo-edited.jpg");

      // Verify edited file matches original metadata
      strictEqual(entry.jsonPath, "/tmp/photo.jpg.json");
    });

    test("should match IMG_1234-edited to original metadata", () => {
      const entry = map.get("/tmp/IMG_1234-edited.PNG");
      strictEqual(entry.jsonPath, "/tmp/IMG_1234.PNG.json");
    });

    test("should match Copy-edited to Copy metadata", () => {
      const entry = map.get("/tmp/IMG_1809 Copy-edited.JPG");
      strictEqual(entry.jsonPath, "/tmp/IMG_1809 Copy.JPG.supplemental-metadata.json");
    });

    test("should match edited file where -edited suffix caused truncation", () => {
      const entry = map.get("/tmp/j23456789012345678901234567890123456-edited.jpg");
      strictEqual(entry.jsonPath, "/tmp/j2345678901234567890123456789012345678901.jpg.json");
    });
  });

  describe("complex extensions & collisions", () => {
    const rawCollections = {
      filesMedia: [
        "/tmp/11491078.MP.jpg",
        "/tmp/11491078.MP",
        "/tmp/IMG_0785.HEIC",
        "/tmp/11491078.MP-edited.jpg",
      ],
      filesMetadata: [
        "/tmp/11491078.MP.jpg.supplemental-met.json",
        "/tmp/IMG_0785.HEIC.supplemental-metadata.json",
      ],
      filesMetadataAlbums: [],
    };

    const { manifest } = link(rawCollections, { fuzzyThreshold: 40 });
    const map = new Map(manifest.map((entry) => [entry.mediaPath, entry]));

    test("should match double extension - .MP.jpg", () => {
      const entry = map.get("/tmp/11491078.MP.jpg");
      strictEqual(entry.jsonPath, "/tmp/11491078.MP.jpg.supplemental-met.json");
    });

    test("should match prefix collision file (.MP) to shared metadata", () => {
      const entry = map.get("/tmp/11491078.MP");
      strictEqual(entry.jsonPath, "/tmp/11491078.MP.jpg.supplemental-met.json");
    });

    test("should match Live Photo HEIC", () => {
      const entry = map.get("/tmp/IMG_0785.HEIC");
      strictEqual(entry.jsonPath, "/tmp/IMG_0785.HEIC.supplemental-metadata.json");
    });

    test("should match edited double extension file", () => {
      const entry = map.get("/tmp/11491078.MP-edited.jpg");
      strictEqual(entry.jsonPath, "/tmp/11491078.MP.jpg.supplemental-met.json");
    });
  });

  describe("album source detection", () => {
    const rawCollections = {
      filesMedia: ["/tmp/My Album/IMG_0076.PNG", "/tmp/Vacation 2024/photo.jpg", "/tmp/loose.jpg"],
      filesMetadata: [],
      filesMetadataAlbums: ["/tmp/My Album/metadata.json", "/tmp/Vacation 2024/metadata.json"],
    };

    const { manifest } = link(rawCollections, { fuzzyThreshold: 40 });
    const map = new Map(manifest.map((entry) => [entry.mediaPath, entry]));

    test("should identify album sources correctly", () => {
      // Verify album sources are identified correctly
      strictEqual(map.get("/tmp/My Album/IMG_0076.PNG").source.type, "album");

      strictEqual(map.get("/tmp/My Album/IMG_0076.PNG").source.name, "My Album");

      strictEqual(map.get("/tmp/Vacation 2024/photo.jpg").source.type, "album");

      strictEqual(map.get("/tmp/Vacation 2024/photo.jpg").source.name, "Vacation 2024");
    });

    test("should identify loose files correctly", () => {
      // Verify loose files are identified correctly
      strictEqual(map.get("/tmp/loose.jpg").source.type, "loose");
    });
  });

  describe("directory isolation", () => {
    const rawCollections = {
      filesMedia: ["/Photos/Vacation.jpg"],
      filesMetadata: ["/Photos/Vacation 2024/IMG_123.json"],
      filesMetadataAlbums: [],
    };

    const { manifest } = link(rawCollections, { fuzzyThreshold: 40 });
    const map = new Map(manifest.map((entry) => [entry.mediaPath, entry]));

    test("should NOT match media to metadata in a sibling directory that shares a prefix", () => {
      const entry = map.get("/Photos/Vacation.jpg");

      // Verify media does not match metadata in sibling directory
      strictEqual(entry.jsonPath, undefined);
    });
  });

  describe("statistics & reporting", () => {
    const rawCollections = {
      filesMedia: ["/tmp/matched.jpg", "/tmp/unmatched.jpg"],
      filesMetadata: ["/tmp/matched.jpg.json", "/tmp/unused.json"],
      filesMetadataAlbums: [],
    };

    const { stats } = link(rawCollections, { fuzzyThreshold: 40 });

    test("should report unmatched media files", () => {
      // Verify unmatched media files are reported
      ok(stats.unmatchedMediaFiles.has("/tmp/unmatched.jpg"));

      strictEqual(stats.unmatchedMediaFiles.size, 1);
    });

    test("should report unmatched metadata files", () => {
      // Verify unmatched metadata files are reported
      ok(stats.unmatchedMetadataFiles.has("/tmp/unused.json"));

      strictEqual(stats.unmatchedMetadataFiles.size, 1);
    });
  });

  describe("extension-specific matching with same base name", () => {
    const rawCollections = {
      filesMedia: ["/tmp/IMG_0267.JPG", "/tmp/IMG_0523.MOV", "/tmp/IMG_0525.PNG"],
      filesMetadata: [
        // HEIC metadata files listed FIRST to test that extension matching
        // prefers exact extension match over first-found match
        "/tmp/IMG_0267.HEIC.supplemental-metadata.json",
        "/tmp/IMG_0267.JPG.supplemental-metadata.json",
        "/tmp/IMG_0523.HEIC.supplemental-metadata.json",
        "/tmp/IMG_0523.MOV.supplemental-metadata.json",
        "/tmp/IMG_0525.HEIC.supplemental-metadata.json",
        "/tmp/IMG_0525.PNG.supplemental-metadata.json",
      ],
      filesMetadataAlbums: [],
    };

    const { manifest, stats } = link(rawCollections, { fuzzyThreshold: 40 });
    const map = new Map(manifest.map((entry) => [entry.mediaPath, entry]));

    test("should match JPG media to JPG metadata, not HEIC metadata", () => {
      const entry = map.get("/tmp/IMG_0267.JPG");

      // Verify JPG file matches JPG-specific metadata, not HEIC metadata
      strictEqual(entry.jsonPath, "/tmp/IMG_0267.JPG.supplemental-metadata.json");
    });

    test("should match MOV media to MOV metadata, not HEIC metadata", () => {
      const entry = map.get("/tmp/IMG_0523.MOV");

      // Verify MOV file matches MOV-specific metadata
      strictEqual(entry.jsonPath, "/tmp/IMG_0523.MOV.supplemental-metadata.json");
    });

    test("should match PNG media to PNG metadata, not HEIC metadata", () => {
      const entry = map.get("/tmp/IMG_0525.PNG");

      // Verify PNG file matches PNG-specific metadata
      strictEqual(entry.jsonPath, "/tmp/IMG_0525.PNG.supplemental-metadata.json");
    });

    test("should leave HEIC metadata files unmatched when no HEIC media exists", () => {
      // Verify HEIC metadata files are reported as unmatched
      ok(stats.unmatchedMetadataFiles.has("/tmp/IMG_0267.HEIC.supplemental-metadata.json"));

      ok(stats.unmatchedMetadataFiles.has("/tmp/IMG_0523.HEIC.supplemental-metadata.json"));

      ok(stats.unmatchedMetadataFiles.has("/tmp/IMG_0525.HEIC.supplemental-metadata.json"));

      strictEqual(stats.unmatchedMetadataFiles.size, 3);
    });
  });

  describe("safety against false positives", () => {
    const rawCollections = {
      filesMedia: ["/tmp/IMG_123.jpg", "/tmp/IMG_1234.jpg"],
      filesMetadata: ["/tmp/IMG_123.json"],
      filesMetadataAlbums: [],
    };

    const { manifest } = link(rawCollections, { fuzzyThreshold: 40 });
    const map = new Map(manifest.map((e) => [e.mediaPath, e]));

    test("should match exact short name", () => {
      const entry = map.get("/tmp/IMG_123.jpg");
      strictEqual(entry.jsonPath, "/tmp/IMG_123.json");
    });

    test("should NOT fuzzy match short names that share a prefix", () => {
      // IMG_1234 starts with IMG_123, but is too short to be a Google truncation.
      // Therefore, it should NOT claim IMG_123.json.
      const entry = map.get("/tmp/IMG_1234.jpg");
      strictEqual(entry.jsonPath, undefined);
    });
  });

  describe("truncated -edited suffixes", () => {
    const rawCollections = {
      filesMedia: [
        "/tmp/IMG_100-edited.jpg",
        "/tmp/IMG_200-edite.jpg", // Truncated d
        "/tmp/IMG_300-edit.jpg", // Truncated ed
        "/tmp/IMG_400-edi.jpg", // Truncated ted
        "/tmp/IMG_500.MP-edited.jpg", // Stacked extension + edited
      ],
      filesMetadata: [
        "/tmp/IMG_100.json",
        "/tmp/IMG_200.json",
        "/tmp/IMG_300.json",
        "/tmp/IMG_400.json",
        "/tmp/IMG_500.MP.jpg.json",
      ],
      filesMetadataAlbums: [],
    };

    const { manifest } = link(rawCollections, { fuzzyThreshold: 40 });
    const map = new Map(manifest.map((e) => [e.mediaPath, e]));

    test("should match full -edited suffix", () => {
      const entry = map.get("/tmp/IMG_100-edited.jpg");
      strictEqual(entry.jsonPath, "/tmp/IMG_100.json");
    });

    test("should match truncated -edite suffix", () => {
      const entry = map.get("/tmp/IMG_200-edite.jpg");
      strictEqual(entry.jsonPath, "/tmp/IMG_200.json");
    });

    test("should match truncated -edit suffix", () => {
      const entry = map.get("/tmp/IMG_300-edit.jpg");
      strictEqual(entry.jsonPath, "/tmp/IMG_300.json");
    });

    test("should match truncated -edi suffix", () => {
      const entry = map.get("/tmp/IMG_400-edi.jpg");
      strictEqual(entry.jsonPath, "/tmp/IMG_400.json");
    });

    test("should match -edited with embedded extension", () => {
      // Logic:
      // 1. parseMedia parses "IMG_500.MP-edited" -> "IMG_500.MP" (strips -edited)
      // 2. parseMetadata parses "IMG_500.MP"
      // 3. Match!
      const entry = map.get("/tmp/IMG_500.MP-edited.jpg");
      strictEqual(entry.jsonPath, "/tmp/IMG_500.MP.jpg.json");
    });
  });

  describe("truncated Live Photo with shared sidecar", () => {
    const rawCollections = {
      filesMedia: [
        "/tmp/3D06C8D1-7637-4625-BEBE-C3D916AEF50D.mp4",
        "/tmp/3D06C8D1-7637-4625-BEBE-C3D916AEF50.heic", // truncated by 1 char
      ],
      filesMetadata: ["/tmp/3D06C8D1-7637-4625-BEBE-C3D916AEF50D.json"],
      filesMetadataAlbums: [],
    };

    // Use fuzzyThreshold: 0 because the UUID is only 35 chars (under 40 threshold)
    const { manifest } = link(rawCollections, { fuzzyThreshold: 0 });
    const map = new Map(manifest.map((entry) => [entry.mediaPath, entry]));

    test("should match exact mp4 to sidecar", () => {
      const entry = map.get("/tmp/3D06C8D1-7637-4625-BEBE-C3D916AEF50D.mp4");

      // Verify exact match works
      strictEqual(entry.jsonPath, "/tmp/3D06C8D1-7637-4625-BEBE-C3D916AEF50D.json");
    });

    test("should match truncated heic to same sidecar", () => {
      const entry = map.get("/tmp/3D06C8D1-7637-4625-BEBE-C3D916AEF50.heic");

      // Verify truncated Live Photo component also matches the shared sidecar
      // This tests that fuzzy matches can share sidecars claimed by exact matches
      strictEqual(entry.jsonPath, "/tmp/3D06C8D1-7637-4625-BEBE-C3D916AEF50D.json");
    });
  });
});
