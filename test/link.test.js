import { test, describe } from "node:test";
import { strictEqual, ok } from "node:assert";
import { normalizeMetadataName, link } from "../src/stages/link.js";

describe("normalizeMetadataName", () => {
  test("should normalize .suppl.json metadata files", () => {
    const result = normalizeMetadataName("3D06C8D1-7637-4625-BEBE-C3D916AEF50D.jpg.suppl.json");
    strictEqual(result, "3D06C8D1-7637-4625-BEBE-C3D916AEF50D.jpg");
  });

  test("should normalize .supplemental-metada.json metadata files", () => {
    const result = normalizeMetadataName("PXL_20241231_114900266.jpg.supplemental-metada.json");
    strictEqual(result, "PXL_20241231_114900266.jpg");
  });

  test("should normalize .supplemental-met.json metadata files with two file extensions", () => {
    const result = normalizeMetadataName("PXL_20241231_114910784.MP.jpg.supplemental-met.json");
    strictEqual(result, "PXL_20241231_114910784.MP.jpg");
  });

  test("should normalize .supplemental-metadata(N).json with duplicate markers", () => {
    const result = normalizeMetadataName("camphoto_33463914.jpg.supplemental-metadata(4).json");
    strictEqual(result, "camphoto_33463914(4).jpg");
  });

  test("should normalize .supplemental-metadata(N).json with duplicate markers and two extensions", () => {
    const result = normalizeMetadataName("camphoto_33463914.MP.jpg.supplemental-metadata(4).json");
    strictEqual(result, "camphoto_33463914(4).MP.jpg");
  });

  test("should normalize .(N).json with duplicate markers", () => {
    const result = normalizeMetadataName("camphoto_33463914.jpg.(4).json");
    strictEqual(result, "camphoto_33463914(4).jpg");
  });

  test("should return original file name if file name has no extensions", () => {
    const result = normalizeMetadataName("camphoto_33463914");
    strictEqual(result, "camphoto_33463914");
  });

  test("should return original file name if file extension is not .json", () => {
    const result = normalizeMetadataName("PXL_20241231_114900266.jpg");
    strictEqual(result, "PXL_20241231_114900266.jpg");
  });

  test("should return filename without extension if the only extension is .json", () => {
    const result = normalizeMetadataName("29407C9C-7528-4FF1-AD5F-08EAA7F9738E-98855-000.json");
    strictEqual(result, "29407C9C-7528-4FF1-AD5F-08EAA7F9738E-98855-000");
  });

  test("should return an empty string if empty string is provided", () => {
    const result = normalizeMetadataName("");
    strictEqual(result, "");
  });

  test("should return undefined if undefined is supplied", () => {
    const result = normalizeMetadataName(undefined);
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
      "/temporary/directory/IMG_0785.MP4",
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

  const result = new Map(link(rawCollections));

  test("should return correct total number of media entries", () => {
    strictEqual(result.size, 15);
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

  test("should match Live Photo pairs separately - MP4 without metadata", () => {
    const mp4 = result.get("/temporary/directory/IMG_0785.MP4");
    ok(mp4);
    strictEqual(mp4.mediaPath, "/temporary/directory/IMG_0785.MP4");
    strictEqual(mp4.jsonPath, undefined);
    strictEqual(mp4.source.type, "loose");
  });

  test("should include orphan media - IMG_0792.MP4", () => {
    const entry = result.get("/temporary/directory/IMG_0792.MP4");
    ok(entry);
    strictEqual(entry.mediaPath, "/temporary/directory/IMG_0792.MP4");
    strictEqual(entry.jsonPath, undefined);
    strictEqual(entry.source.type, "loose");
  });

  test("should include orphan media - 11491078.MP", () => {
    const entry = result.get("/temporary/directory/11491078.MP");
    ok(entry);
    strictEqual(entry.mediaPath, "/temporary/directory/11491078.MP");
    strictEqual(entry.jsonPath, undefined);
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

  const result = new Map(link(rawCollections));

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
