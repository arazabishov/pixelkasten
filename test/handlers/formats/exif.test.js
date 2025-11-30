import { test, describe, beforeEach, mock } from "node:test";
import { strictEqual, deepStrictEqual } from "node:assert";

const normalizeDiskDateMock = mock.fn((date) => {
  return date;
});
mock.module("../../../src/core/datetime.js", {
  namedExports: {
    normalizeDiskDate: normalizeDiskDateMock,
  },
});

const parseCompositeGeoMock = mock.fn(() => {
  return null;
});
mock.module("../../../src/handlers/composite.js", {
  namedExports: {
    compositeGeoTags: ["Composite:GPSAltitude", "Composite:GPSLatitude", "Composite:GPSLongitude"],
    parseCompositeGeo: parseCompositeGeoMock,
  },
});

const { exifHandler } = await import("../../../src/handlers/formats/exif.js");

describe("exifHandler", () => {
  beforeEach(() => {
    [normalizeDiskDateMock, parseCompositeGeoMock].forEach((m) => {
      m.mock.resetCalls();
    });

    // Set default mocks
    normalizeDiskDateMock.mock.mockImplementation((date) => {
      return date;
    });
    parseCompositeGeoMock.mock.mockImplementation(() => {
      return null;
    });
  });

  describe("parse", () => {
    test("should extract timestamp from DateTimeOriginal", () => {
      const result = exifHandler.parse({
        "EXIF:DateTimeOriginal": "2023:05:20 14:30:00",
      });

      // Verify timestamp is extracted and normalized
      strictEqual(result.timestamp, "2023:05:20 14:30:00");

      // Verify normalizeDiskDate was called with DateTimeOriginal
      strictEqual(normalizeDiskDateMock.mock.callCount(), 7);
      strictEqual(normalizeDiskDateMock.mock.calls[0].arguments[0], "2023:05:20 14:30:00");
    });

    test("should extract and normalize all date fields", () => {
      const result = exifHandler.parse({
        "EXIF:DateTimeOriginal": "2023:05:20 14:30:00",
        "EXIF:CreateDate": "2023:05:20 14:30:01",
        "Composite:GPSDateTime": "2023:05:20 14:30:02",
        "EXIF:ModifyDate": "2023:05:20 14:30:03",
        "File:FileCreateDate": "2023:05:20 14:30:04",
        "File:FileModifyDate": "2023:05:20 14:30:05",
      });

      // Verify all dates are in the dates array
      strictEqual(result.dates.length, 6);

      // Verify dates are in priority order
      deepStrictEqual(result.dates, [
        "2023:05:20 14:30:00",
        "2023:05:20 14:30:01",
        "2023:05:20 14:30:02",
        "2023:05:20 14:30:03",
        "2023:05:20 14:30:04",
        "2023:05:20 14:30:05",
      ]);
    });

    test("should filter out null dates when normalizeDiskDate returns null", () => {
      normalizeDiskDateMock.mock.mockImplementation((date) => {
        if (date === "invalid") {
          return null;
        }
        return date;
      });

      const result = exifHandler.parse({
        "EXIF:DateTimeOriginal": "2023:05:20 14:30:00",
        "EXIF:CreateDate": "invalid",
        "EXIF:ModifyDate": "2023:05:20 14:30:03",
      });

      // Verify only valid dates are included
      strictEqual(result.dates.length, 2);

      deepStrictEqual(result.dates, ["2023:05:20 14:30:00", "2023:05:20 14:30:03"]);
    });

    test("should handle missing date fields gracefully", () => {
      normalizeDiskDateMock.mock.mockImplementation((date) => {
        return date || null;
      });

      const result = exifHandler.parse({});

      // Verify timestamp is undefined when normalized to null
      strictEqual(result.timestamp, null);

      // Verify dates array is empty when all dates are missing
      strictEqual(result.dates.length, 0);
    });

    test("should extract geo data via parseCompositeGeo", () => {
      const raw = {
        "Composite:GPSLatitude": 40.7128,
        "Composite:GPSLongitude": -74.006,
        "Composite:GPSAltitude": 10,
      };

      const geo = {
        latitude: 40.7128,
        longitude: -74.006,
        altitude: 10,
      };

      parseCompositeGeoMock.mock.mockImplementation(() => {
        return geo;
      });

      const result = exifHandler.parse(raw);

      // Verify geo data is extracted
      deepStrictEqual(result.geo, geo);

      // Verify parseCompositeGeo was called with raw data
      strictEqual(parseCompositeGeoMock.mock.callCount(), 1);
      deepStrictEqual(parseCompositeGeoMock.mock.calls[0].arguments[0], raw);
    });

    test("should return null geo when no geo data is present", () => {
      const result = exifHandler.parse({
        "EXIF:DateTimeOriginal": "2023:05:20 14:30:00",
      });

      // Verify geo is null when not present
      strictEqual(result.geo, null);
    });
  });

  describe("timestamp", () => {
    test("should return SubSecDateTimeOriginal tag for writing", () => {
      const result = exifHandler.timestamp("2023:05:20 14:30:00+00:00");

      // Verify correct tag is returned for writing
      deepStrictEqual(result, ["SubSecDateTimeOriginal=2023:05:20 14:30:00+00:00"]);
    });
  });

  describe("geo", () => {
    test("should return all required GPS tags for writing", () => {
      const result = exifHandler.geo({
        latitude: 40.7128,
        longitude: -74.006,
        altitude: 10,
      });

      // Verify all GPS tags are returned
      strictEqual(result.length, 4);

      // Verify composite latitude tag
      strictEqual(result[0], "Composite:GPSLatitude=40.7128");

      // Verify composite longitude tag
      strictEqual(result[1], "Composite:GPSLongitude=-74.006");

      // Verify altitude tag
      strictEqual(result[2], "GPSAltitude=10");

      // Verify altitude reference tag
      strictEqual(result[3], "GPSAltitudeRef=10");
    });

    test("should handle negative altitude", () => {
      const result = exifHandler.geo({
        latitude: 40.7128,
        longitude: -74.006,
        altitude: -5,
      });

      // Verify altitude reference is set correctly for below sea level
      strictEqual(result[2], "GPSAltitude=-5");

      strictEqual(result[3], "GPSAltitudeRef=-5");
    });
  });

  describe("readTags", () => {
    test("should include all required EXIF date tags", () => {
      // Verify date tags are present
      strictEqual(exifHandler.readTags.includes("EXIF:DateTimeOriginal"), true);

      strictEqual(exifHandler.readTags.includes("EXIF:CreateDate"), true);

      strictEqual(exifHandler.readTags.includes("EXIF:ModifyDate"), true);

      strictEqual(exifHandler.readTags.includes("Composite:GPSDateTime"), true);

      strictEqual(exifHandler.readTags.includes("File:FileCreateDate"), true);

      strictEqual(exifHandler.readTags.includes("File:FileModifyDate"), true);
    });

    test("should include composite geo tags", () => {
      // Verify geo tags from composite are included
      strictEqual(exifHandler.readTags.includes("Composite:GPSAltitude"), true);

      strictEqual(exifHandler.readTags.includes("Composite:GPSLatitude"), true);

      strictEqual(exifHandler.readTags.includes("Composite:GPSLongitude"), true);
    });
  });
});
