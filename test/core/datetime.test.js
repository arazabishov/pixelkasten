import { test, describe } from "node:test";
import { strictEqual, throws } from "node:assert";
import { parsePhotoTakenTime, normalizeDiskDate } from "../../src/core/datetime.js";

describe("normalizeDiskDate", () => {
  describe("EXIF date formats", () => {
    test("should normalize standard EXIF DateTimeOriginal format", () => {
      const result = normalizeDiskDate("2023:05:20 14:30:00");

      // Verify standard EXIF format is normalized to ISO
      strictEqual(result, "2023-05-20T14:30:00");
    });

    test("should normalize EXIF CreateDate format", () => {
      const result = normalizeDiskDate("2024:03:15 08:45:30");

      // Verify EXIF date with different values
      strictEqual(result, "2024-03-15T08:45:30");
    });

    test("should normalize midnight timestamp", () => {
      const result = normalizeDiskDate("2023:01:01 00:00:00");

      // Verify midnight is handled correctly
      strictEqual(result, "2023-01-01T00:00:00");
    });

    test("should normalize end of day timestamp", () => {
      const result = normalizeDiskDate("2023:12:31 23:59:59");

      // Verify end of day is handled correctly
      strictEqual(result, "2023-12-31T23:59:59");
    });
  });

  describe("timezone handling (wall clock preservation)", () => {
    test("should ignore negative timezone offset", () => {
      const result = normalizeDiskDate("2023:05:20 14:30:00-05:00");

      // Verify timezone offset is ignored, preserving wall clock time
      strictEqual(result, "2023-05-20T14:30:00");
    });

    test("should ignore positive timezone offset", () => {
      const result = normalizeDiskDate("2023:05:20 14:30:00+02:00");

      // Verify positive timezone offset is ignored
      strictEqual(result, "2023-05-20T14:30:00");
    });

    test("should ignore UTC timezone marker (Z)", () => {
      const result = normalizeDiskDate("2023:05:20 14:30:00Z");

      // Verify Z timezone marker is ignored
      strictEqual(result, "2023-05-20T14:30:00");
    });

    test("should ignore timezone with fractional offset", () => {
      const result = normalizeDiskDate("2023:05:20 14:30:00+05:30");

      // Verify fractional timezone offset (e.g., India) is ignored
      strictEqual(result, "2023-05-20T14:30:00");
    });
  });

  describe("alternative date formats", () => {
    test("should handle dates with dash separators", () => {
      const result = normalizeDiskDate("2023-05-20 14:30:00");

      // Verify dates with dashes instead of colons are accepted
      strictEqual(result, "2023-05-20T14:30:00");
    });

    test("should handle mixed separators", () => {
      const result = normalizeDiskDate("2023-05-20 14:30:00");

      // Verify mixed date separators work
      strictEqual(result, "2023-05-20T14:30:00");
    });
  });

  describe("whitespace handling", () => {
    test("should trim leading whitespace", () => {
      const result = normalizeDiskDate("  2023:05:20 14:30:00");

      // Verify leading whitespace is trimmed
      strictEqual(result, "2023-05-20T14:30:00");
    });

    test("should trim trailing whitespace", () => {
      const result = normalizeDiskDate("2023:05:20 14:30:00  ");

      // Verify trailing whitespace is trimmed
      strictEqual(result, "2023-05-20T14:30:00");
    });

    test("should trim both leading and trailing whitespace", () => {
      const result = normalizeDiskDate("  2023:05:20 14:30:00  ");

      // Verify both leading and trailing whitespace is trimmed
      strictEqual(result, "2023-05-20T14:30:00");
    });
  });

  describe("invalid inputs", () => {
    test("should return null for undefined", () => {
      const result = normalizeDiskDate(undefined);

      // Verify undefined returns null
      strictEqual(result, null);
    });

    test("should return null for null", () => {
      const result = normalizeDiskDate(null);

      // Verify null input returns null
      strictEqual(result, null);
    });

    test("should return null for empty string", () => {
      const result = normalizeDiskDate("");

      // Verify empty string returns null
      strictEqual(result, null);
    });

    test("should return null for non-string input", () => {
      const result = normalizeDiskDate(12345);

      // Verify number input returns null
      strictEqual(result, null);
    });

    test("should return null for invalid date format", () => {
      const result = normalizeDiskDate("invalid date");

      // Verify invalid format returns null
      strictEqual(result, null);
    });

    test("should return null for incomplete date", () => {
      const result = normalizeDiskDate("2023:05:20");

      // Verify date without time returns null
      strictEqual(result, null);
    });

    test("should return null for date with missing components", () => {
      const result = normalizeDiskDate("2023:05 14:30:00");

      // Verify incomplete date components return null
      strictEqual(result, null);
    });
  });

  describe("edge cases", () => {
    test("should handle leap year date", () => {
      const result = normalizeDiskDate("2024:02:29 12:00:00");

      // Verify leap year date is normalized correctly
      strictEqual(result, "2024-02-29T12:00:00");
    });

    test("should handle single digit hours/minutes/seconds (zero-padded)", () => {
      const result = normalizeDiskDate("2023:05:20 01:02:03");

      // Verify zero-padded time components
      strictEqual(result, "2023-05-20T01:02:03");
    });

    test("should ignore subsecond precision", () => {
      const result = normalizeDiskDate("2023:05:20 14:30:00.123");

      // Verify subseconds are ignored (matched up to seconds)
      strictEqual(result, "2023-05-20T14:30:00");
    });
  });
});

describe("parsePhotoTakenTime", () => {
  test("should format timestamp 1719935787 correctly", () => {
    const result = parsePhotoTakenTime("1719935787");

    // Verify EXIF format is correct
    strictEqual(result.exif, "2024:07:02 15:56:27+00:00");

    // Verify ISO format is correct
    strictEqual(result.iso, "2024-07-02T15:56:27");
  });

  test("should format timestamp 1710899464 correctly", () => {
    const result = parsePhotoTakenTime("1710899464");

    // Verify EXIF format is correct
    strictEqual(result.exif, "2024:03:20 01:51:04+00:00");

    // Verify ISO format is correct
    strictEqual(result.iso, "2024-03-20T01:51:04");
  });

  test("should format timestamp 1710994697 correctly", () => {
    const result = parsePhotoTakenTime("1710994697");

    // Verify EXIF format is correct
    strictEqual(result.exif, "2024:03:21 04:18:17+00:00");

    // Verify ISO format is correct
    strictEqual(result.iso, "2024-03-21T04:18:17");
  });

  test("should format timestamp 1711192947 correctly", () => {
    const result = parsePhotoTakenTime("1711192947");

    // Verify EXIF format is correct
    strictEqual(result.exif, "2024:03:23 11:22:27+00:00");

    // Verify ISO format is correct
    strictEqual(result.iso, "2024-03-23T11:22:27");
  });

  test("should format timestamp 1711016650 correctly", () => {
    const result = parsePhotoTakenTime("1711016650");

    // Verify EXIF format is correct
    strictEqual(result.exif, "2024:03:21 10:24:10+00:00");

    // Verify ISO format is correct
    strictEqual(result.iso, "2024-03-21T10:24:10");
  });

  test("should pad single digit months and days", () => {
    const result = parsePhotoTakenTime("1704675601");

    // Verify single-digit month (01) and day (08) are zero-padded in EXIF
    strictEqual(result.exif, "2024:01:08 01:00:01+00:00");

    // Verify single-digit month and day are zero-padded in ISO
    strictEqual(result.iso, "2024-01-08T01:00:01");
  });

  test("should handle midnight timestamp", () => {
    const result = parsePhotoTakenTime("1704067200");

    // Verify midnight is formatted with 00:00:00 in EXIF
    strictEqual(result.exif, "2024:01:01 00:00:00+00:00");

    // Verify midnight is formatted correctly in ISO
    strictEqual(result.iso, "2024-01-01T00:00:00");
  });

  test("should handle end of day timestamp", () => {
    const result = parsePhotoTakenTime("1704153599");

    // Verify end of day is formatted with 23:59:59 in EXIF
    strictEqual(result.exif, "2024:01:01 23:59:59+00:00");

    // Verify end of day is formatted correctly in ISO
    strictEqual(result.iso, "2024-01-01T23:59:59");
  });

  test("should handle epoch zero timestamp", () => {
    const result = parsePhotoTakenTime("0");

    // Verify Unix epoch (timestamp 0) is handled correctly in EXIF
    strictEqual(result.exif, "1970:01:01 00:00:00+00:00");

    // Verify Unix epoch is handled correctly in ISO
    strictEqual(result.iso, "1970-01-01T00:00:00");
  });

  test("should handle very old timestamp from 1990", () => {
    const result = parsePhotoTakenTime("631152000");

    // Verify old timestamps are handled correctly in EXIF
    strictEqual(result.exif, "1990:01:01 00:00:00+00:00");

    // Verify old timestamps are handled correctly in ISO
    strictEqual(result.iso, "1990-01-01T00:00:00");
  });

  test("should throw error when timestamp is not a valid number", () => {
    // Verify invalid timestamp string throws descriptive error
    throws(
      () => {
        parsePhotoTakenTime("invalid");
      },
      {
        name: "Error",
        message: "Failed to parse photoTakenTime timestamp: invalid",
      }
    );
  });

  test("should throw error when timestamp is empty string", () => {
    // Verify empty string throws error with NaN result
    throws(
      () => {
        parsePhotoTakenTime("");
      },
      {
        name: "Error",
        message: "Failed to parse photoTakenTime timestamp: ",
      }
    );
  });

  test("should accept numeric timestamp", () => {
    const result = parsePhotoTakenTime(1704067200);

    // Verify function accepts numbers in addition to strings for EXIF
    strictEqual(result.exif, "2024:01:01 00:00:00+00:00");

    // Verify function accepts numbers in addition to strings for ISO
    strictEqual(result.iso, "2024-01-01T00:00:00");
  });
});
