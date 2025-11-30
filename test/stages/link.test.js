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
        "/tmp/camphoto_33463914(4).MP.jpg",
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

    const { manifest } = link(rawCollections);
    const map = new Map(manifest.map((entry) => [entry.mediaPath, entry]));

    test("should match .suppl.json metadata files", () => {
      const entry = map.get("/tmp/3D06C8D1-7637-4625-BEBE-C3D916AEF50D.jpg");
      strictEqual(entry.jsonPath, "/tmp/3D06C8D1-7637-4625-BEBE-C3D916AEF50D.jpg.suppl.json");
    });

    test("should match .supplemental-metada.json metadata files", () => {
      const entry = map.get("/tmp/PXL_20241231_114900266.jpg");
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
      const entry = map.get("/tmp/camphoto_33463914(4).MP.jpg");
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

    const { manifest } = link(rawCollections);
    const map = new Map(manifest.map((entry) => [entry.mediaPath, entry]));

    test("should match exact metadata - IMG_0076.PNG", () => {
      const entry = map.get("/tmp/IMG_0076.PNG");
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

    const { manifest } = link(rawCollections);
    const map = new Map(manifest.map((entry) => [entry.mediaPath, entry]));

    test("should match truncated metadata - 988555 video", () => {
      const entry = map.get("/tmp/988555-0000.mov");
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

    const { manifest } = link(rawCollections);
    const map = new Map(manifest.map((entry) => [entry.mediaPath, entry]));

    test("should match duplicate marker - original", () => {
      const entry = map.get("/tmp/1804928587.jpg");
      strictEqual(entry.jsonPath, "/tmp/1804928587.jpg.supplemental-metadata.json");
    });

    test("should match duplicate marker - (1)", () => {
      const entry = map.get("/tmp/1804928587(1).jpg");
      strictEqual(entry.jsonPath, "/tmp/1804928587.jpg.supplemental-metadata(1).json");
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

    const { manifest } = link(rawCollections);
    const map = new Map(manifest.map((entry) => [entry.mediaPath, entry]));

    test("should match photo-edited to original metadata", () => {
      const entry = map.get("/tmp/photo-edited.jpg");
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
        "/tmp/11491078-edited.MP.jpg",
      ],
      filesMetadata: [
        "/tmp/11491078.MP.jpg.supplemental-met.json",
        "/tmp/IMG_0785.HEIC.supplemental-metadata.json",
      ],
      filesMetadataAlbums: [],
    };

    const { manifest } = link(rawCollections);
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
      const entry = map.get("/tmp/11491078-edited.MP.jpg");
      strictEqual(entry.jsonPath, "/tmp/11491078.MP.jpg.supplemental-met.json");
    });
  });

  describe("album source detection", () => {
    const rawCollections = {
      filesMedia: ["/tmp/My Album/IMG_0076.PNG", "/tmp/Vacation 2024/photo.jpg", "/tmp/loose.jpg"],
      filesMetadata: [],
      filesMetadataAlbums: ["/tmp/My Album/metadata.json", "/tmp/Vacation 2024/metadata.json"],
    };

    const { manifest } = link(rawCollections);
    const map = new Map(manifest.map((entry) => [entry.mediaPath, entry]));

    test("should identify album sources correctly", () => {
      strictEqual(map.get("/tmp/My Album/IMG_0076.PNG").source.type, "album");
      strictEqual(map.get("/tmp/My Album/IMG_0076.PNG").source.name, "My Album");

      strictEqual(map.get("/tmp/Vacation 2024/photo.jpg").source.type, "album");
      strictEqual(map.get("/tmp/Vacation 2024/photo.jpg").source.name, "Vacation 2024");
    });

    test("should identify loose files correctly", () => {
      strictEqual(map.get("/tmp/loose.jpg").source.type, "loose");
    });
  });

  describe("directory isolation", () => {
    const rawCollections = {
      filesMedia: ["/Photos/Vacation.jpg"],
      filesMetadata: ["/Photos/Vacation 2024/IMG_123.json"],
      filesMetadataAlbums: [],
    };

    const { manifest } = link(rawCollections);
    const map = new Map(manifest.map((entry) => [entry.mediaPath, entry]));

    test("should NOT match media to metadata in a sibling directory that shares a prefix", () => {
      const entry = map.get("/Photos/Vacation.jpg");
      strictEqual(entry.jsonPath, undefined);
    });
  });

  describe("statistics & reporting", () => {
    const rawCollections = {
      filesMedia: ["/tmp/matched.jpg", "/tmp/unmatched.jpg"],
      filesMetadata: ["/tmp/matched.jpg.json", "/tmp/unused.json"],
      filesMetadataAlbums: [],
    };

    const { stats } = link(rawCollections);

    test("should report unmatched media files", () => {
      ok(stats.unmatchedMediaFiles.has("/tmp/unmatched.jpg"));
      strictEqual(stats.unmatchedMediaFiles.size, 1);
    });

    test("should report unmatched metadata files", () => {
      ok(stats.unmatchedMetadataFiles.has("/tmp/unused.json"));
      strictEqual(stats.unmatchedMetadataFiles.size, 1);
    });
  });
});
