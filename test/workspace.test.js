import { test, describe } from "node:test";
import { strictEqual, ok } from "node:assert";
import { normalizeMetadataName, connect } from "../src/workspace.js";

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

describe("connect", () => {
  const result = connect(
    new Map([
      [
        "/temporary/directory/IMG_0076.PNG",
        { sha256: "a1", entry: { path: "/temporary/directory", name: "IMG_0076.PNG" } },
      ],
      [
        "/temporary/directory/IMG_0784.MOV",
        { sha256: "b2", entry: { path: "/temporary/directory", name: "IMG_0784.MOV" } },
      ],
      [
        "/temporary/directory/988555-0000.mov",
        { sha256: "c3", entry: { path: "/temporary/directory", name: "988555-0000.mov" } },
      ],
      [
        "/temporary/directory/C3D916AEF50.jpg",
        { sha256: "d4", entry: { path: "/temporary/directory", name: "C3D916AEF50.jpg" } },
      ],
      [
        "/temporary/directory/1804928587.jpg",
        { sha256: "e5", entry: { path: "/temporary/directory", name: "1804928587.jpg" } },
      ],
      [
        "/temporary/directory/1804928587(1).jpg",
        { sha256: "f6", entry: { path: "/temporary/directory", name: "1804928587(1).jpg" } },
      ],
      [
        "/temporary/directory/11491078.MP.jpg",
        { sha256: "g7", entry: { path: "/temporary/directory", name: "11491078.MP.jpg" } },
      ],
      [
        "/temporary/directory/FA79581F10E4.jpeg",
        { sha256: "h8", entry: { path: "/temporary/directory", name: "FA79581F10E4.jpeg" } },
      ],
      [
        "/temporary/directory/IMG_0785.HEIC",
        { sha256: "i9", entry: { path: "/temporary/directory", name: "IMG_0785.HEIC" } },
      ],
      [
        "/temporary/directory/IMG_0785.MP4",
        { sha256: "j0", entry: { path: "/temporary/directory", name: "IMG_0785.MP4" } },
      ],
      [
        "/temporary/directory/IMG_0792.MP4",
        { sha256: "k1", entry: { path: "/temporary/directory", name: "IMG_0792.MP4" } },
      ],
      [
        "/temporary/directory/11491078.MP",
        { sha256: "l2", entry: { path: "/temporary/directory", name: "11491078.MP" } },
      ],
      [
        "/temporary/directory/IMG_0076-edited.PNG",
        { sha256: "m1", entry: { path: "/temporary/directory", name: "IMG_0076-edited.PNG" } },
      ],
      [
        "/temporary/directory/PXL_202501-edited.jpg",
        { sha256: "n1", entry: { path: "/temporary/directory", name: "PXL_202501-edited.jpg" } },
      ],
      [
        "/temporary/directory/11491078-edited.MP.jpg",
        { sha256: "o1", entry: { path: "/temporary/directory", name: "11491078-edited.MP.jpg" } },
      ],
    ]),
    new Map([
      [
        "/temporary/directory/IMG_0076.PNG",
        { path: "/temporary/directory", name: "IMG_0076.PNG.supplemental-metadata.json" },
      ],
      [
        "/temporary/directory/IMG_0784.MOV",
        { path: "/temporary/directory", name: "IMG_0784.MOV.supplemental-metadata.json" },
      ],
      [
        "/temporary/directory/988555-000",
        { path: "/temporary/directory", name: "988555-000.json" },
      ],
      [
        "/temporary/directory/C3D916AEF50D.jpg",
        { path: "/temporary/directory", name: "C3D916AEF50D.jpg.suppl.json" },
      ],
      [
        "/temporary/directory/1804928587.jpg",
        { path: "/temporary/directory", name: "1804928587.jpg.supplemental-metadata.json" },
      ],
      [
        "/temporary/directory/1804928587(1).jpg",
        { path: "/temporary/directory", name: "1804928587.jpg.supplemental-metadata(1).json" },
      ],
      [
        "/temporary/directory/11491078.MP.jpg",
        { path: "/temporary/directory", name: "11491078.MP.jpg.supplemental-met.json" },
      ],
      [
        "/temporary/directory/FA79581F10E4.jpeg.",
        { path: "/temporary/directory", name: "FA79581F10E4.jpeg..json" },
      ],
      [
        "/temporary/directory/IMG_0785.HEIC",
        { path: "/temporary/directory", name: "IMG_0785.HEIC.supplemental-metadata.json" },
      ],
      [
        "/temporary/directory/PXL_202501.jpg",
        { path: "/temporary/directory", name: "PXL_202501.jpg.json" },
      ],
    ])
  );

  test("should return correct total number of media entries", () => {
    strictEqual(result.size, 15);
  });

  test("should match exact metadata - IMG_0076.PNG", () => {
    const entry = result.get("/temporary/directory/IMG_0076.PNG");
    ok(entry.media);
    ok(entry.metadata);
    strictEqual(entry.media.entry.name, "IMG_0076.PNG");
    strictEqual(entry.media.sha256, "a1");
    strictEqual(entry.metadata.name, "IMG_0076.PNG.supplemental-metadata.json");
  });

  test("should match exact metadata - IMG_0784.MOV", () => {
    const entry = result.get("/temporary/directory/IMG_0784.MOV");
    ok(entry.media);
    ok(entry.metadata);
    strictEqual(entry.media.entry.name, "IMG_0784.MOV");
    strictEqual(entry.media.sha256, "b2");
    strictEqual(entry.metadata.name, "IMG_0784.MOV.supplemental-metadata.json");
  });

  test("should match truncated metadata - 988555 video", () => {
    const entry = result.get("/temporary/directory/988555-0000.mov");
    ok(entry.media);
    ok(entry.metadata);
    strictEqual(entry.media.entry.name, "988555-0000.mov");
    strictEqual(entry.media.sha256, "c3");
    strictEqual(entry.metadata.name, "988555-000.json");
  });

  test("should match truncated metadata - C3D916", () => {
    const entry = result.get("/temporary/directory/C3D916AEF50.jpg");
    ok(entry.media);
    ok(entry.metadata);
    strictEqual(entry.media.entry.name, "C3D916AEF50.jpg");
    strictEqual(entry.media.sha256, "d4");
    strictEqual(entry.metadata.name, "C3D916AEF50D.jpg.suppl.json");
  });

  test("should match duplicate marker - original", () => {
    const entry = result.get("/temporary/directory/1804928587.jpg");
    ok(entry.media);
    ok(entry.metadata);
    strictEqual(entry.media.entry.name, "1804928587.jpg");
    strictEqual(entry.media.sha256, "e5");
    strictEqual(entry.metadata.name, "1804928587.jpg.supplemental-metadata.json");
  });

  test("should match duplicate marker - (1)", () => {
    const entry = result.get("/temporary/directory/1804928587(1).jpg");
    ok(entry.media);
    ok(entry.metadata);
    strictEqual(entry.media.entry.name, "1804928587(1).jpg");
    strictEqual(entry.media.sha256, "f6");
    strictEqual(entry.metadata.name, "1804928587.jpg.supplemental-metadata(1).json");
  });

  test("should match double extension - .MP.jpg", () => {
    const entry = result.get("/temporary/directory/11491078.MP.jpg");
    ok(entry.media);
    ok(entry.metadata);
    strictEqual(entry.media.entry.name, "11491078.MP.jpg");
    strictEqual(entry.media.sha256, "g7");
    strictEqual(entry.metadata.name, "11491078.MP.jpg.supplemental-met.json");
  });

  test("should match double-dot extension - FA7958", () => {
    const entry = result.get("/temporary/directory/FA79581F10E4.jpeg");
    ok(entry.media);
    ok(entry.metadata);
    strictEqual(entry.media.entry.name, "FA79581F10E4.jpeg");
    strictEqual(entry.media.sha256, "h8");
    strictEqual(entry.metadata.name, "FA79581F10E4.jpeg..json");
  });

  test("should match Live Photo pairs separately - HEIC with metadata", () => {
    const heic = result.get("/temporary/directory/IMG_0785.HEIC");
    ok(heic.media);
    ok(heic.metadata);
    strictEqual(heic.media.entry.name, "IMG_0785.HEIC");
    strictEqual(heic.media.sha256, "i9");
  });

  test("should match Live Photo pairs separately - MP4 without metadata", () => {
    const mp4 = result.get("/temporary/directory/IMG_0785.MP4");
    ok(mp4.media);
    strictEqual(mp4.metadata, undefined);
    strictEqual(mp4.media.entry.name, "IMG_0785.MP4");
    strictEqual(mp4.media.sha256, "j0");
  });

  test("should include orphan media - IMG_0792.MP4", () => {
    const entry = result.get("/temporary/directory/IMG_0792.MP4");
    ok(entry.media);
    strictEqual(entry.metadata, undefined);
    strictEqual(entry.media.entry.name, "IMG_0792.MP4");
    strictEqual(entry.media.sha256, "k1");
  });

  test("should include orphan media - 11491078.MP", () => {
    const entry = result.get("/temporary/directory/11491078.MP");
    ok(entry.media);
    strictEqual(entry.metadata, undefined);
    strictEqual(entry.media.entry.name, "11491078.MP");
    strictEqual(entry.media.sha256, "l2");
  });

  test("should match edited PNG to original metadata", () => {
    const entry = result.get("/temporary/directory/IMG_0076-edited.PNG");
    ok(entry.media);
    ok(entry.metadata);
    strictEqual(entry.media.entry.name, "IMG_0076-edited.PNG");
    strictEqual(entry.media.sha256, "m1");
    strictEqual(entry.metadata.name, "IMG_0076.PNG.supplemental-metadata.json");
  });

  test("should match edited PXL photo to original metadata", () => {
    const entry = result.get("/temporary/directory/PXL_202501-edited.jpg");
    ok(entry.media);
    ok(entry.metadata);
    strictEqual(entry.media.entry.name, "PXL_202501-edited.jpg");
    strictEqual(entry.media.sha256, "n1");
    strictEqual(entry.metadata.name, "PXL_202501.jpg.json");
  });

  test("should match edited double extension file to original metadata", () => {
    const entry = result.get("/temporary/directory/11491078-edited.MP.jpg");
    ok(entry.media);
    ok(entry.metadata);
    strictEqual(entry.media.entry.name, "11491078-edited.MP.jpg");
    strictEqual(entry.media.sha256, "o1");
    strictEqual(entry.metadata.name, "11491078.MP.jpg.supplemental-met.json");
  });
});
