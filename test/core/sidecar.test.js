import { test, describe, mock } from "node:test";
import { strictEqual, deepStrictEqual, rejects } from "node:assert";

const readFileMock = mock.fn();
mock.module("fs/promises", {
  namedExports: {
    readFile: readFileMock,
  },
});

const { readSidecar } = await import("../../src/core/sidecar.js");

describe("readSidecar", () => {
  test("should return null when jsonPath is falsy", async () => {
    const result = await readSidecar(null);

    // Verify null path returns null without reading from disk
    strictEqual(result, null);

    // Verify no file read was attempted
    strictEqual(readFileMock.mock.callCount(), 0);
  });

  test("should extract timestamp from photoTakenTime", async () => {
    readFileMock.mock.mockImplementation(async () => {
      return JSON.stringify({
        photoTakenTime: { timestamp: "1719935787", formatted: "Jul 2, 2024" },
        geoData: { latitude: 0.0, longitude: 0.0, altitude: 0.0 },
      });
    });

    const result = await readSidecar("/path/to/sidecar.json");

    // Verify timestamp is extracted
    strictEqual(result.timestamp, "1719935787");
  });

  test("should return undefined timestamp when photoTakenTime is absent", async () => {
    readFileMock.mock.mockImplementation(async () => {
      return JSON.stringify({
        geoData: { latitude: 0.0, longitude: 0.0, altitude: 0.0 },
      });
    });

    const result = await readSidecar("/path/to/sidecar.json");

    // Verify timestamp is undefined when photoTakenTime is missing
    strictEqual(result.timestamp, undefined);
  });

  test("should prefer geoDataExif over geoData", async () => {
    readFileMock.mock.mockImplementation(async () => {
      return JSON.stringify({
        photoTakenTime: { timestamp: "1719935787" },
        geoData: {
          latitude: 10.0,
          longitude: 20.0,
          altitude: 5.0,
          latitudeSpan: 0.0,
          longitudeSpan: 0.0,
        },
        geoDataExif: {
          latitude: 48.8584,
          longitude: 2.2945,
          altitude: 35.0,
          latitudeSpan: 0.0,
          longitudeSpan: 0.0,
        },
      });
    });

    const result = await readSidecar("/path/to/sidecar.json");

    // Verify geoDataExif values are used, not geoData
    deepStrictEqual(result.geo, {
      latitude: 48.8584,
      longitude: 2.2945,
      altitude: 35.0,
    });
  });

  test("should fall back to geoData when geoDataExif is absent", async () => {
    readFileMock.mock.mockImplementation(async () => {
      return JSON.stringify({
        photoTakenTime: { timestamp: "1719935787" },
        geoData: {
          latitude: 40.6892,
          longitude: -74.0445,
          altitude: 10.0,
          latitudeSpan: 0.0,
          longitudeSpan: 0.0,
        },
      });
    });

    const result = await readSidecar("/path/to/sidecar.json");

    // Verify geoData values are used when geoDataExif is missing
    deepStrictEqual(result.geo, {
      latitude: 40.6892,
      longitude: -74.0445,
      altitude: 10.0,
    });
  });

  test("should treat geoData with (0, 0) coordinates as missing location", async () => {
    readFileMock.mock.mockImplementation(async () => {
      return JSON.stringify({
        photoTakenTime: { timestamp: "1719935787" },
        geoData: {
          latitude: 0.0,
          longitude: 0.0,
          altitude: 0.0,
          latitudeSpan: 0.0,
          longitudeSpan: 0.0,
        },
      });
    });

    const result = await readSidecar("/path/to/sidecar.json");

    // Verify (0, 0) is treated as no geo data (Google's default for missing location)
    strictEqual(result.geo, undefined);
  });

  test("should treat geoDataExif with (0, 0) coordinates as missing location", async () => {
    readFileMock.mock.mockImplementation(async () => {
      return JSON.stringify({
        photoTakenTime: { timestamp: "1719935787" },
        geoData: {
          latitude: 0.0,
          longitude: 0.0,
          altitude: 0.0,
        },
        geoDataExif: {
          latitude: 0,
          longitude: 0,
          altitude: 0,
        },
      });
    });

    const result = await readSidecar("/path/to/sidecar.json");

    // Verify (0, 0) in geoDataExif is also treated as missing
    strictEqual(result.geo, undefined);
  });

  test("should fall back to geoData when geoDataExif has (0, 0) but geoData has real coordinates", async () => {
    readFileMock.mock.mockImplementation(async () => {
      return JSON.stringify({
        photoTakenTime: { timestamp: "1719935787" },
        geoData: {
          latitude: 40.6892,
          longitude: -74.0445,
          altitude: 10.0,
        },
        geoDataExif: {
          latitude: 0,
          longitude: 0,
          altitude: 0,
        },
      });
    });

    const result = await readSidecar("/path/to/sidecar.json");

    // Verify geoDataExif (0,0) is skipped and geoData is used instead
    deepStrictEqual(result.geo, {
      latitude: 40.6892,
      longitude: -74.0445,
      altitude: 10.0,
    });
  });

  test("should strip latitudeSpan and longitudeSpan from geo output", async () => {
    readFileMock.mock.mockImplementation(async () => {
      return JSON.stringify({
        photoTakenTime: { timestamp: "1719935787" },
        geoDataExif: {
          latitude: 48.8584,
          longitude: 2.2945,
          altitude: 35.0,
          latitudeSpan: 0.003,
          longitudeSpan: 0.004,
        },
      });
    });

    const result = await readSidecar("/path/to/sidecar.json");

    // Verify span fields are not included in the output
    strictEqual(result.geo.latitudeSpan, undefined);
    strictEqual(result.geo.longitudeSpan, undefined);
  });

  test("should handle negative altitude (below sea level)", async () => {
    readFileMock.mock.mockImplementation(async () => {
      return JSON.stringify({
        photoTakenTime: { timestamp: "1735645750" },
        geoDataExif: {
          latitude: 40.3865,
          longitude: 49.8916,
          altitude: -11.19,
        },
      });
    });

    const result = await readSidecar("/path/to/sidecar.json");

    // Verify negative altitude is preserved (below sea level, e.g. near Dead Sea)
    strictEqual(result.geo.altitude, -11.19);
  });

  test("should ignore extra fields not used by the pipeline", async () => {
    readFileMock.mock.mockImplementation(async () => {
      return JSON.stringify({
        title: "IMG_001.jpg",
        description: "My vacation photo",
        imageViews: "42",
        creationTime: { timestamp: "1700000000" },
        photoTakenTime: { timestamp: "1719935787" },
        geoData: { latitude: 0.0, longitude: 0.0, altitude: 0.0 },
        url: "https://photos.google.com/photo/abc123",
        googlePhotosOrigin: { mobileUpload: { deviceType: "IOS_PHONE" } },
      });
    });

    const result = await readSidecar("/path/to/sidecar.json");

    // Verify only the fields we care about are returned
    strictEqual(result.timestamp, "1719935787");
    strictEqual(result.geo, undefined);
    strictEqual(result.title, undefined);
    strictEqual(result.description, undefined);
  });

  test("should throw a descriptive error for malformed JSON", async () => {
    readFileMock.mock.mockImplementation(async () => {
      return "{ not valid json";
    });

    // Verify error message includes the file path
    await rejects(
      () => readSidecar("/path/to/broken.json"),
      (err) => {
        return err.message.includes("Failed to read sidecar file at /path/to/broken.json");
      }
    );
  });

  test("should throw a descriptive error when file cannot be read", async () => {
    readFileMock.mock.mockImplementation(async () => {
      throw new Error("ENOENT: no such file or directory");
    });

    // Verify error message wraps the underlying error
    await rejects(
      () => readSidecar("/path/to/missing.json"),
      (err) => {
        return (
          err.message.includes("Failed to read sidecar file at /path/to/missing.json") &&
          err.message.includes("ENOENT")
        );
      }
    );
  });
});
