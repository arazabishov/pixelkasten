import { test, describe } from "node:test";
import { strictEqual, throws } from "node:assert";
import { transformPhotoTakenTime } from "../src/transform.js";

describe("transformPhotoTakenTime", () => {
  test("should format timestamp 1719935787 as 2024:07:02 15:56:27+00:00", () => {
    const photoTakenTime = {
      timestamp: "1719935787",
      formatted: "Jul 2, 2024, 3:56:27 PM UTC",
    };

    const result = transformPhotoTakenTime(photoTakenTime);

    strictEqual(result, "2024:07:02 15:56:27+00:00");
  });

  test("should format timestamp 1710899464 as 2024:03:20 01:51:04+00:00", () => {
    const photoTakenTime = {
      timestamp: "1710899464",
      formatted: "Mar 20, 2024, 1:51:04 AM UTC",
    };

    const result = transformPhotoTakenTime(photoTakenTime);

    strictEqual(result, "2024:03:20 01:51:04+00:00");
  });

  test("should format timestamp 1710994697 as 2024:03:21 04:18:17+00:00", () => {
    const photoTakenTime = {
      timestamp: "1710994697",
      formatted: "Mar 21, 2024, 4:18:17 AM UTC",
    };

    const result = transformPhotoTakenTime(photoTakenTime);

    strictEqual(result, "2024:03:21 04:18:17+00:00");
  });

  test("should format timestamp 1711192947 as 2024:03:23 11:22:27+00:00", () => {
    const photoTakenTime = {
      timestamp: "1711192947",
      formatted: "Mar 23, 2024, 11:22:27 AM UTC",
    };

    const result = transformPhotoTakenTime(photoTakenTime);

    strictEqual(result, "2024:03:23 11:22:27+00:00");
  });

  test("should format timestamp 1711016650 as 2024:03:21 10:24:10+00:00", () => {
    const photoTakenTime = {
      timestamp: "1711016650",
      formatted: "Mar 21, 2024, 10:24:10 AM UTC",
    };

    const result = transformPhotoTakenTime(photoTakenTime);

    strictEqual(result, "2024:03:21 10:24:10+00:00");
  });

  test("should pad single digit months and days", () => {
    const photoTakenTime = {
      timestamp: "1704675601",
      formatted: "Jan 8, 2024, 1:00:01 AM UTC",
    };

    const result = transformPhotoTakenTime(photoTakenTime);

    strictEqual(result, "2024:01:08 01:00:01+00:00");
  });

  test("should handle midnight timestamp", () => {
    const photoTakenTime = {
      timestamp: "1704067200",
      formatted: "Jan 1, 2024, 12:00:00 AM UTC",
    };

    const result = transformPhotoTakenTime(photoTakenTime);

    strictEqual(result, "2024:01:01 00:00:00+00:00");
  });

  test("should handle end of day timestamp", () => {
    const photoTakenTime = {
      timestamp: "1704153599",
      formatted: "Jan 1, 2024, 11:59:59 PM UTC",
    };

    const result = transformPhotoTakenTime(photoTakenTime);

    strictEqual(result, "2024:01:01 23:59:59+00:00");
  });

  test("should throw error when photoTakenTime is null", () => {
    throws(() => transformPhotoTakenTime(null), {
      name: "Error",
      message: "Invalid photoTakenTime: missing timestamp property",
    });
  });

  test("should throw error when photoTakenTime is undefined", () => {
    throws(() => transformPhotoTakenTime(undefined), {
      name: "Error",
      message: "Invalid photoTakenTime: missing timestamp property",
    });
  });

  test("should throw error when timestamp property is missing", () => {
    throws(() => transformPhotoTakenTime({ formatted: "Jan 1, 2024, 12:00:00 AM UTC" }), {
      name: "Error",
      message: "Invalid photoTakenTime: missing timestamp property",
    });
  });

  test("should throw error when timestamp is not a valid number", () => {
    throws(() => transformPhotoTakenTime({ timestamp: "invalid" }), {
      name: "Error",
      message: "Failed to parse photoTakenTime timestamp: invalid",
    });
  });

  test("should throw error when timestamp is empty string", () => {
    throws(() => transformPhotoTakenTime({ timestamp: "" }), {
      name: "Error",
      message: "Invalid photoTakenTime: missing timestamp property",
    });
  });

  test("should handle epoch zero timestamp", () => {
    const photoTakenTime = {
      timestamp: "0",
      formatted: "Jan 1, 1970, 12:00:00 AM UTC",
    };

    const result = transformPhotoTakenTime(photoTakenTime);

    strictEqual(result, "1970:01:01 00:00:00+00:00");
  });

  test("should handle very old timestamp from 1990", () => {
    const photoTakenTime = {
      timestamp: "631152000", // Jan 1, 1990, 12:00:00 AM UTC
      formatted: "Jan 1, 1990, 12:00:00 AM UTC",
    };

    const result = transformPhotoTakenTime(photoTakenTime);

    strictEqual(result, "1990:01:01 00:00:00+00:00");
  });
});
