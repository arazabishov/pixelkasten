import { test, describe, mock } from "node:test";
import { strictEqual, ok } from "node:assert";

mock.module("../../src/utils/logger.js", {
  namedExports: {
    logger: {
      error: mock.fn(),
      info: mock.fn(),
      warn: mock.fn(),
    },
  },
});

const { rename } = await import("../../src/stages/rename.js");

describe("rename", () => {
  test("should not process entries when manifest is empty", () => {
    const manifest = [];

    rename(manifest);

    // Verify no entries were added
    strictEqual(manifest.length, 0);
  });

  test("should skip entries marked for deletion", () => {
    const manifest = [
      {
        mediaPath: "/path/to/delete.jpg",
        dedupe: { status: "delete" },
        metadata: { dates: ["2023-01-15T14:30:45"] },
      },
      {
        mediaPath: "/path/to/keep.jpg",
        dedupe: { status: "keep" },
        metadata: { dates: ["2023-01-15T14:30:45"] },
      },
    ];

    rename(manifest);

    // Verify deleted entry was not processed
    strictEqual(manifest[0].rename, undefined);

    // Verify kept entry was processed
    strictEqual(manifest[1].rename.status, "processed");
  });

  test("should generate correct path structure from date", () => {
    const manifest = [
      {
        mediaPath: "/path/to/image.jpg",
        metadata: { dates: ["2024-03-01T13:32:45"] },
      },
    ];

    rename(manifest);

    // Verify correct path format: yyyy/mm - Month/yyyymmddhhmmss.ext
    strictEqual(manifest[0].rename.targetPath, "2024/03 - March/20240301-133245.jpg");
  });

  test("should handle different months correctly", () => {
    const manifest = [
      {
        mediaPath: "/path/to/jan.jpg",
        metadata: { dates: ["2024-01-15T10:00:30"] },
      },
      {
        mediaPath: "/path/to/dec.jpg",
        metadata: { dates: ["2024-12-25T18:30:59"] },
      },
    ];

    rename(manifest);

    // Verify January path
    strictEqual(manifest[0].rename.targetPath, "2024/01 - January/20240115-100030.jpg");

    // Verify December path
    strictEqual(manifest[1].rename.targetPath, "2024/12 - December/20241225-183059.jpg");
  });

  test("should preserve file extension in lowercase", () => {
    const manifest = [
      {
        mediaPath: "/path/to/image.JPG",
        metadata: { dates: ["2024-03-01T13:32:00"] },
      },
      {
        mediaPath: "/path/to/video.MP4",
        metadata: { dates: ["2024-03-01T14:00:00"] },
      },
    ];

    rename(manifest);

    // Verify lowercase extension for image
    ok(manifest[0].rename.targetPath.endsWith(".jpg"));

    // Verify lowercase extension for video
    ok(manifest[1].rename.targetPath.endsWith(".mp4"));
  });

  test("should handle collisions by appending -1, -2 suffixes", () => {
    const manifest = [
      {
        mediaPath: "/path/to/first.jpg",
        metadata: { dates: ["2024-03-01T14:02:30"] },
      },
      {
        mediaPath: "/path/to/second.jpg",
        metadata: { dates: ["2024-03-01T14:02:30"] },
      },
      {
        mediaPath: "/path/to/third.jpg",
        metadata: { dates: ["2024-03-01T14:02:30"] },
      },
    ];

    rename(manifest);

    // Verify first file gets base name
    strictEqual(manifest[0].rename.targetPath, "2024/03 - March/20240301-140230.jpg");

    // Verify second file gets -1 suffix
    strictEqual(manifest[1].rename.targetPath, "2024/03 - March/20240301-140230-1.jpg");

    // Verify third file gets -2 suffix
    strictEqual(manifest[2].rename.targetPath, "2024/03 - March/20240301-140230-2.jpg");
  });

  test("should mark entries without dates as error", () => {
    const manifest = [
      {
        mediaPath: "/path/to/image.jpg",
        metadata: {},
      },
    ];

    rename(manifest);

    // Verify entry has error status
    strictEqual(manifest[0].rename.status, "error");
  });

  test("should mark entries with empty dates array as error", () => {
    const manifest = [
      {
        mediaPath: "/path/to/image.jpg",
        metadata: { dates: [] },
      },
    ];

    rename(manifest);

    // Verify entry has error status
    strictEqual(manifest[0].rename.status, "error");
  });

  test("should mark entries with invalid date format as error", () => {
    const manifest = [
      {
        mediaPath: "/path/to/image.jpg",
        metadata: { dates: ["not-a-valid-date"] },
      },
    ];

    rename(manifest);

    // Verify entry has error status
    strictEqual(manifest[0].rename.status, "error");
  });

  test("should use first date in array as primary timestamp", () => {
    const manifest = [
      {
        mediaPath: "/path/to/image.jpg",
        metadata: {
          dates: ["2024-03-01T13:32:15", "2024-03-01T14:00:00", "2024-03-02T10:00:00"],
        },
      },
    ];

    rename(manifest);

    // Verify first date was used (not second or third)
    strictEqual(manifest[0].rename.targetPath, "2024/03 - March/20240301-133215.jpg");
  });

  test("should fall back to next date if first is invalid", () => {
    const manifest = [
      {
        mediaPath: "/path/to/image.jpg",
        metadata: {
          dates: ["invalid-date", "also-invalid", "2024-05-10T09:15:30"],
        },
      },
    ];

    rename(manifest);

    // Verify third date was used after first two failed
    strictEqual(manifest[0].rename.targetPath, "2024/05 - May/20240510-091530.jpg");
  });

  test("should process entries without dedupe property", () => {
    const manifest = [
      {
        mediaPath: "/path/to/image.jpg",
        metadata: { dates: ["2024-03-01T13:32:00"] },
      },
    ];

    rename(manifest);

    // Verify entry was processed despite missing dedupe
    strictEqual(manifest[0].rename.status, "processed");
  });

  test("should handle entries with pending dedupe status", () => {
    const manifest = [
      {
        mediaPath: "/path/to/image.jpg",
        dedupe: { status: "pending" },
        metadata: { dates: ["2024-03-01T13:32:00"] },
      },
    ];

    rename(manifest);

    // Verify entry with pending action is still processed
    strictEqual(manifest[0].rename.status, "processed");
  });

  test("should pad single-digit months and times with zeros", () => {
    const manifest = [
      {
        mediaPath: "/path/to/image.jpg",
        metadata: { dates: ["2024-01-05T09:05:07"] },
      },
    ];

    rename(manifest);

    // Verify proper zero-padding in path
    strictEqual(manifest[0].rename.targetPath, "2024/01 - January/20240105-090507.jpg");
  });

  test("should handle HEIC files correctly", () => {
    const manifest = [
      {
        mediaPath: "/path/to/image.HEIC",
        metadata: { dates: ["2024-03-01T13:32:00"] },
      },
    ];

    rename(manifest);

    // Verify HEIC extension is preserved in lowercase
    strictEqual(manifest[0].rename.targetPath, "2024/03 - March/20240301-133200.heic");
  });

  test("should handle MOV files correctly", () => {
    const manifest = [
      {
        mediaPath: "/path/to/video.MOV",
        metadata: { dates: ["2024-03-01T13:32:00"] },
      },
    ];

    rename(manifest);

    // Verify MOV extension is preserved in lowercase
    strictEqual(manifest[0].rename.targetPath, "2024/03 - March/20240301-133200.mov");
  });

  test("should handle collisions across different file types", () => {
    const manifest = [
      {
        mediaPath: "/path/to/image.jpg",
        metadata: { dates: ["2024-03-01T14:02:00"] },
      },
      {
        mediaPath: "/path/to/video.mp4",
        metadata: { dates: ["2024-03-01T14:02:00"] },
      },
    ];

    rename(manifest);

    // Verify different extensions don't collide
    strictEqual(manifest[0].rename.targetPath, "2024/03 - March/20240301-140200.jpg");
    strictEqual(manifest[1].rename.targetPath, "2024/03 - March/20240301-140200.mp4");
  });

  test("should include seconds in timestamp to reduce collisions", () => {
    const manifest = [
      {
        mediaPath: "/path/to/first.jpg",
        metadata: { dates: ["2024-03-01T14:02:30"] },
      },
      {
        mediaPath: "/path/to/second.jpg",
        metadata: { dates: ["2024-03-01T14:02:31"] },
      },
    ];

    rename(manifest);

    // Verify different seconds produce different paths (no collision)
    strictEqual(manifest[0].rename.targetPath, "2024/03 - March/20240301-140230.jpg");
    strictEqual(manifest[1].rename.targetPath, "2024/03 - March/20240301-140231.jpg");
  });

  test("should place album photos in album subfolder", () => {
    const manifest = [
      {
        mediaPath: "/path/to/image.jpg",
        source: { type: "album", name: "Trip to Japan" },
        metadata: { dates: ["2024-04-15T10:30:00"] },
      },
    ];

    rename(manifest);

    // Verify album structure: yyyy/mm - Month/yyyymmdd - Album Name/timestamp.ext
    strictEqual(
      manifest[0].rename.targetPath,
      "2024/04 - April/20240415 - Trip to Japan/20240415-103000.jpg"
    );
  });

  test("should use earliest album date for folder structure", () => {
    const manifest = [
      {
        mediaPath: "/path/to/later.jpg",
        source: { type: "album", name: "Vacation" },
        metadata: { dates: ["2024-03-20T15:00:00"] },
      },
      {
        mediaPath: "/path/to/earlier.jpg",
        source: { type: "album", name: "Vacation" },
        metadata: { dates: ["2024-03-18T09:00:00"] },
      },
    ];

    rename(manifest);

    // Verify both photos use earliest date (March 18) for folder
    strictEqual(
      manifest[0].rename.targetPath,
      "2024/03 - March/20240318 - Vacation/20240320-150000.jpg"
    );
    strictEqual(
      manifest[1].rename.targetPath,
      "2024/03 - March/20240318 - Vacation/20240318-090000.jpg"
    );
  });

  test("should place cross-month album in earliest month", () => {
    const manifest = [
      {
        mediaPath: "/path/to/jan.jpg",
        source: { type: "album", name: "New Year Trip" },
        metadata: { dates: ["2024-01-02T12:00:00"] },
      },
      {
        mediaPath: "/path/to/dec.jpg",
        source: { type: "album", name: "New Year Trip" },
        metadata: { dates: ["2023-12-31T23:00:00"] },
      },
    ];

    rename(manifest);

    // Verify both photos go to December (earliest month)
    strictEqual(
      manifest[0].rename.targetPath,
      "2023/12 - December/20231231 - New Year Trip/20240102-120000.jpg"
    );
    strictEqual(
      manifest[1].rename.targetPath,
      "2023/12 - December/20231231 - New Year Trip/20231231-230000.jpg"
    );
  });

  test("should handle mix of album and loose files", () => {
    const manifest = [
      {
        mediaPath: "/path/to/album-photo.jpg",
        source: { type: "album", name: "Birthday" },
        metadata: { dates: ["2024-05-10T14:00:00"] },
      },
      {
        mediaPath: "/path/to/loose-photo.jpg",
        source: { type: "loose" },
        metadata: { dates: ["2024-05-10T14:30:00"] },
      },
    ];

    rename(manifest);

    // Verify album photo goes to album subfolder
    strictEqual(
      manifest[0].rename.targetPath,
      "2024/05 - May/20240510 - Birthday/20240510-140000.jpg"
    );

    // Verify loose photo goes directly to month folder
    strictEqual(manifest[1].rename.targetPath, "2024/05 - May/20240510-143000.jpg");
  });

  test("should handle collisions within album", () => {
    const manifest = [
      {
        mediaPath: "/path/to/first.jpg",
        source: { type: "album", name: "Party" },
        metadata: { dates: ["2024-06-01T20:00:00"] },
      },
      {
        mediaPath: "/path/to/second.jpg",
        source: { type: "album", name: "Party" },
        metadata: { dates: ["2024-06-01T20:00:00"] },
      },
    ];

    rename(manifest);

    // Verify collision handling within album
    strictEqual(
      manifest[0].rename.targetPath,
      "2024/06 - June/20240601 - Party/20240601-200000.jpg"
    );
    strictEqual(
      manifest[1].rename.targetPath,
      "2024/06 - June/20240601 - Party/20240601-200000-1.jpg"
    );
  });
});
