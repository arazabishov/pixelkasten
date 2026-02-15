import { test, describe, beforeEach, mock } from "node:test";
import { strictEqual, ok } from "node:assert";

const writeFileMock = mock.fn();
mock.module("fs/promises", {
  namedExports: {
    writeFile: writeFileMock,
  },
});

const { report } = await import("../../src/core/report.js");

describe("report", () => {
  beforeEach(() => {
    writeFileMock.mock.resetCalls();

    writeFileMock.mock.mockImplementation(async () => {
      return undefined;
    });
  });

  test("should write CSV with correct header and rows", async () => {
    const manifest = [
      {
        mediaPath: "/source/photos/IMG_001.jpg",
        json: {
          path: "/source/photos/IMG_001.jpg.json",
          confidence: 3,
        },
        dedupe: {
          status: "keep",
        },
        metadata: {
          status: "processed",
          writeTags: ["DateTimeOriginal=2023:01:01"],
          dates: ["2023-01-01T12:00:00"],
        },
        apply: {
          status: "embedded",
          targetPath: "/dest/2023/01 - January/20230101-120000.jpg",
        },
      },
    ];

    const options = {
      source: "/source",
      destination: "/dest",
    };

    const reportPath = await report(manifest, options);

    // Verify report path
    strictEqual(reportPath, "/dest/report.csv");

    // Verify writeFile was called once
    strictEqual(writeFileMock.mock.callCount(), 1);

    // Verify CSV content
    const csv = writeFileMock.mock.calls[0].arguments[1];
    const lines = csv.trim().split("\n");

    // Verify header
    strictEqual(lines[0], "media,metadata,confidence,status,reason");

    // Verify data row
    strictEqual(lines[1], "photos/IMG_001.jpg,photos/IMG_001.jpg.json,3,embedded,");
  });

  test("should resolve status as deleted for deduplicated entries", async () => {
    const manifest = [
      {
        mediaPath: "/source/dup.jpg",
        json: null,
        dedupe: {
          status: "delete",
        },
      },
    ];

    await report(manifest, {
      source: "/source",
      destination: "/dest",
    });

    const csv = writeFileMock.mock.calls[0].arguments[1];
    const lines = csv.trim().split("\n");

    // Verify status is deleted
    strictEqual(lines[1], "dup.jpg,,,deleted,");
  });

  test("should resolve status as skipped for unsupported formats", async () => {
    const manifest = [
      {
        mediaPath: "/source/video.avi",
        json: {
          path: "/source/video.avi.json",
          confidence: 3,
        },
        dedupe: {
          status: "keep",
        },
        metadata: {
          status: "skipped",
          reason: "No metadata handler for .avi",
          writeTags: [],
          dates: [],
        },
      },
    ];

    await report(manifest, {
      source: "/source",
      destination: "/dest",
    });

    const csv = writeFileMock.mock.calls[0].arguments[1];
    const lines = csv.trim().split("\n");

    // Verify status is skipped with reason
    strictEqual(lines[1], "video.avi,video.avi.json,3,skipped,No metadata handler for .avi");
  });

  test("should resolve status as error when apply fails", async () => {
    const manifest = [
      {
        mediaPath: "/source/photo.jpg",
        json: null,
        dedupe: {
          status: "keep",
        },
        apply: {
          status: "error",
          reason: "ENOENT: no such file",
        },
      },
    ];

    await report(manifest, {
      source: "/source",
      destination: "/dest",
    });

    const csv = writeFileMock.mock.calls[0].arguments[1];
    const lines = csv.trim().split("\n");

    // Verify status is error with reason
    strictEqual(lines[1], "photo.jpg,,,error,ENOENT: no such file");
  });

  test("should resolve status as copied when no metadata changes needed", async () => {
    const manifest = [
      {
        mediaPath: "/source/photo.jpg",
        json: {
          path: "/source/photo.jpg.json",
          confidence: 2,
        },
        dedupe: {
          status: "keep",
        },
        metadata: {
          status: "noop",
          writeTags: [],
          dates: ["2023-01-01T12:00:00"],
        },
        apply: {
          status: "copied",
          targetPath: "/dest/photo.jpg",
        },
      },
    ];

    await report(manifest, {
      source: "/source",
      destination: "/dest",
    });

    const csv = writeFileMock.mock.calls[0].arguments[1];
    const lines = csv.trim().split("\n");

    // Verify status is copied
    strictEqual(lines[1], "photo.jpg,photo.jpg.json,2,copied,");
  });

  test("should escape commas and quotes in CSV fields", async () => {
    const manifest = [
      {
        mediaPath: '/source/photo, "special".jpg',
        json: null,
        apply: {
          status: "error",
          reason: 'Failed with "error"',
        },
      },
    ];

    await report(manifest, {
      source: "/source",
      destination: "/dest",
    });

    const csv = writeFileMock.mock.calls[0].arguments[1];
    const lines = csv.trim().split("\n");

    // Verify proper escaping of commas and quotes
    ok(lines[1].includes('"photo, ""special"".jpg"'));
    ok(lines[1].includes('"Failed with ""error"""'));
  });

  test("should handle entries without json match", async () => {
    const manifest = [
      {
        mediaPath: "/source/unmatched.jpg",
        json: null,
        dedupe: {
          status: "keep",
        },
        apply: {
          status: "copied",
          targetPath: "/dest/unmatched.jpg",
        },
      },
    ];

    await report(manifest, {
      source: "/source",
      destination: "/dest",
    });

    const csv = writeFileMock.mock.calls[0].arguments[1];
    const lines = csv.trim().split("\n");

    // Verify empty metadata and confidence fields
    strictEqual(lines[1], "unmatched.jpg,,,copied,");
  });
});
