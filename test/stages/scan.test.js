import { test, describe, mock, beforeEach } from "node:test";
import { strictEqual, deepStrictEqual } from "node:assert";

mock.module("../../src/utils/progress.js", {
  namedExports: {
    progressBar: mock.fn(() => {
      return {
        start: mock.fn(),
        increment: mock.fn(),
        stop: mock.fn(),
      };
    }),
  },
});

const readdirMock = mock.fn();
const statMock = mock.fn();
mock.module("fs/promises", {
  namedExports: {
    readdir: readdirMock,
    stat: statMock,
  },
});

const { scan } = await import("../../src/stages/scan.js");

describe("scan", () => {
  const dirent = (name, path, isFile = true) => {
    return { name, path, isFile: () => isFile };
  };

  beforeEach(() => {
    statMock.mock.mockImplementation(async () => {
      return { isDirectory: () => true };
    });
  });

  test("should categorize media files by known extensions", async () => {
    readdirMock.mock.mockImplementation(async () => {
      return [
        dirent("photo.jpg", "/source"),
        dirent("image.heic", "/source"),
        dirent("screenshot.png", "/source"),
        dirent("clip.mp4", "/source"),
        dirent("video.mov", "/source"),
        dirent("motion.mp", "/source"),
        dirent("image.jpeg", "/source"),
      ];
    });

    const result = await scan("/source");

    // Verify all supported media files are categorized
    strictEqual(result.filesMedia.length, 7);

    // Verify no files leaked into other buckets
    strictEqual(result.filesMetadata.length, 0);
    strictEqual(result.filesMetadataAlbums.length, 0);
    strictEqual(result.filesOtherIgnored.length, 0);
  });

  test("should categorize unsupported media files as media", async () => {
    readdirMock.mock.mockImplementation(async () => {
      return [
        dirent("old-video.avi", "/source"),
        dirent("movie.mkv", "/source"),
        dirent("clip.wmv", "/source"),
        dirent("stream.flv", "/source"),
      ];
    });

    const result = await scan("/source");

    // Verify unsupported-but-known media files are categorized as media
    strictEqual(result.filesMedia.length, 4);
  });

  test("should categorize json files as metadata", async () => {
    readdirMock.mock.mockImplementation(async () => {
      return [
        dirent("photo.jpg.supplemental-metadata.json", "/source"),
        dirent("photo.jpg.suppl.json", "/source"),
        dirent("photo.jpeg..json", "/source"),
      ];
    });

    const result = await scan("/source");

    // Verify all JSON files are categorized as metadata
    strictEqual(result.filesMetadata.length, 3);

    // Verify they are not miscategorized as media
    strictEqual(result.filesMedia.length, 0);
  });

  test("should categorize metadata.json as album metadata", async () => {
    readdirMock.mock.mockImplementation(async () => {
      return [
        dirent("metadata.json", "/source/Vacation"),
        dirent("metadata.json", "/source/Japan"),
        dirent("other.json", "/source"),
      ];
    });

    const result = await scan("/source");

    // Verify metadata.json files are categorized as album metadata
    strictEqual(result.filesMetadataAlbums.length, 2);

    // Verify other JSON files are categorized as metadata
    strictEqual(result.filesMetadata.length, 1);
  });

  test("should categorize unknown extensions as other/ignored", async () => {
    readdirMock.mock.mockImplementation(async () => {
      return [
        dirent("readme.txt", "/source"),
        dirent("notes.md", "/source"),
        dirent("archive.zip", "/source"),
      ];
    });

    const result = await scan("/source");

    // Verify unknown extensions go to the other/ignored bucket
    strictEqual(result.filesOtherIgnored.length, 3);

    // Verify they are not miscategorized
    strictEqual(result.filesMedia.length, 0);
    strictEqual(result.filesMetadata.length, 0);
  });

  test("should skip directories and non-file entries", async () => {
    readdirMock.mock.mockImplementation(async () => {
      return [dirent("subdir", "/source", false), dirent("photo.jpg", "/source")];
    });

    const result = await scan("/source");

    // Verify directory entries are skipped
    strictEqual(result.filesMedia.length, 1);

    // Verify total only counts files, not directories
    strictEqual(result.filesTotal, 1);
  });

  test("should build full paths from dirent name and parent path", async () => {
    readdirMock.mock.mockImplementation(async () => {
      return [
        dirent("photo.jpg", "/source/Photos from 2024"),
        dirent("metadata.json", "/source/Vacation"),
      ];
    });

    const result = await scan("/source");

    // Verify full paths are constructed correctly
    deepStrictEqual(result.filesMedia, ["/source/Photos from 2024/photo.jpg"]);
    deepStrictEqual(result.filesMetadataAlbums, ["/source/Vacation/metadata.json"]);
  });

  test("should handle case-insensitive extensions for media files", async () => {
    readdirMock.mock.mockImplementation(async () => {
      return [
        dirent("PHOTO.JPG", "/source"),
        dirent("image.HEIC", "/source"),
        dirent("video.MP4", "/source"),
      ];
    });

    const result = await scan("/source");

    // Verify uppercase extensions are matched case-insensitively
    strictEqual(result.filesMedia.length, 3);
  });

  test("should maintain correct total count across all buckets", async () => {
    readdirMock.mock.mockImplementation(async () => {
      return [
        dirent("photo.jpg", "/source"),
        dirent("photo.jpg.json", "/source"),
        dirent("metadata.json", "/source/Album"),
        dirent("readme.txt", "/source"),
        dirent("subdir", "/source", false),
      ];
    });

    const result = await scan("/source");

    // Verify total only counts files (not directories)
    strictEqual(result.filesTotal, 4);

    // Verify invariant: all buckets sum to total
    const bucketSum =
      result.filesMedia.length +
      result.filesMetadata.length +
      result.filesMetadataAlbums.length +
      result.filesOtherIgnored.length;
    strictEqual(bucketSum, result.filesTotal);
  });
});
