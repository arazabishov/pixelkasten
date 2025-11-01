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
        "/test/temporary/directory/IMG_0076.PNG",
        { sha256: "a1", entry: { path: "/test/temporary/directory", name: "IMG_0076.PNG" } },
      ],
      [
        "/test/temporary/directory/IMG_0784.MOV",
        { sha256: "b2", entry: { path: "/test/temporary/directory", name: "IMG_0784.MOV" } },
      ],
      [
        "/test/temporary/directory/98855-0000.mov",
        { sha256: "c3", entry: { path: "/test/temporary/directory", name: "98855-0000.mov" } },
      ],
      [
        "/test/temporary/directory/C3D916AEF50.jpg",
        { sha256: "d4", entry: { path: "/test/temporary/directory", name: "C3D916AEF50.jpg" } },
      ],
      [
        "/test/temporary/directory/1804928587.jpg",
        { sha256: "e5", entry: { path: "/test/temporary/directory", name: "1804928587.jpg" } },
      ],
      [
        "/test/temporary/directory/1804928587(1).jpg",
        { sha256: "f6", entry: { path: "/test/temporary/directory", name: "1804928587(1).jpg" } },
      ],
      [
        "/test/temporary/directory/114910784.MP.jpg",
        { sha256: "g7", entry: { path: "/test/temporary/directory", name: "114910784.MP.jpg" } },
      ],
      [
        "/test/temporary/directory/FA79581F10E4.jpeg",
        { sha256: "h8", entry: { path: "/test/temporary/directory", name: "FA79581F10E4.jpeg" } },
      ],
      [
        "/test/temporary/directory/IMG_0785.HEIC",
        { sha256: "i9", entry: { path: "/test/temporary/directory", name: "IMG_0785.HEIC" } },
      ],
      [
        "/test/temporary/directory/IMG_0785.MP4",
        { sha256: "j0", entry: { path: "/test/temporary/directory", name: "IMG_0785.MP4" } },
      ],
      [
        "/test/temporary/directory/IMG_0792.MP4",
        { sha256: "k1", entry: { path: "/test/temporary/directory", name: "IMG_0792.MP4" } },
      ],
      [
        "/test/temporary/directory/114910784.MP",
        { sha256: "l2", entry: { path: "/test/temporary/directory", name: "114910784.MP" } },
      ],
    ]),
    new Map([
      [
        "/test/temporary/directory/IMG_0076.PNG",
        { path: "/test/temporary/directory", name: "IMG_0076.PNG.supplemental-metadata.json" },
      ],
      [
        "/test/temporary/directory/IMG_0784.MOV",
        { path: "/test/temporary/directory", name: "IMG_0784.MOV.supplemental-metadata.json" },
      ],
      [
        "/test/temporary/directory/98855-000",
        { path: "/test/temporary/directory", name: "98855-000.json" },
      ],
      [
        "/test/temporary/directory/C3D916AEF50D.jpg",
        { path: "/test/temporary/directory", name: "C3D916AEF50D.jpg.suppl.json" },
      ],
      [
        "/test/temporary/directory/1804928587.jpg",
        { path: "/test/temporary/directory", name: "1804928587.jpg.supplemental-metadata.json" },
      ],
      [
        "/test/temporary/directory/1804928587(1).jpg",
        { path: "/test/temporary/directory", name: "1804928587.jpg.supplemental-metadata(1).json" },
      ],
      [
        "/test/temporary/directory/114910784.MP.jpg",
        { path: "/test/temporary/directory", name: "114910784.MP.jpg.supplemental-met.json" },
      ],
      [
        "/test/temporary/directory/FA79581F10E4.jpeg.",
        { path: "/test/temporary/directory", name: "FA79581F10E4.jpeg..json" },
      ],
      [
        "/test/temporary/directory/IMG_0785.HEIC",
        { path: "/test/temporary/directory", name: "IMG_0785.HEIC.supplemental-metadata.json" },
      ],
    ])
  );

  test("should return correct total number of media entries", () => {
    strictEqual(result.size, 12);
  });

  test("should match exact metadata - IMG_0076.PNG", () => {
    const entry = result.get("/test/temporary/directory/IMG_0076.PNG");
    ok(entry.media);
    ok(entry.metadata);
    strictEqual(entry.media.entry.name, "IMG_0076.PNG");
    strictEqual(entry.media.sha256, "a1");
    strictEqual(entry.metadata.name, "IMG_0076.PNG.supplemental-metadata.json");
  });

  test("should match exact metadata - IMG_0784.MOV", () => {
    const entry = result.get("/test/temporary/directory/IMG_0784.MOV");
    ok(entry.media);
    ok(entry.metadata);
    strictEqual(entry.media.entry.name, "IMG_0784.MOV");
    strictEqual(entry.media.sha256, "b2");
    strictEqual(entry.metadata.name, "IMG_0784.MOV.supplemental-metadata.json");
  });

  test("should match truncated metadata - 98855 video", () => {
    const entry = result.get("/test/temporary/directory/98855-0000.mov");
    ok(entry.media);
    ok(entry.metadata);
    strictEqual(entry.media.entry.name, "98855-0000.mov");
    strictEqual(entry.media.sha256, "c3");
    strictEqual(entry.metadata.name, "98855-000.json");
  });

  test("should match truncated metadata - C3D916", () => {
    const entry = result.get("/test/temporary/directory/C3D916AEF50.jpg");
    ok(entry.media);
    ok(entry.metadata);
    strictEqual(entry.media.entry.name, "C3D916AEF50.jpg");
    strictEqual(entry.media.sha256, "d4");
    strictEqual(entry.metadata.name, "C3D916AEF50D.jpg.suppl.json");
  });

  test("should match duplicate marker - original", () => {
    const entry = result.get("/test/temporary/directory/1804928587.jpg");
    ok(entry.media);
    ok(entry.metadata);
    strictEqual(entry.media.entry.name, "1804928587.jpg");
    strictEqual(entry.media.sha256, "e5");
    strictEqual(entry.metadata.name, "1804928587.jpg.supplemental-metadata.json");
  });

  test("should match duplicate marker - (1)", () => {
    const entry = result.get("/test/temporary/directory/1804928587(1).jpg");
    ok(entry.media);
    ok(entry.metadata);
    strictEqual(entry.media.entry.name, "1804928587(1).jpg");
    strictEqual(entry.media.sha256, "f6");
    strictEqual(entry.metadata.name, "1804928587.jpg.supplemental-metadata(1).json");
  });

  test("should match double extension - .MP.jpg", () => {
    const entry = result.get("/test/temporary/directory/114910784.MP.jpg");
    ok(entry.media);
    ok(entry.metadata);
    strictEqual(entry.media.entry.name, "114910784.MP.jpg");
    strictEqual(entry.media.sha256, "g7");
    strictEqual(entry.metadata.name, "114910784.MP.jpg.supplemental-met.json");
  });

  test("should match double-dot extension - FA7958", () => {
    const entry = result.get("/test/temporary/directory/FA79581F10E4.jpeg");
    ok(entry.media);
    ok(entry.metadata);
    strictEqual(entry.media.entry.name, "FA79581F10E4.jpeg");
    strictEqual(entry.media.sha256, "h8");
    strictEqual(entry.metadata.name, "FA79581F10E4.jpeg..json");
  });

  test("should match Live Photo pairs separately - HEIC with metadata", () => {
    const heic = result.get("/test/temporary/directory/IMG_0785.HEIC");
    ok(heic.media);
    ok(heic.metadata);
    strictEqual(heic.media.entry.name, "IMG_0785.HEIC");
    strictEqual(heic.media.sha256, "i9");
  });

  test("should match Live Photo pairs separately - MP4 without metadata", () => {
    const mp4 = result.get("/test/temporary/directory/IMG_0785.MP4");
    ok(mp4.media);
    strictEqual(mp4.metadata, undefined);
    strictEqual(mp4.media.entry.name, "IMG_0785.MP4");
    strictEqual(mp4.media.sha256, "j0");
  });

  test("should include orphan media - IMG_0792.MP4", () => {
    const entry = result.get("/test/temporary/directory/IMG_0792.MP4");
    ok(entry.media);
    strictEqual(entry.metadata, undefined);
    strictEqual(entry.media.entry.name, "IMG_0792.MP4");
    strictEqual(entry.media.sha256, "k1");
  });

  test("should include orphan media - 114910784.MP", () => {
    const entry = result.get("/test/temporary/directory/114910784.MP");
    ok(entry.media);
    strictEqual(entry.metadata, undefined);
    strictEqual(entry.media.entry.name, "114910784.MP");
    strictEqual(entry.media.sha256, "l2");
  });
});
