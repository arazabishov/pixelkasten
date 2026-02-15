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

const { quicktimeHandler } = await import("../../../src/handlers/formats/quicktime.js");

describe("quicktimeHandler", () => {
  beforeEach(() => {
    [normalizeDiskDateMock, parseCompositeGeoMock].forEach((m) => {
      m.mock.resetCalls();
    });

    normalizeDiskDateMock.mock.mockImplementation((date) => {
      return date;
    });
    parseCompositeGeoMock.mock.mockImplementation(() => {
      return null;
    });
  });

  describe("parse", () => {
    test("should extract timestamp from CreationDate", () => {
      const result = quicktimeHandler.parse({
        "QuickTime:CreationDate": "2024:03:15 10:30:00",
      });

      // Verify timestamp is extracted and normalized
      strictEqual(result.timestamp, "2024:03:15 10:30:00");

      // Verify normalizeDiskDate was called with CreationDate
      strictEqual(normalizeDiskDateMock.mock.callCount(), 7);
      strictEqual(normalizeDiskDateMock.mock.calls[0].arguments[0], "2024:03:15 10:30:00");
    });

    test("should extract and normalize all date fields", () => {
      const result = quicktimeHandler.parse({
        "QuickTime:CreationDate": "2024:03:15 10:30:00",
        "QuickTime:CreateDate": "2024:03:15 10:30:01",
        "QuickTime:GPSDateTime": "2024:03:15 10:30:02",
        "QuickTime:ModifyDate": "2024:03:15 10:30:03",
        "File:FileCreateDate": "2024:03:15 10:30:04+02:00",
        "File:FileModifyDate": "2024:03:15 10:30:05+02:00",
      });

      // Verify all dates are in the dates array
      strictEqual(result.dates.length, 6);

      // Verify dates are in priority order
      deepStrictEqual(result.dates, [
        "2024:03:15 10:30:00",
        "2024:03:15 10:30:01",
        "2024:03:15 10:30:02",
        "2024:03:15 10:30:03",
        "2024:03:15 10:30:04+02:00",
        "2024:03:15 10:30:05+02:00",
      ]);
    });

    test("should filter out null dates when normalizeDiskDate returns null", () => {
      normalizeDiskDateMock.mock.mockImplementation((date) => {
        if (date === "invalid") {
          return null;
        }
        return date;
      });

      const result = quicktimeHandler.parse({
        "QuickTime:CreationDate": "2024:03:15 10:30:00",
        "QuickTime:CreateDate": "invalid",
        "QuickTime:ModifyDate": "2024:03:15 10:30:03",
      });

      // Verify only valid dates are included
      strictEqual(result.dates.length, 2);

      deepStrictEqual(result.dates, ["2024:03:15 10:30:00", "2024:03:15 10:30:03"]);
    });

    test("should handle missing date fields gracefully", () => {
      normalizeDiskDateMock.mock.mockImplementation((date) => {
        return date || null;
      });

      const result = quicktimeHandler.parse({});

      // Verify timestamp is null when normalized to null
      strictEqual(result.timestamp, null);

      // Verify dates array is empty when all dates are missing
      strictEqual(result.dates.length, 0);
    });

    test("should extract geo data via parseCompositeGeo", () => {
      const raw = {
        "Composite:GPSLatitude": 37.7749,
        "Composite:GPSLongitude": -122.4194,
        "Composite:GPSAltitude": 50,
      };

      const geo = {
        latitude: 37.7749,
        longitude: -122.4194,
        altitude: 50,
      };

      parseCompositeGeoMock.mock.mockImplementation(() => {
        return geo;
      });

      const result = quicktimeHandler.parse(raw);

      // Verify geo data is extracted
      deepStrictEqual(result.geo, geo);

      // Verify parseCompositeGeo was called with raw data
      strictEqual(parseCompositeGeoMock.mock.callCount(), 1);
      deepStrictEqual(parseCompositeGeoMock.mock.calls[0].arguments[0], raw);
    });

    test("should return null geo when no geo data is present", () => {
      const result = quicktimeHandler.parse({
        "QuickTime:CreationDate": "2024:03:15 10:30:00",
      });

      // Verify geo is null when not present
      strictEqual(result.geo, null);
    });
  });

  describe("timestamp", () => {
    test("should return CreationDate tag for writing", () => {
      const result = quicktimeHandler.timestamp("2024:03:15 10:30:00+00:00");

      // Verify correct tag is returned for writing
      deepStrictEqual(result, ["CreationDate=2024:03:15 10:30:00+00:00"]);
    });
  });

  describe("geo", () => {
    test("should return Keys:GPSCoordinates tag for writing", () => {
      const result = quicktimeHandler.geo({
        latitude: 37.7749,
        longitude: -122.4194,
        altitude: 50,
      });

      // Verify GPS coordinates tag is returned
      strictEqual(result.length, 1);

      // Verify coordinates are formatted correctly
      strictEqual(result[0], "Keys:GPSCoordinates=37.7749, -122.4194, 50");
    });

    test("should handle negative coordinates", () => {
      const result = quicktimeHandler.geo({
        latitude: -33.8688,
        longitude: 151.2093,
        altitude: -10,
      });

      // Verify negative coordinates are handled correctly
      strictEqual(result[0], "Keys:GPSCoordinates=-33.8688, 151.2093, -10");
    });
  });

  describe("readTags", () => {
    test("should include all required QuickTime date tags", () => {
      // Verify QuickTime date tags are present
      strictEqual(quicktimeHandler.readTags.includes("QuickTime:CreationDate"), true);

      strictEqual(quicktimeHandler.readTags.includes("QuickTime:CreateDate"), true);

      strictEqual(quicktimeHandler.readTags.includes("QuickTime:ModifyDate"), true);

      strictEqual(quicktimeHandler.readTags.includes("File:FileCreateDate"), true);

      strictEqual(quicktimeHandler.readTags.includes("File:FileModifyDate"), true);
    });

    test("should include composite geo tags", () => {
      // Verify geo tags from composite are included
      strictEqual(quicktimeHandler.readTags.includes("Composite:GPSAltitude"), true);

      strictEqual(quicktimeHandler.readTags.includes("Composite:GPSLatitude"), true);

      strictEqual(quicktimeHandler.readTags.includes("Composite:GPSLongitude"), true);
    });
  });
});
