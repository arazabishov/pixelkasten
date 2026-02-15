import { test, describe, beforeEach, mock } from "node:test";
import { strictEqual, deepStrictEqual } from "node:assert";

const mkdirMock = mock.fn();
const copyFileMock = mock.fn();
mock.module("fs/promises", {
  namedExports: {
    mkdir: mkdirMock,
    copyFile: copyFileMock,
  },
});

const writeMetadataMock = mock.fn();
mock.module("../../src/core/exiftool.js", {
  namedExports: {
    writeMetadata: writeMetadataMock,
  },
});

const { apply } = await import("../../src/stages/apply.js");

describe("apply", () => {
  beforeEach(() => {
    mkdirMock.mock.resetCalls();
    copyFileMock.mock.resetCalls();
    writeMetadataMock.mock.resetCalls();

    // Set default mock implementations
    mkdirMock.mock.mockImplementation(async () => {
      return undefined;
    });
    copyFileMock.mock.mockImplementation(async () => {
      return undefined;
    });
    writeMetadataMock.mock.mockImplementation(async () => {
      return undefined;
    });
  });

  test("should not perform disk operations when manifest is empty", async () => {
    const manifest = [];

    await apply(manifest, { destination: "/dest" });

    // Verify no directories were created
    strictEqual(mkdirMock.mock.callCount(), 0);

    // Verify no files were copied
    strictEqual(copyFileMock.mock.callCount(), 0);

    // Verify no metadata was written
    strictEqual(writeMetadataMock.mock.callCount(), 0);
  });

  test("should not copy entries marked for deletion", async () => {
    const manifest = [
      {
        mediaPath: "/source/delete-me.jpg",
        dedupe: {
          status: "delete",
        },
      },
      {
        mediaPath: "/source/keep-me.jpg",
        dedupe: {
          status: "keep",
        },
        rename: {
          targetPath: "2023/01 - January/keep-me.jpg",
        },
      },
    ];

    await apply(manifest, { destination: "/dest", skipEmbed: true });

    // Verify only one file was copied
    strictEqual(copyFileMock.mock.callCount(), 1);

    // Verify the kept file was copied, not the deleted one
    strictEqual(copyFileMock.mock.calls[0].arguments[0], "/source/keep-me.jpg");

    // Verify deleted entry has no apply status
    strictEqual(manifest[0].apply, undefined);

    // Verify kept entry was marked as copied
    strictEqual(manifest[1].apply.status, "copied");
  });

  test("should use original filename when rename stage was skipped", async () => {
    const manifest = [
      {
        mediaPath: "/source/photos/IMG_1234.jpg",
        dedupe: {
          status: "keep",
        },
        // No rename property - rename stage was skipped
      },
    ];

    await apply(manifest, { destination: "/dest", skipEmbed: true });

    // Verify file was copied to destination with original filename
    strictEqual(copyFileMock.mock.calls[0].arguments[1], "/dest/IMG_1234.jpg");

    // Verify entry was marked as copied
    strictEqual(manifest[0].apply.status, "copied");
  });

  test("should use target path when rename stage was run", async () => {
    const manifest = [
      {
        mediaPath: "/source/IMG_1234.jpg",
        dedupe: {
          status: "keep",
        },
        rename: {
          status: "processed",
          targetPath: "2023/05 - May/20230515-120000.jpg",
        },
      },
    ];

    await apply(manifest, { destination: "/dest", skipEmbed: true });

    // Verify directory was created
    strictEqual(mkdirMock.mock.calls[0].arguments[0], "/dest/2023/05 - May");

    // Verify file was copied to target path
    strictEqual(copyFileMock.mock.calls[0].arguments[1], "/dest/2023/05 - May/20230515-120000.jpg");
  });

  test("should treat entries without dedupe as keepers", async () => {
    const manifest = [
      {
        mediaPath: "/source/photo.jpg",
        // No dedupe property - dedupe stage was skipped
        rename: {
          targetPath: "photo.jpg",
        },
      },
    ];

    await apply(manifest, { destination: "/dest", skipEmbed: true });

    // Verify file was copied
    strictEqual(copyFileMock.mock.callCount(), 1);

    // Verify entry was marked as copied
    strictEqual(manifest[0].apply.status, "copied");
  });

  test("should only check writeTags to decide embedding, not options", async () => {
    // This test verifies that apply doesn't check options.skipEmbed directly.
    // Instead, it relies on reconcile to have already respected skipEmbed
    // by not populating writeTags when skipEmbed is true.
    const manifest = [
      {
        mediaPath: "/source/photo.jpg",
        dedupe: {
          status: "keep",
        },
        rename: {
          targetPath: "photo.jpg",
        },
        metadata: {
          // When skipEmbed is true, reconcile sets writeTags to empty
          status: "noop",
          writeTags: [],
          dates: ["2023-01-01T12:00:00"],
        },
      },
    ];

    // Even with skipEmbed: false, apply should not embed because writeTags is empty
    await apply(manifest, { destination: "/dest", skipEmbed: false });

    // Verify no metadata was written
    strictEqual(writeMetadataMock.mock.callCount(), 0);

    // Verify entry status remains copied (not embedded)
    strictEqual(manifest[0].apply.status, "copied");
  });

  test("should skip embedding when entry has no writeTags", async () => {
    const manifest = [
      {
        mediaPath: "/source/photo.jpg",
        dedupe: {
          status: "keep",
        },
        rename: {
          targetPath: "photo.jpg",
        },
        metadata: {
          status: "noop",
          writeTags: [],
        },
      },
    ];

    await apply(manifest, { destination: "/dest" });

    // Verify no metadata was written
    strictEqual(writeMetadataMock.mock.callCount(), 0);

    // Verify entry status remains copied
    strictEqual(manifest[0].apply.status, "copied");
  });

  test("should skip embedding when metadata property is undefined", async () => {
    const manifest = [
      {
        mediaPath: "/source/photo.jpg",
        dedupe: {
          status: "keep",
        },
        rename: {
          targetPath: "photo.jpg",
        },
        // No metadata property - reconcile stage was skipped
      },
    ];

    await apply(manifest, { destination: "/dest" });

    // Verify no metadata was written
    strictEqual(writeMetadataMock.mock.callCount(), 0);

    // Verify entry status remains copied
    strictEqual(manifest[0].apply.status, "copied");
  });

  test("should embed metadata into copied files", async () => {
    const manifest = [
      {
        mediaPath: "/source/photo.jpg",
        dedupe: {
          status: "keep",
        },
        rename: {
          targetPath: "photo.jpg",
        },
        metadata: {
          status: "processed",
          writeTags: ["DateTimeOriginal=2023:01:01 12:00:00"],
        },
      },
    ];

    await apply(manifest, { destination: "/dest" });

    // Verify metadata was written
    strictEqual(writeMetadataMock.mock.callCount(), 1);

    // Verify metadata was written to the destination copy, not the source
    strictEqual(writeMetadataMock.mock.calls[0].arguments[0], "/dest/photo.jpg");
    deepStrictEqual(writeMetadataMock.mock.calls[0].arguments[1], [
      "DateTimeOriginal=2023:01:01 12:00:00",
    ]);

    // Verify entry status was updated to embedded
    strictEqual(manifest[0].apply.status, "embedded");
  });

  test("should mark entry as error when copy fails in non-strict mode", async () => {
    const manifest = [
      {
        mediaPath: "/source/photo.jpg",
        dedupe: {
          status: "keep",
        },
        rename: {
          targetPath: "photo.jpg",
        },
      },
    ];

    copyFileMock.mock.mockImplementation(async () => {
      throw new Error("ENOENT: no such file");
    });

    await apply(manifest, { destination: "/dest", skipEmbed: true, strict: false });

    // Verify entry was marked as error
    strictEqual(manifest[0].apply.status, "error");

    // Verify error message was stored
    strictEqual(manifest[0].apply.reason, "ENOENT: no such file");
  });

  test("should mark entry as error when embed fails in non-strict mode", async () => {
    const manifest = [
      {
        mediaPath: "/source/photo.jpg",
        dedupe: {
          status: "keep",
        },
        rename: {
          targetPath: "photo.jpg",
        },
        metadata: {
          status: "processed",
          writeTags: ["DateTimeOriginal=2023:01:01 12:00:00"],
        },
      },
    ];

    writeMetadataMock.mock.mockImplementation(async () => {
      throw new Error("exiftool failed");
    });

    await apply(manifest, { destination: "/dest", strict: false });

    // Verify entry was marked as error
    strictEqual(manifest[0].apply.status, "error");

    // Verify error message was stored
    strictEqual(manifest[0].apply.reason, "exiftool failed");
  });

  test("should store destPath in apply object for successfully copied files", async () => {
    const manifest = [
      {
        mediaPath: "/source/photo.jpg",
        dedupe: {
          status: "keep",
        },
        rename: {
          targetPath: "2023/05 - May/photo.jpg",
        },
      },
    ];

    await apply(manifest, { destination: "/dest", skipEmbed: true });

    // Verify destPath was stored
    strictEqual(manifest[0].apply.targetPath, "/dest/2023/05 - May/photo.jpg");
  });

  test("should copy sidecar alongside media when skipEmbed is true and sidecar exists", async () => {
    const manifest = [
      {
        mediaPath: "/source/photo.jpg",
        dedupe: {
          status: "keep",
        },
        rename: {
          targetPath: "2023/05 - May/photo.jpg",
        },
        json: {
          path: "/source/photo.jpg.json",
        },
      },
    ];

    await apply(manifest, { destination: "/dest", skipEmbed: true });

    // Verify both media and sidecar were copied
    strictEqual(copyFileMock.mock.callCount(), 2);

    // Verify sidecar was copied from source
    strictEqual(copyFileMock.mock.calls[1].arguments[0], "/source/photo.jpg.json");

    // Verify sidecar destination follows media name
    strictEqual(copyFileMock.mock.calls[1].arguments[1], "/dest/2023/05 - May/photo.jpg.json");
  });

  test("should not copy sidecar when skipEmbed is false", async () => {
    const manifest = [
      {
        mediaPath: "/source/photo.jpg",
        dedupe: {
          status: "keep",
        },
        rename: {
          targetPath: "photo.jpg",
        },
        json: {
          path: "/source/photo.jpg.json",
        },
      },
    ];

    await apply(manifest, { destination: "/dest", skipEmbed: false });

    // Verify only the media file was copied
    strictEqual(copyFileMock.mock.callCount(), 1);
  });

  test("should not copy sidecar when entry has no matched sidecar", async () => {
    const manifest = [
      {
        mediaPath: "/source/photo.jpg",
        dedupe: {
          status: "keep",
        },
        rename: {
          targetPath: "photo.jpg",
        },
        json: null,
      },
    ];

    await apply(manifest, { destination: "/dest", skipEmbed: true });

    // Verify only the media file was copied
    strictEqual(copyFileMock.mock.callCount(), 1);
  });

  test("should use original filename for sidecar when rename is skipped", async () => {
    const manifest = [
      {
        mediaPath: "/source/photos/IMG_1234.jpg",
        dedupe: {
          status: "keep",
        },
        json: {
          path: "/source/photos/IMG_1234.jpg.json",
        },
        // No rename property - rename stage was skipped
      },
    ];

    await apply(manifest, { destination: "/dest", skipEmbed: true });

    // Verify sidecar was copied using the original filename
    strictEqual(copyFileMock.mock.calls[1].arguments[1], "/dest/IMG_1234.jpg.json");
  });

  test("should mark entry as error when sidecar copy fails", async () => {
    const manifest = [
      {
        mediaPath: "/source/photo.jpg",
        dedupe: {
          status: "keep",
        },
        rename: {
          targetPath: "photo.jpg",
        },
        json: {
          path: "/source/photo.jpg.json",
        },
      },
    ];

    copyFileMock.mock.mockImplementation(async (src) => {
      if (src === "/source/photo.jpg.json") {
        throw new Error("ENOSPC: no space left");
      }
      return undefined;
    });

    await apply(manifest, { destination: "/dest", skipEmbed: true });

    // Verify entry was marked as error
    strictEqual(manifest[0].apply.status, "error");

    // Verify error message was stored
    strictEqual(manifest[0].apply.reason, "ENOSPC: no space left");
  });

  test("should not copy sidecar when skipEmbed is not set", async () => {
    const manifest = [
      {
        mediaPath: "/source/photo.jpg",
        dedupe: {
          status: "keep",
        },
        rename: {
          targetPath: "photo.jpg",
        },
        json: {
          path: "/source/photo.jpg.json",
        },
      },
    ];

    await apply(manifest, { destination: "/dest" });

    // Verify only the media file was copied
    strictEqual(copyFileMock.mock.callCount(), 1);
  });

  test("should handle nested album paths correctly", async () => {
    const manifest = [
      {
        mediaPath: "/source/photo.jpg",
        dedupe: {
          status: "keep",
        },
        rename: {
          status: "processed",
          targetPath: "2023/05 - May/20230501 - Vacation/20230515-120000.jpg",
        },
      },
    ];

    await apply(manifest, { destination: "/dest", skipEmbed: true });

    // Verify full nested directory was created
    strictEqual(mkdirMock.mock.calls[0].arguments[0], "/dest/2023/05 - May/20230501 - Vacation");

    // Verify file was copied to correct nested path
    strictEqual(
      copyFileMock.mock.calls[0].arguments[1],
      "/dest/2023/05 - May/20230501 - Vacation/20230515-120000.jpg"
    );
  });
});
