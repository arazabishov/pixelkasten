import { test, describe } from "node:test";
import { strictEqual, ok } from "node:assert";
import { getNormalizedMetadataName, link } from "../src/stages/link.js";

describe("normalizeMetadataName", () => {
  test("should normalize .suppl.json metadata files", () => {
    const result = getNormalizedMetadataName("3D06C8D1-7637-4625-BEBE-C3D916AEF50D.jpg.suppl.json");
    strictEqual(result, "3D06C8D1-7637-4625-BEBE-C3D916AEF50D.jpg");
  });

  test("should normalize .supplemental-metada.json metadata files", () => {
    const result = getNormalizedMetadataName("PXL_20241231_114900266.jpg.supplemental-metada.json");
    strictEqual(result, "PXL_20241231_114900266.jpg");
  });

  test("should normalize .supplemental-met.json metadata files with two file extensions", () => {
    const result = getNormalizedMetadataName("PXL_20241231_114910784.MP.jpg.supplemental-met.json");
    strictEqual(result, "PXL_20241231_114910784.MP.jpg");
  });

  test("should normalize .supplemental-metadata(N).json with duplicate markers", () => {
    const result = getNormalizedMetadataName("camphoto_33463914.jpg.supplemental-metadata(4).json");
    strictEqual(result, "camphoto_33463914(4).jpg");
  });

  test("should normalize .supplemental-metadata(N).json with duplicate markers and two extensions", () => {
    const result = getNormalizedMetadataName(
      "camphoto_33463914.MP.jpg.supplemental-metadata(4).json"
    );
    strictEqual(result, "camphoto_33463914(4).MP.jpg");
  });

  test("should normalize .(N).json with duplicate markers", () => {
    const result = getNormalizedMetadataName("camphoto_33463914.jpg.(4).json");
    strictEqual(result, "camphoto_33463914(4).jpg");
  });

  test("should return original file name if file name has no extensions", () => {
    const result = getNormalizedMetadataName("camphoto_33463914");
    strictEqual(result, "camphoto_33463914");
  });

  test("should return original file name if file extension is not .json", () => {
    const result = getNormalizedMetadataName("PXL_20241231_114900266.jpg");
    strictEqual(result, "PXL_20241231_114900266.jpg");
  });

  test("should return filename without extension if the only extension is .json", () => {
    const result = getNormalizedMetadataName("29407C9C-7528-4FF1-AD5F-08EAA7F9738E-98855-000.json");
    strictEqual(result, "29407C9C-7528-4FF1-AD5F-08EAA7F9738E-98855-000");
  });

  test("should return an empty string if empty string is provided", () => {
    const result = getNormalizedMetadataName("");
    strictEqual(result, "");
  });

  test("should return undefined if undefined is supplied", () => {
    const result = getNormalizedMetadataName(undefined);
    strictEqual(result, undefined);
  });
});

describe("link", () => {
  const rawCollections = {
    filesMedia: [
      "/temporary/directory/IMG_0076.PNG",
      "/temporary/directory/IMG_0784.MOV",
      "/temporary/directory/988555-0000.mov",
      "/temporary/directory/C3D916AEF50.jpg",
      "/temporary/directory/1804928587.jpg",
      "/temporary/directory/1804928587(1).jpg",
      "/temporary/directory/11491078.MP.jpg",
      "/temporary/directory/FA79581F10E4.jpeg",
      "/temporary/directory/IMG_0785.HEIC",
      // "/temporary/directory/IMG_0785.MP4",
      "/temporary/directory/IMG_0792.MP4",
      "/temporary/directory/11491078.MP",
      "/temporary/directory/IMG_0076-edited.PNG",
      "/temporary/directory/PXL_202501-edited.jpg",
      "/temporary/directory/11491078-edited.MP.jpg",
    ],
    filesMetadata: [
      "/temporary/directory/IMG_0076.PNG.supplemental-metadata.json",
      "/temporary/directory/IMG_0784.MOV.supplemental-metadata.json",
      "/temporary/directory/988555-000.json",
      "/temporary/directory/C3D916AEF50D.jpg.suppl.json",
      "/temporary/directory/1804928587.jpg.supplemental-metadata.json",
      "/temporary/directory/1804928587.jpg.supplemental-metadata(1).json",
      "/temporary/directory/11491078.MP.jpg.supplemental-met.json",
      "/temporary/directory/FA79581F10E4.jpeg..json",
      "/temporary/directory/IMG_0785.HEIC.supplemental-metadata.json",
      "/temporary/directory/PXL_202501.jpg.json",
    ],
    filesMetadataAlbums: [],
  };

  const result = new Map(link(rawCollections).manifest.map((entry) => [entry.mediaPath, entry]));

  test("should return correct total number of media entries", () => {
    strictEqual(result.size, 14);
  });

  test("should match exact metadata - IMG_0076.PNG", () => {
    const entry = result.get("/temporary/directory/IMG_0076.PNG");
    ok(entry);
    strictEqual(entry.mediaPath, "/temporary/directory/IMG_0076.PNG");
    strictEqual(entry.jsonPath, "/temporary/directory/IMG_0076.PNG.supplemental-metadata.json");
    strictEqual(entry.source.type, "loose");
  });

  test("should match exact metadata - IMG_0784.MOV", () => {
    const entry = result.get("/temporary/directory/IMG_0784.MOV");
    ok(entry);
    strictEqual(entry.mediaPath, "/temporary/directory/IMG_0784.MOV");
    strictEqual(entry.jsonPath, "/temporary/directory/IMG_0784.MOV.supplemental-metadata.json");
    strictEqual(entry.source.type, "loose");
  });

  test("should match truncated metadata - 988555 video", () => {
    const entry = result.get("/temporary/directory/988555-0000.mov");
    ok(entry);
    strictEqual(entry.mediaPath, "/temporary/directory/988555-0000.mov");
    strictEqual(entry.jsonPath, "/temporary/directory/988555-000.json");
    strictEqual(entry.source.type, "loose");
  });

  test("should match truncated metadata - C3D916", () => {
    const entry = result.get("/temporary/directory/C3D916AEF50.jpg");
    ok(entry);
    strictEqual(entry.mediaPath, "/temporary/directory/C3D916AEF50.jpg");
    strictEqual(entry.jsonPath, "/temporary/directory/C3D916AEF50D.jpg.suppl.json");
    strictEqual(entry.source.type, "loose");
  });

  test("should match duplicate marker - original", () => {
    const entry = result.get("/temporary/directory/1804928587.jpg");
    ok(entry);
    strictEqual(entry.mediaPath, "/temporary/directory/1804928587.jpg");
    strictEqual(entry.jsonPath, "/temporary/directory/1804928587.jpg.supplemental-metadata.json");
    strictEqual(entry.source.type, "loose");
  });

  test("should match duplicate marker - (1)", () => {
    const entry = result.get("/temporary/directory/1804928587(1).jpg");
    ok(entry);
    strictEqual(entry.mediaPath, "/temporary/directory/1804928587(1).jpg");
    strictEqual(
      entry.jsonPath,
      "/temporary/directory/1804928587.jpg.supplemental-metadata(1).json"
    );
    strictEqual(entry.source.type, "loose");
  });

  test("should match double extension - .MP.jpg", () => {
    const entry = result.get("/temporary/directory/11491078.MP.jpg");
    ok(entry);
    strictEqual(entry.mediaPath, "/temporary/directory/11491078.MP.jpg");
    strictEqual(entry.jsonPath, "/temporary/directory/11491078.MP.jpg.supplemental-met.json");
    strictEqual(entry.source.type, "loose");
  });

  test("should match double-dot extension - FA7958", () => {
    const entry = result.get("/temporary/directory/FA79581F10E4.jpeg");
    ok(entry);
    strictEqual(entry.mediaPath, "/temporary/directory/FA79581F10E4.jpeg");
    strictEqual(entry.jsonPath, "/temporary/directory/FA79581F10E4.jpeg..json");
    strictEqual(entry.source.type, "loose");
  });

  test("should match Live Photo pairs separately - HEIC with metadata", () => {
    const heic = result.get("/temporary/directory/IMG_0785.HEIC");
    ok(heic);
    strictEqual(heic.mediaPath, "/temporary/directory/IMG_0785.HEIC");
    strictEqual(heic.jsonPath, "/temporary/directory/IMG_0785.HEIC.supplemental-metadata.json");
    strictEqual(heic.source.type, "loose");
  });

  // test("should match Live Photo pairs separately - MP4 without metadata", () => {
  //   const mp4 = result.get("/temporary/directory/IMG_0785.MP4");
  //   ok(mp4);
  //   strictEqual(mp4.mediaPath, "/temporary/directory/IMG_0785.MP4");
  //   strictEqual(mp4.jsonPath, undefined);
  //   strictEqual(mp4.source.type, "loose");
  // });

  test("should include orphan media - IMG_0792.MP4", () => {
    const entry = result.get("/temporary/directory/IMG_0792.MP4");
    ok(entry);
    strictEqual(entry.mediaPath, "/temporary/directory/IMG_0792.MP4");
    strictEqual(entry.jsonPath, undefined);
    strictEqual(entry.source.type, "loose");
  });

  test("should match 11491078.MP to shared 11491078.MP.jpg metadata", () => {
    const entry = result.get("/temporary/directory/11491078.MP");
    ok(entry);
    strictEqual(entry.mediaPath, "/temporary/directory/11491078.MP");
    strictEqual(entry.jsonPath, "/temporary/directory/11491078.MP.jpg.supplemental-met.json");
    strictEqual(entry.source.type, "loose");
  });

  test("should match edited PNG to original metadata", () => {
    const entry = result.get("/temporary/directory/IMG_0076-edited.PNG");
    ok(entry);
    strictEqual(entry.mediaPath, "/temporary/directory/IMG_0076-edited.PNG");
    strictEqual(entry.jsonPath, "/temporary/directory/IMG_0076.PNG.supplemental-metadata.json");
    strictEqual(entry.source.type, "loose");
  });

  test("should match edited PXL photo to original metadata", () => {
    const entry = result.get("/temporary/directory/PXL_202501-edited.jpg");
    ok(entry);
    strictEqual(entry.mediaPath, "/temporary/directory/PXL_202501-edited.jpg");
    strictEqual(entry.jsonPath, "/temporary/directory/PXL_202501.jpg.json");
    strictEqual(entry.source.type, "loose");
  });

  test("should match edited double extension file to original metadata", () => {
    const entry = result.get("/temporary/directory/11491078-edited.MP.jpg");
    ok(entry);
    strictEqual(entry.mediaPath, "/temporary/directory/11491078-edited.MP.jpg");
    strictEqual(entry.jsonPath, "/temporary/directory/11491078.MP.jpg.supplemental-met.json");
    strictEqual(entry.source.type, "loose");
  });
});

describe("link with albums", () => {
  const rawCollections = {
    filesMedia: [
      "/temporary/directory/My Album/IMG_0076.PNG",
      "/temporary/directory/My Album/IMG_0784.MOV",
      "/temporary/directory/Vacation 2024/photo.jpg",
    ],
    filesMetadata: [
      "/temporary/directory/My Album/IMG_0076.PNG.supplemental-metadata.json",
      "/temporary/directory/My Album/IMG_0784.MOV.supplemental-metadata.json",
      "/temporary/directory/Vacation 2024/photo.jpg.json",
    ],
    filesMetadataAlbums: [
      "/temporary/directory/My Album/metadata.json",
      "/temporary/directory/Vacation 2024/metadata.json",
    ],
  };

  const result = new Map(link(rawCollections).manifest.map((entry) => [entry.mediaPath, entry]));

  test("should identify album sources correctly", () => {
    const entry1 = result.get("/temporary/directory/My Album/IMG_0076.PNG");
    ok(entry1);
    strictEqual(entry1.source.type, "album");
    strictEqual(entry1.source.name, "My Album");

    const entry2 = result.get("/temporary/directory/Vacation 2024/photo.jpg");
    ok(entry2);
    strictEqual(entry2.source.type, "album");
    strictEqual(entry2.source.name, "Vacation 2024");
  });
});

describe("link with truncated filenames", () => {
  const rawCollections = {
    filesMedia: [
      "/temporary/directory/a2345678901234567890123456789012345678901.jpg",
      "/temporary/directory/b23456789012345678901234567890123456789012.jpg",
      "/temporary/directory/c234567890123456789012345678901234567890123.jpg",
      "/temporary/directory/d2345678901234567890123456789012345678901234.jpg",
      "/temporary/directory/e23456789012345678901234567890123456789012345.jpg",
      "/temporary/directory/f234567890123456789012345678901234567890123456.jpg",
      "/temporary/directory/g2345678901234567890123456789012345678901234567.jpg",
      "/temporary/directory/h2345678901234567890123456789012345678901234567.jpg",
      "/temporary/directory/i2345678901234567890123456789012345678901234567.jpg",
    ],
    filesMetadata: [
      "/temporary/directory/a2345678901234567890123456789012345678901.jpg.json",
      "/temporary/directory/b23456789012345678901234567890123456789012.jpg.json",
      "/temporary/directory/c234567890123456789012345678901234567890123.jp.json",
      "/temporary/directory/d2345678901234567890123456789012345678901234.j.json",
      "/temporary/directory/e23456789012345678901234567890123456789012345..json",
      "/temporary/directory/f234567890123456789012345678901234567890123456.json",
      "/temporary/directory/g234567890123456789012345678901234567890123456.json",
      "/temporary/directory/h234567890123456789012345678901234567890123456.json",
      "/temporary/directory/i234567890123456789012345678901234567890123456.json",
    ],
    filesMetadataAlbums: [],
  };

  const result = new Map(link(rawCollections).manifest.map((entry) => [entry.mediaPath, entry]));

  test("should return correct total number of media entries", () => {
    strictEqual(result.size, 9);
  });

  test("should match exact filename - a2345678901234567890123456789012345678901.jpg", () => {
    const entry = result.get("/temporary/directory/a2345678901234567890123456789012345678901.jpg");
    ok(entry);
    strictEqual(
      entry.mediaPath,
      "/temporary/directory/a2345678901234567890123456789012345678901.jpg"
    );
    strictEqual(
      entry.jsonPath,
      "/temporary/directory/a2345678901234567890123456789012345678901.jpg.json"
    );
    strictEqual(entry.source.type, "loose");
  });

  test("should match exact filename - b23456789012345678901234567890123456789012.jpg", () => {
    const entry = result.get("/temporary/directory/b23456789012345678901234567890123456789012.jpg");
    ok(entry);
    strictEqual(
      entry.mediaPath,
      "/temporary/directory/b23456789012345678901234567890123456789012.jpg"
    );
    strictEqual(
      entry.jsonPath,
      "/temporary/directory/b23456789012345678901234567890123456789012.jpg.json"
    );
    strictEqual(entry.source.type, "loose");
  });

  test("should match truncated metadata - c234567890123456789012345678901234567890123.jp.json", () => {
    const entry = result.get(
      "/temporary/directory/c234567890123456789012345678901234567890123.jpg"
    );
    ok(entry);
    strictEqual(
      entry.mediaPath,
      "/temporary/directory/c234567890123456789012345678901234567890123.jpg"
    );
    strictEqual(
      entry.jsonPath,
      "/temporary/directory/c234567890123456789012345678901234567890123.jp.json"
    );
    strictEqual(entry.source.type, "loose");
  });

  test("should match truncated metadata - d2345678901234567890123456789012345678901234.j.json", () => {
    const entry = result.get(
      "/temporary/directory/d2345678901234567890123456789012345678901234.jpg"
    );
    ok(entry);
    strictEqual(
      entry.mediaPath,
      "/temporary/directory/d2345678901234567890123456789012345678901234.jpg"
    );
    strictEqual(
      entry.jsonPath,
      "/temporary/directory/d2345678901234567890123456789012345678901234.j.json"
    );
    strictEqual(entry.source.type, "loose");
  });

  test("should match truncated metadata with double-dot - e23456789012345678901234567890123456789012345..json", () => {
    const entry = result.get(
      "/temporary/directory/e23456789012345678901234567890123456789012345.jpg"
    );
    ok(entry);
    strictEqual(
      entry.mediaPath,
      "/temporary/directory/e23456789012345678901234567890123456789012345.jpg"
    );
    strictEqual(
      entry.jsonPath,
      "/temporary/directory/e23456789012345678901234567890123456789012345..json"
    );
    strictEqual(entry.source.type, "loose");
  });

  test("should match truncated media filename - f234567890123456789012345678901234567890123456.json", () => {
    const entry = result.get(
      "/temporary/directory/f234567890123456789012345678901234567890123456.jpg"
    );
    ok(entry);
    strictEqual(
      entry.mediaPath,
      "/temporary/directory/f234567890123456789012345678901234567890123456.jpg"
    );
    strictEqual(
      entry.jsonPath,
      "/temporary/directory/f234567890123456789012345678901234567890123456.json"
    );
    strictEqual(entry.source.type, "loose");
  });

  test("should match truncated media filename - g234567890123456789012345678901234567890123456.json", () => {
    const entry = result.get(
      "/temporary/directory/g2345678901234567890123456789012345678901234567.jpg"
    );
    ok(entry);
    strictEqual(
      entry.mediaPath,
      "/temporary/directory/g2345678901234567890123456789012345678901234567.jpg"
    );
    strictEqual(
      entry.jsonPath,
      "/temporary/directory/g234567890123456789012345678901234567890123456.json"
    );
    strictEqual(entry.source.type, "loose");
  });

  test("should match truncated media filename - h234567890123456789012345678901234567890123456.json", () => {
    const entry = result.get(
      "/temporary/directory/h2345678901234567890123456789012345678901234567.jpg"
    );
    ok(entry);
    strictEqual(
      entry.mediaPath,
      "/temporary/directory/h2345678901234567890123456789012345678901234567.jpg"
    );
    strictEqual(
      entry.jsonPath,
      "/temporary/directory/h234567890123456789012345678901234567890123456.json"
    );
    strictEqual(entry.source.type, "loose");
  });

  test("should match truncated media filename - i234567890123456789012345678901234567890123456.json", () => {
    const entry = result.get(
      "/temporary/directory/i2345678901234567890123456789012345678901234567.jpg"
    );
    ok(entry);
    strictEqual(
      entry.mediaPath,
      "/temporary/directory/i2345678901234567890123456789012345678901234567.jpg"
    );
    strictEqual(
      entry.jsonPath,
      "/temporary/directory/i234567890123456789012345678901234567890123456.json"
    );
    strictEqual(entry.source.type, "loose");
  });
});

describe("link with truncated filenames and edited suffix", () => {
  const rawCollections = {
    filesMedia: [
      "/temporary/directory/j23456789012345678901234567890123456-edited.jpg",
      "/temporary/directory/k2345678901234567890123456789012345678-edited.jpg",
      "/temporary/directory/l234567890123456789012345678901234567890-edited.jpg",
      "/temporary/directory/m23456789012345678901234567890123456789-edited.jpg",
    ],
    filesMetadata: [
      "/temporary/directory/j2345678901234567890123456789012345678901.jpg.json",
      "/temporary/directory/k234567890123456789012345678901234567890123.jpg.json",
      "/temporary/directory/l23456789012345678901234567890123456789012.jpg.json",
      "/temporary/directory/m2345678901234567890123456789012345678901.jpg.json",
    ],
    filesMetadataAlbums: [],
  };

  const result = new Map(link(rawCollections).manifest.map((entry) => [entry.mediaPath, entry]));

  test("should return correct total number of media entries", () => {
    strictEqual(result.size, 4);
  });

  test("should match edited file where -edited suffix caused truncation - j case", () => {
    const entry = result.get(
      "/temporary/directory/j23456789012345678901234567890123456-edited.jpg"
    );
    ok(entry);
    strictEqual(
      entry.mediaPath,
      "/temporary/directory/j23456789012345678901234567890123456-edited.jpg"
    );
    strictEqual(
      entry.jsonPath,
      "/temporary/directory/j2345678901234567890123456789012345678901.jpg.json"
    );
    strictEqual(entry.source.type, "loose");
  });

  test("should match edited file where -edited suffix caused truncation - k case", () => {
    const entry = result.get(
      "/temporary/directory/k2345678901234567890123456789012345678-edited.jpg"
    );
    ok(entry);
    strictEqual(
      entry.mediaPath,
      "/temporary/directory/k2345678901234567890123456789012345678-edited.jpg"
    );
    strictEqual(
      entry.jsonPath,
      "/temporary/directory/k234567890123456789012345678901234567890123.jpg.json"
    );
    strictEqual(entry.source.type, "loose");
  });

  test("should match edited file where -edited suffix caused truncation - l case", () => {
    const entry = result.get(
      "/temporary/directory/l234567890123456789012345678901234567890-edited.jpg"
    );
    ok(entry);
    strictEqual(
      entry.mediaPath,
      "/temporary/directory/l234567890123456789012345678901234567890-edited.jpg"
    );
    strictEqual(
      entry.jsonPath,
      "/temporary/directory/l23456789012345678901234567890123456789012.jpg.json"
    );
    strictEqual(entry.source.type, "loose");
  });

  test("should match edited file where -edited suffix caused truncation - m case", () => {
    const entry = result.get(
      "/temporary/directory/m23456789012345678901234567890123456789-edited.jpg"
    );
    ok(entry);
    strictEqual(
      entry.mediaPath,
      "/temporary/directory/m23456789012345678901234567890123456789-edited.jpg"
    );
    strictEqual(
      entry.jsonPath,
      "/temporary/directory/m2345678901234567890123456789012345678901.jpg.json"
    );
    strictEqual(entry.source.type, "loose");
  });
});

describe("link with -edited suffix", () => {
  const rawCollections = {
    filesMedia: [
      "/temporary/directory/photo.jpg",
      "/temporary/directory/photo-edited.jpg",
      "/temporary/directory/IMG_1234.PNG",
      "/temporary/directory/IMG_1234-edited.PNG",
    ],
    filesMetadata: [
      "/temporary/directory/photo.jpg.json",
      "/temporary/directory/IMG_1234.PNG.json",
    ],
    filesMetadataAlbums: [],
  };

  const result = new Map(link(rawCollections).manifest.map((entry) => [entry.mediaPath, entry]));

  test("should return correct total number of media entries", () => {
    strictEqual(result.size, 4);
  });

  test("should match original photo to its metadata", () => {
    const entry = result.get("/temporary/directory/photo.jpg");
    ok(entry);
    strictEqual(entry.mediaPath, "/temporary/directory/photo.jpg");
    strictEqual(entry.jsonPath, "/temporary/directory/photo.jpg.json");
    strictEqual(entry.source.type, "loose");
  });

  test("should match photo-edited to original metadata when original exists", () => {
    const entry = result.get("/temporary/directory/photo-edited.jpg");
    ok(entry);
    strictEqual(entry.mediaPath, "/temporary/directory/photo-edited.jpg");
    strictEqual(entry.jsonPath, "/temporary/directory/photo.jpg.json");
    strictEqual(entry.source.type, "loose");
  });

  test("should match original IMG_1234 to its metadata", () => {
    const entry = result.get("/temporary/directory/IMG_1234.PNG");
    ok(entry);
    strictEqual(entry.mediaPath, "/temporary/directory/IMG_1234.PNG");
    strictEqual(entry.jsonPath, "/temporary/directory/IMG_1234.PNG.json");
    strictEqual(entry.source.type, "loose");
  });

  test("should match IMG_1234-edited to original metadata when original exists", () => {
    const entry = result.get("/temporary/directory/IMG_1234-edited.PNG");
    ok(entry);
    strictEqual(entry.mediaPath, "/temporary/directory/IMG_1234-edited.PNG");
    strictEqual(entry.jsonPath, "/temporary/directory/IMG_1234.PNG.json");
    strictEqual(entry.source.type, "loose");
  });
});

describe("link with Copy and Copy-edited files", () => {
  const rawCollections = {
    filesMedia: [
      "/temporary/directory/IMG_1809 Copy Copy.JPG",
      "/temporary/directory/IMG_1809.HEIC",
      "/temporary/directory/IMG_1809 Copy-edited.JPG",
      "/temporary/directory/IMG_1809 Copy.JPG",
    ],
    filesMetadata: [
      "/temporary/directory/IMG_1809 Copy.JPG.supplemental-metadata.json",
      "/temporary/directory/IMG_1809 Copy Copy.JPG.supplemental-metadata.json",
      "/temporary/directory/IMG_1809.HEIC.supplemental-metadata.json",
    ],
    filesMetadataAlbums: [],
  };

  const result = new Map(link(rawCollections).manifest.map((entry) => [entry.mediaPath, entry]));

  test("should return correct total number of media entries", () => {
    strictEqual(result.size, 4);
  });

  test("should match IMG_1809 Copy Copy.JPG to its metadata", () => {
    const entry = result.get("/temporary/directory/IMG_1809 Copy Copy.JPG");
    ok(entry);
    strictEqual(entry.mediaPath, "/temporary/directory/IMG_1809 Copy Copy.JPG");
    strictEqual(
      entry.jsonPath,
      "/temporary/directory/IMG_1809 Copy Copy.JPG.supplemental-metadata.json"
    );
    strictEqual(entry.source.type, "loose");
  });

  test("should match IMG_1809.HEIC to its metadata", () => {
    const entry = result.get("/temporary/directory/IMG_1809.HEIC");
    ok(entry);
    strictEqual(entry.mediaPath, "/temporary/directory/IMG_1809.HEIC");
    strictEqual(entry.jsonPath, "/temporary/directory/IMG_1809.HEIC.supplemental-metadata.json");
    strictEqual(entry.source.type, "loose");
  });

  test("should match IMG_1809 Copy-edited.JPG to IMG_1809 Copy.JPG metadata", () => {
    const entry = result.get("/temporary/directory/IMG_1809 Copy-edited.JPG");
    ok(entry);
    strictEqual(entry.mediaPath, "/temporary/directory/IMG_1809 Copy-edited.JPG");
    strictEqual(
      entry.jsonPath,
      "/temporary/directory/IMG_1809 Copy.JPG.supplemental-metadata.json"
    );
    strictEqual(entry.source.type, "loose");
  });

  test("should match IMG_1809 Copy.JPG to its metadata", () => {
    const entry = result.get("/temporary/directory/IMG_1809 Copy.JPG");
    ok(entry);
    strictEqual(entry.mediaPath, "/temporary/directory/IMG_1809 Copy.JPG");
    strictEqual(
      entry.jsonPath,
      "/temporary/directory/IMG_1809 Copy.JPG.supplemental-metadata.json"
    );
    strictEqual(entry.source.type, "loose");
  });
});

describe("link with prefix collision - MP and MP.jpg", () => {
  const rawCollections = {
    filesMedia: [
      "/temporary/directory/PXL_20241231_114910784.MP",
      "/temporary/directory/PXL_20241231_114910784.MP.jpg",
    ],
    filesMetadata: ["/temporary/directory/PXL_20241231_114910784.MP.jpg.supplemental-met.json"],
    filesMetadataAlbums: [],
  };

  const result = new Map(link(rawCollections).manifest.map((entry) => [entry.mediaPath, entry]));

  test("should return correct total number of media entries", () => {
    strictEqual(result.size, 2);
  });

  test("should match PXL_20241231_114910784.MP.jpg to its metadata", () => {
    const entry = result.get("/temporary/directory/PXL_20241231_114910784.MP.jpg");
    ok(entry);
    strictEqual(entry.mediaPath, "/temporary/directory/PXL_20241231_114910784.MP.jpg");
    strictEqual(
      entry.jsonPath,
      "/temporary/directory/PXL_20241231_114910784.MP.jpg.supplemental-met.json"
    );
    strictEqual(entry.source.type, "loose");
  });

  test("should match PXL_20241231_114910784.MP to shared MP.jpg metadata", () => {
    const entry = result.get("/temporary/directory/PXL_20241231_114910784.MP");
    ok(entry);
    strictEqual(entry.mediaPath, "/temporary/directory/PXL_20241231_114910784.MP");
    strictEqual(
      entry.jsonPath,
      "/temporary/directory/PXL_20241231_114910784.MP.jpg.supplemental-met.json"
    );
    strictEqual(entry.source.type, "loose");
  });
});

describe("link with sibling directory false positive", () => {
  const rawCollections = {
    filesMedia: ["/Photos/Vacation.jpg"],
    filesMetadata: ["/Photos/Vacation 2024/IMG_123.json"],
    filesMetadataAlbums: [],
  };

  const result = new Map(link(rawCollections).manifest.map((entry) => [entry.mediaPath, entry]));

  test("should NOT match media to metadata in a sibling directory that shares a prefix", () => {
    const entry = result.get("/Photos/Vacation.jpg");
    ok(entry);
    // Should be undefined because strict directory checking prevents the false positive
    strictEqual(entry.jsonPath, undefined);
  });
});
