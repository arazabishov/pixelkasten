import { test, describe, beforeEach, mock } from "node:test";
import { strictEqual, deepStrictEqual, ok, rejects } from "node:assert";

mock.module("../../src/utils/logger.js", {
  namedExports: {
    logger: {
      error: mock.fn(),
      info: mock.fn(),
      warn: mock.fn(),
    },
  },
});
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

const readMetadataMock = mock.fn();
mock.module("../../src/core/exiftool.js", {
  namedExports: {
    readMetadata: readMetadataMock,
  },
});

const readSidecarMock = mock.fn();
mock.module("../../src/core/sidecar.js", {
  namedExports: {
    readSidecar: readSidecarMock,
  },
});

const handlerMock = {
  readTags: ["CreateDate", "GPSLatitude"],
  parse: mock.fn(),
  timestamp: mock.fn(),
  geo: mock.fn(),
};
mock.module("../../src/handlers/index.js", {
  namedExports: {
    handlers: {
      ".jpg": handlerMock,
      ".jpeg": handlerMock,
    },
  },
});

const transformPhotoTakenTimeMock = mock.fn((ts) => ts);
mock.module("../../src/core/datetime.js", {
  namedExports: {
    transformPhotoTakenTime: transformPhotoTakenTimeMock,
  },
});

const { reconcile } = await import("../../src/stages/reconcile.js");

describe("reconcile", () => {
  beforeEach(() => {
    [
      transformPhotoTakenTimeMock,
      readMetadataMock,
      readSidecarMock,
      handlerMock.timestamp,
      handlerMock.parse,
      handlerMock.geo,
    ].forEach((m) => m.mock.resetCalls());

    // Set default mock: no sidecar file exists (most common case)
    readSidecarMock.mock.mockImplementation(async () => {
      return null;
    });
  });

  test("should not perform disk operations when manifest is empty", async () => {
    const manifest = [];

    await reconcile(manifest, {});

    // Verify no entries were added
    strictEqual(manifest.length, 0);

    // Verify no metadata was read from disk
    strictEqual(readMetadataMock.mock.callCount(), 0);

    // Verify no sidecar was read from disk
    strictEqual(readSidecarMock.mock.callCount(), 0);
  });

  test("should skip disk operations for entries marked for deletion", async () => {
    const manifest = [
      { dedupe: { action: "delete" } },
      { dedupe: { action: "keep" }, mediaPath: "test.jpg" },
    ];

    readMetadataMock.mock.mockImplementation(async () => {
      return new Map([["test.jpg", { CreateDate: "2023:01:01 12:00:00" }]]);
    });
    handlerMock.parse.mock.mockImplementation(() => {
      return {
        timestamp: "2023-01-01T12:00:00.000Z",
        dates: ["2023-01-01T12:00:00.000Z"],
      };
    });

    await reconcile(manifest, {});

    // Verify only one entry was processed
    strictEqual(readMetadataMock.mock.callCount(), 1);

    // Verify sidecar was read once
    strictEqual(readSidecarMock.mock.callCount(), 1);

    // Verify only the kept entry's media path was passed
    deepStrictEqual(readMetadataMock.mock.calls[0].arguments[0], ["test.jpg"]);
  });

  test("should not queue metadata writes when no sidecar exists", async () => {
    const manifest = [{ mediaPath: "/path/image.jpg", jsonPath: "/path/image.json" }];

    readMetadataMock.mock.mockImplementation(async () => {
      return new Map([["/path/image.jpg", { CreateDate: "2023:01:01 12:00:00" }]]);
    });
    handlerMock.parse.mock.mockImplementation(() => {
      return {
        timestamp: "2023-01-01T12:00:00.000Z",
        dates: ["2023-01-01T12:00:00.000Z"],
      };
    });

    await reconcile(manifest, {});

    // Verify no metadata changes were needed
    strictEqual(manifest[0].metadata.status, "noop");

    // Verify no tags were queued for writing
    strictEqual(manifest[0].metadata.writeTags.length, 0);

    // Verify dates from disk are preserved even without sidecar
    deepStrictEqual(manifest[0].metadata.dates, ["2023-01-01T12:00:00.000Z"]);
  });

  test("should not queue metadata writes when disk already has sidecar data", async () => {
    const manifest = [{ mediaPath: "/path/image.jpg", jsonPath: "/path/image.json" }];

    readMetadataMock.mock.mockImplementation(async () => {
      return new Map([["/path/image.jpg", { CreateDate: "2023:01:01 12:00:00" }]]);
    });
    readSidecarMock.mock.mockImplementation(async () => {
      return { timestamp: "1672574400" };
    });
    handlerMock.parse.mock.mockImplementation(() => {
      return {
        timestamp: "2023-01-01T12:00:00.000Z",
        dates: ["2023-01-01T12:00:00.000Z"],
      };
    });

    await reconcile(manifest, {});

    // Verify no metadata changes were needed
    strictEqual(manifest[0].metadata.status, "noop");
  });

  test("should queue timestamp write when missing from disk metadata", async () => {
    const manifest = [{ mediaPath: "/path/image.jpg", jsonPath: "/path/image.json" }];

    readMetadataMock.mock.mockImplementation(async () => {
      return new Map([["/path/image.jpg", {}]]);
    });
    readSidecarMock.mock.mockImplementation(async () => {
      return { timestamp: "1672574400" };
    });
    handlerMock.parse.mock.mockImplementation(() => {
      return { timestamp: null, dates: [] };
    });
    handlerMock.timestamp.mock.mockImplementation((ts) => {
      return [`DateTimeOriginal=${ts}`];
    });
    transformPhotoTakenTimeMock.mock.mockImplementation((_) => {
      return `2023-01-01T12:00:00.000Z`;
    });

    await reconcile(manifest, {});

    // Verify entry was marked for processing
    strictEqual(manifest[0].metadata.status, "processed");

    // Verify one tag was queued for writing
    strictEqual(manifest[0].metadata.writeTags.length, 1);

    // Verify timestamp was added to dates
    strictEqual(manifest[0].metadata.dates[0], "2023-01-01T12:00:00.000Z");
  });

  test("should queue geo write when missing from disk metadata", async () => {
    const manifest = [{ mediaPath: "/path/image.jpg", jsonPath: "/path/image.json" }];

    readMetadataMock.mock.mockImplementation(async () => {
      return new Map([["/path/image.jpg", {}]]);
    });
    readSidecarMock.mock.mockImplementation(async () => {
      return { geo: { latitude: 40.7128, longitude: -74.006 } };
    });
    handlerMock.parse.mock.mockImplementation(() => {
      return { timestamp: null, dates: [], geo: null };
    });
    handlerMock.geo.mock.mockImplementation((geo) => {
      return [`GPSLatitude=${geo.latitude}`, `GPSLongitude=${geo.longitude}`];
    });

    await reconcile(manifest, {});

    // Verify entry was marked for processing
    strictEqual(manifest[0].metadata.status, "processed");

    // Verify two geo tags were queued for writing
    strictEqual(manifest[0].metadata.writeTags.length, 2);
  });

  test("should queue timestamp and geo writes when both missing from disk", async () => {
    const manifest = [{ mediaPath: "/path/image.jpg", jsonPath: "/path/image.json" }];

    readMetadataMock.mock.mockImplementation(async () => {
      return new Map([["/path/image.jpg", {}]]);
    });
    readSidecarMock.mock.mockImplementation(async () => {
      return {
        timestamp: "1672574400",
        geo: { latitude: 40.7128, longitude: -74.006 },
      };
    });
    handlerMock.parse.mock.mockImplementation(() => {
      return { timestamp: null, dates: [], geo: null };
    });
    handlerMock.timestamp.mock.mockImplementation((ts) => {
      return [`DateTimeOriginal=${ts}`];
    });
    handlerMock.geo.mock.mockImplementation((geo) => {
      return [`GPSLatitude=${geo.latitude}`];
    });
    transformPhotoTakenTimeMock.mock.mockImplementation((_) => {
      return `2023-01-01T12:00:00.000Z`;
    });

    await reconcile(manifest, {});

    // Verify entry was marked for processing
    strictEqual(manifest[0].metadata.status, "processed");

    // Verify both timestamp and geo tags were queued
    strictEqual(manifest[0].metadata.writeTags.length, 2);

    // Verify timestamp was added to dates
    strictEqual(manifest[0].metadata.dates[0], "2023-01-01T12:00:00.000Z");
  });

  test("should read metadata for all entries regardless of manifest size", async () => {
    const manifest = Array.from({ length: 1000 }, (_, i) => ({
      mediaPath: `/path/image${i}.jpg`,
      jsonPath: `/path/image${i}.json`,
    }));

    readMetadataMock.mock.mockImplementation(async (paths) => {
      const map = new Map();
      paths.forEach((path) => map.set(path, {}));
      return map;
    });
    handlerMock.parse.mock.mockImplementation(() => {
      return { timestamp: null, dates: [] };
    });

    await reconcile(manifest, {});

    // Verify metadata was read in exactly 2 batches
    strictEqual(readMetadataMock.mock.callCount(), 2);

    // Verify first batch contained 512 items
    strictEqual(readMetadataMock.mock.calls[0].arguments[0].length, 512);

    // Verify second batch contained remaining 488 items
    strictEqual(readMetadataMock.mock.calls[1].arguments[0].length, 488);

    // Verify tags were passed to readMetadata
    ok(readMetadataMock.mock.calls[0].arguments[1].includes("CreateDate"));
  });

  test("should log errors in non-strict mode", async () => {
    const manifest = [{ mediaPath: "/path/image.jpg" }];

    readMetadataMock.mock.mockImplementation(async () => {
      return new Map();
    });

    await reconcile(manifest, { strict: false });

    // Verify error was logged without throwing
    strictEqual(manifest[0].metadata.status, "error");
  });

  test("should throw errors in strict mode", async () => {
    const manifest = [{ mediaPath: "/path/image.jpg" }];

    readMetadataMock.mock.mockImplementation(async () => {
      return new Map();
    });

    // Verify error was thrown with expected message
    await rejects(
      async () => await reconcile(manifest, { strict: true }),
      /ExifTool did not report/
    );
  });

  test("should mark entries with unsupported file types as errors", async () => {
    const manifest = [{ mediaPath: "/path/image.unknown", jsonPath: "/path/image.json" }];

    readMetadataMock.mock.mockImplementation(async () => {
      return new Map([["/path/image.unknown", {}]]);
    });

    await reconcile(manifest, { strict: false });

    // Verify unsupported file type resulted in error
    strictEqual(manifest[0].metadata.status, "error");
  });
});
