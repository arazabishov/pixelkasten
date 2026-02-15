import { test, describe, mock } from "node:test";
import { strictEqual, ok } from "node:assert";
import { readdir, readFile, writeFile } from "fs/promises";
import { join } from "path";
import { checkExiftool, readMetadata } from "../../src/core/exiftool.js";
import { createTempDir, buildTakeout } from "./fixtures/fixtures.js";

mock.module("../../src/utils/logger.js", {
  namedExports: {
    logger: {
      info: mock.fn(),
      warn: mock.fn(),
      error: mock.fn(),
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

const { runPipeline } = await import("../../src/pipeline.js");

await checkExiftool();

describe("pipeline integration", () => {
  // EXIF tags used to verify pipeline writes.
  const verifyTags = [
    "EXIF:DateTimeOriginal",
    "Composite:GPSLatitude",
    "Composite:GPSLongitude",
    "Composite:GPSAltitude",
  ];

  // Asserts GPS coordinate equality within 0.01 deg tolerance (EXIF DMS rounding).
  const assertApproxEqual = (actual, expected, label) => {
    ok(Math.abs(actual - expected) < 0.01, `${label}: expected ~${expected}, got ${actual}`);
  };

  test("should embed, preserve, and partially fill metadata", async (context) => {
    const source = await createTempDir(context);
    const dest = await createTempDir(context);

    await buildTakeout(source, {
      "Photos from 2024": [
        {
          // No EXIF -- both timestamp and GPS should be written.
          media: "no-metadata.jpg",
          name: "IMG_001.jpg",
          sidecar: {
            timestamp: "1711016650",
            geo: { latitude: 51.5007, longitude: -0.1246, altitude: 11 },
          },
        },
        {
          // Has timestamp + GPS -- pipeline should not overwrite.
          media: "with-datetime-and-gps.jpg",
          name: "IMG_002.jpg",
          sidecar: {
            timestamp: "1719935787",
            geo: { latitude: 48.8584, longitude: 2.2945, altitude: 35 },
          },
        },
        {
          // Has timestamp but no GPS -- only GPS should be written.
          media: "with-datetime-no-gps.jpg",
          name: "IMG_003.jpg",
          sidecar: {
            timestamp: "1710899464",
            geo: { latitude: 35.6762, longitude: 139.6503, altitude: 40 },
          },
        },
      ],
    });

    await runPipeline({
      source,
      destination: dest,
      prefer: "album",
      fuzzy: true,
    });

    const noExifFile = join(dest, "2024/03 - March/20240321-102410.jpg");
    const fullExifFile = join(dest, "2024/07 - July/20240702-155627.jpg");
    const partialExifFile = join(dest, "2024/03 - March/20240320-015104.jpg");
    const diskMetadata = await readMetadata([noExifFile, fullExifFile, partialExifFile], verifyTags);

    // No-EXIF file: was empty, should now have timestamp + GPS from sidecar
    const noExifMeta = diskMetadata.get(noExifFile);
    ok(noExifMeta, "No-EXIF file should exist in output");

    // Verify timestamp was written from sidecar
    ok(
      noExifMeta["EXIF:DateTimeOriginal"]?.includes("2024:03:21"),
      `No-EXIF DateTimeOriginal should contain 2024:03:21, got: ${noExifMeta["EXIF:DateTimeOriginal"]}`
    );

    // Verify GPS was written from sidecar
    assertApproxEqual(noExifMeta["Composite:GPSLatitude"], 51.5007, "No-EXIF latitude");
    assertApproxEqual(noExifMeta["Composite:GPSLongitude"], -0.1246, "No-EXIF longitude");

    // Full-EXIF file: already had metadata, should be unchanged
    const fullExifMeta = diskMetadata.get(fullExifFile);
    ok(fullExifMeta, "Full-EXIF file should exist in output");

    // Verify original timestamp was preserved
    ok(
      fullExifMeta["EXIF:DateTimeOriginal"]?.includes("2024:07:02"),
      `Full-EXIF DateTimeOriginal should contain 2024:07:02, got: ${fullExifMeta["EXIF:DateTimeOriginal"]}`
    );

    // Verify original GPS was preserved
    assertApproxEqual(fullExifMeta["Composite:GPSLatitude"], 48.8584, "Full-EXIF latitude");
    assertApproxEqual(fullExifMeta["Composite:GPSLongitude"], 2.2945, "Full-EXIF longitude");

    // Partial-EXIF file: had timestamp but no GPS, should gain GPS from sidecar
    const partialExifMeta = diskMetadata.get(partialExifFile);
    ok(partialExifMeta, "Partial-EXIF file should exist in output");

    // Verify original timestamp was preserved
    ok(
      partialExifMeta["EXIF:DateTimeOriginal"]?.includes("2024:03:20"),
      `Partial-EXIF DateTimeOriginal should contain 2024:03:20, got: ${partialExifMeta["EXIF:DateTimeOriginal"]}`
    );

    // Verify GPS was written from sidecar
    assertApproxEqual(partialExifMeta["Composite:GPSLatitude"], 35.6762, "Partial-EXIF latitude");
    assertApproxEqual(partialExifMeta["Composite:GPSLongitude"], 139.6503, "Partial-EXIF longitude");

    // Verify CSV report reflects per-file statuses
    const reportContent = await readFile(join(dest, "report.csv"), "utf8");
    const reportRows = reportContent.split("\n");

    // Verify no-EXIF file was embedded (metadata written from sidecar)
    const noExifRow = reportRows.find((r) => r.includes("IMG_001.jpg"));
    ok(noExifRow.includes("embedded"), "No-EXIF file should have 'embedded' status in report");

    // Verify full-EXIF file was only copied (already had metadata)
    const fullExifRow = reportRows.find((r) => r.includes("IMG_002.jpg"));
    ok(fullExifRow.includes("copied"), "Full-EXIF file should have 'copied' status in report");

    // Verify partial-EXIF file was embedded (GPS written from sidecar)
    const partialExifRow = reportRows.find((r) => r.includes("IMG_003.jpg"));
    ok(partialExifRow.includes("embedded"), "Partial-EXIF file should have 'embedded' status in report");
  });

  test("should deduplicate album copies over loose copies", async (context) => {
    const source = await createTempDir(context);
    const dest = await createTempDir(context);

    await buildTakeout(source, {
      Vacation: [
        {
          album: true,
        },
        {
          media: "no-metadata.jpg",
          name: "IMG_001.jpg",
          sidecar: {
            timestamp: "1711016650",
            geo: { latitude: 51.5007, longitude: -0.1246, altitude: 11 },
          },
        },
      ],
      "Photos from 2024": [
        {
          // Byte-identical copy -- same fixture, same hash.
          media: "no-metadata.jpg",
          name: "IMG_001.jpg",
          sidecar: {
            timestamp: "1711016650",
            geo: { latitude: 51.5007, longitude: -0.1246, altitude: 11 },
          },
        },
      ],
    });

    await runPipeline({
      source,
      destination: dest,
      prefer: "album",
      fuzzy: true,
    });

    const albumFile = join(dest, "2024/03 - March/20240321 - Vacation/20240321-102410.jpg");
    const diskMetadata = await readMetadata([albumFile], verifyTags);
    const albumFileMeta = diskMetadata.get(albumFile);

    // Verify the album copy exists with embedded metadata
    ok(albumFileMeta, "Album copy should exist in output");
    ok(
      albumFileMeta["EXIF:DateTimeOriginal"]?.includes("2024:03:21"),
      "Album copy should have timestamp embedded"
    );
    assertApproxEqual(albumFileMeta["Composite:GPSLatitude"], 51.5007, "Album copy latitude");

    // Verify the loose copy was removed by dedup (no JPEGs directly in month folder)
    const monthFolder = join(dest, "2024/03 - March");
    const monthFolderEntries = await readdir(monthFolder);
    const looseJpegs = monthFolderEntries.filter((f) => f.endsWith(".jpg"));
    strictEqual(looseJpegs.length, 0, "No loose JPEGs should exist directly in the month folder");

    // Verify report: one embedded (album winner), one deleted (loose duplicate)
    const reportContent = await readFile(join(dest, "report.csv"), "utf8");
    const reportRows = reportContent.split("\n");

    const embeddedRows = reportRows.filter((r) => r.includes("embedded"));
    const deletedRows = reportRows.filter((r) => r.includes("deleted"));

    strictEqual(embeddedRows.length, 1, "Exactly one file should be embedded");
    strictEqual(deletedRows.length, 1, "Exactly one file should be deleted");
  });

  test("should copy sidecar alongside media when skip-embed is set", async (context) => {
    const source = await createTempDir(context);
    const dest = await createTempDir(context);

    await buildTakeout(source, {
      "Photos from 2024": [
        {
          media: "no-metadata.jpg",
          name: "IMG_001.jpg",
          sidecar: {
            timestamp: "1711016650",
            geo: { latitude: 51.5007, longitude: -0.1246, altitude: 11 },
          },
        },
      ],
    });

    await runPipeline({
      source,
      destination: dest,
      prefer: "album",
      fuzzy: true,
      skipEmbed: true,
    });

    const copiedFile = join(dest, "2024/03 - March/20240321-102410.jpg");
    const diskMetadata = await readMetadata([copiedFile], verifyTags);
    const copiedFileMeta = diskMetadata.get(copiedFile);

    // Verify the file was copied
    ok(copiedFileMeta, "Copied file should exist");

    // Verify no timestamp was written (skipEmbed prevents metadata embedding)
    strictEqual(
      copiedFileMeta["EXIF:DateTimeOriginal"],
      undefined,
      "DateTimeOriginal should not be present when skipEmbed is set"
    );

    // Verify no GPS was written
    strictEqual(
      copiedFileMeta["Composite:GPSLatitude"],
      undefined,
      "GPSLatitude should not be present when skipEmbed is set"
    );

    // Verify the sidecar JSON was copied alongside the media file
    const copiedSidecarPath = join(dest, "2024/03 - March/20240321-102410.jpg.json");
    const copiedSidecar = JSON.parse(await readFile(copiedSidecarPath, "utf8"));
    strictEqual(
      copiedSidecar.photoTakenTime.timestamp,
      "1711016650",
      "Sidecar should be copied with correct content"
    );
  });

  test("should not write any files in dry-run mode", async (context) => {
    const source = await createTempDir(context);
    const dest = await createTempDir(context);

    await buildTakeout(source, {
      "Photos from 2024": [
        {
          media: "no-metadata.jpg",
          name: "IMG_001.jpg",
          sidecar: { timestamp: "1711016650" },
        },
      ],
    });

    await runPipeline({
      source,
      destination: dest,
      prefer: "album",
      fuzzy: true,
      dryRun: true,
    });

    // Verify destination is empty (dry run writes nothing)
    const destEntries = await readdir(dest);
    strictEqual(destEntries.length, 0, "Destination should be empty in dry-run mode");
  });

  test("should copy unsupported formats without embedding metadata", async (context) => {
    const source = await createTempDir(context);
    const dest = await createTempDir(context);

    await buildTakeout(source, {
      "Photos from 2024": [
        {
          media: "no-metadata.jpg",
          name: "IMG_001.jpg",
          sidecar: {
            timestamp: "1711016650",
            geo: { latitude: 51.5007, longitude: -0.1246, altitude: 11 },
          },
        },
      ],
    });

    // Add an unsupported .avi file alongside the JPEG.
    await writeFile(
      join(source, "Photos from 2024", "video.avi"),
      Buffer.from("dummy avi content for testing")
    );
    await writeFile(
      join(source, "Photos from 2024", "video.avi.supplemental-metadata.json"),
      JSON.stringify({
        title: "video.avi",
        description: "",
        photoTakenTime: { timestamp: "1711016650", formatted: "test" },
        geoData: {
          latitude: 0.0,
          longitude: 0.0,
          altitude: 0.0,
          latitudeSpan: 0.0,
          longitudeSpan: 0.0,
        },
      })
    );

    await runPipeline({
      source,
      destination: dest,
      prefer: "album",
      fuzzy: true,
    });

    // Verify the JPEG was renamed and embedded as usual
    const jpegFile = join(dest, "2024/03 - March/20240321-102410.jpg");
    const jpegMetadata = await readMetadata([jpegFile], verifyTags);
    ok(jpegMetadata.get(jpegFile), "JPEG should be in renamed output path");

    // Verify the .avi was copied with its original filename (unsupported formats skip rename)
    const aviFile = join(dest, "video.avi");
    const aviContent = await readFile(aviFile, "utf8");
    strictEqual(
      aviContent,
      "dummy avi content for testing",
      "AVI should be copied with original content"
    );

    // Verify report shows the .avi as "copied"
    const reportContent = await readFile(join(dest, "report.csv"), "utf8");
    const aviRow = reportContent.split("\n").find((row) => row.includes("video.avi"));

    ok(aviRow, "Report should mention the AVI file");
    ok(aviRow.includes("copied"), "AVI should have 'copied' status in report");
  });
});
