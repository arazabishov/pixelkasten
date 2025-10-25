import { test, describe } from "node:test";
import assert from "node:assert";
import { getFileType } from "../src/fs.js";

describe("getFileType", () => {
  test("should identify image files", () => {
    assert.strictEqual(getFileType("photo.jpg"), "image");
    assert.strictEqual(getFileType("photo.jpeg"), "image");
    assert.strictEqual(getFileType("photo.png"), "image");
    assert.strictEqual(getFileType("photo.gif"), "image");
    assert.strictEqual(getFileType("photo.heic"), "image");
    assert.strictEqual(getFileType("photo.webp"), "image");
  });

  test("should identify video files", () => {
    assert.strictEqual(getFileType("video.mp4"), "video");
    assert.strictEqual(getFileType("video.mov"), "video");
    assert.strictEqual(getFileType("video.avi"), "video");
  });

  test("should identify metadata files", () => {
    assert.strictEqual(getFileType("data.json"), "metadata");
  });

  test("should handle uppercase extensions", () => {
    assert.strictEqual(getFileType("PHOTO.JPG"), "image");
    assert.strictEqual(getFileType("VIDEO.MP4"), "video");
    assert.strictEqual(getFileType("DATA.JSON"), "metadata");
  });

  test("should return unsupported for unknown extensions", () => {
    assert.strictEqual(getFileType("document.pdf"), "unsupported");
    assert.strictEqual(getFileType("file.txt"), "unsupported");
    assert.strictEqual(getFileType("archive.zip"), "unsupported");
  });

  test("should handle files with no extension", () => {
    assert.strictEqual(getFileType("filename"), "unsupported");
  });
});
