import { test, describe } from "node:test";
import { strictEqual, throws } from "node:assert";
import { transformPhotoTakenTime } from "../../src/core/datetime.js";

describe("transformPhotoTakenTime", () => {
  test("should format timestamp 1719935787 as 2024:07:02 15:56:27+00:00", () => {
    const result = transformPhotoTakenTime("1719935787");

    // Verify timestamp is formatted in EXIF datetime format with UTC timezone
    strictEqual(result, "2024:07:02 15:56:27+00:00");
  });

  test("should format timestamp 1710899464 as 2024:03:20 01:51:04+00:00", () => {
    const result = transformPhotoTakenTime("1710899464");

    // Verify timestamp is formatted correctly
    strictEqual(result, "2024:03:20 01:51:04+00:00");
  });

  test("should format timestamp 1710994697 as 2024:03:21 04:18:17+00:00", () => {
    const result = transformPhotoTakenTime("1710994697");

    // Verify timestamp is formatted correctly
    strictEqual(result, "2024:03:21 04:18:17+00:00");
  });

  test("should format timestamp 1711192947 as 2024:03:23 11:22:27+00:00", () => {
    const result = transformPhotoTakenTime("1711192947");

    // Verify timestamp is formatted correctly
    strictEqual(result, "2024:03:23 11:22:27+00:00");
  });

  test("should format timestamp 1711016650 as 2024:03:21 10:24:10+00:00", () => {
    const result = transformPhotoTakenTime("1711016650");

    // Verify timestamp is formatted correctly
    strictEqual(result, "2024:03:21 10:24:10+00:00");
  });

  test("should pad single digit months and days", () => {
    const result = transformPhotoTakenTime("1704675601");

    // Verify single-digit month (01) and day (08) are zero-padded
    strictEqual(result, "2024:01:08 01:00:01+00:00");
  });

  test("should handle midnight timestamp", () => {
    const result = transformPhotoTakenTime("1704067200");

    // Verify midnight is formatted with 00:00:00
    strictEqual(result, "2024:01:01 00:00:00+00:00");
  });

  test("should handle end of day timestamp", () => {
    const result = transformPhotoTakenTime("1704153599");

    // Verify end of day is formatted with 23:59:59
    strictEqual(result, "2024:01:01 23:59:59+00:00");
  });

  test("should handle epoch zero timestamp", () => {
    const result = transformPhotoTakenTime("0");

    // Verify Unix epoch (timestamp 0) is handled correctly
    strictEqual(result, "1970:01:01 00:00:00+00:00");
  });

  test("should handle very old timestamp from 1990", () => {
    const result = transformPhotoTakenTime("631152000");

    // Verify old timestamps are handled correctly
    strictEqual(result, "1990:01:01 00:00:00+00:00");
  });

  test("should throw error when timestamp is not a valid number", () => {
    // Verify invalid timestamp string throws descriptive error
    throws(
      () => {
        transformPhotoTakenTime("invalid");
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
        transformPhotoTakenTime("");
      },
      {
        name: "Error",
        message: "Failed to parse photoTakenTime timestamp: ",
      }
    );
  });

  test("should accept numeric timestamp", () => {
    const result = transformPhotoTakenTime(1704067200);

    // Verify function accepts numbers in addition to strings
    strictEqual(result, "2024:01:01 00:00:00+00:00");
  });
});
