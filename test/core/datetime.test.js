import { test, describe } from "node:test";
import { strictEqual, throws } from "node:assert";
import { parsePhotoTakenTime } from "../../src/core/datetime.js";

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
