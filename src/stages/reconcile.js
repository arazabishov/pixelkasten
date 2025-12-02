import { logger } from "../utils/logger.js";
import { progressBar } from "../utils/progress.js";
import { readMetadata } from "../core/exiftool.js";
import { readSidecar } from "../core/sidecar.js";
import { handlers } from "../handlers/index.js";
import { extname } from "path";
import { parsePhotoTakenTime } from "../core/datetime.js";

export async function reconcile(manifest, options) {
  // Stage 1: filter keepers. We use optional chaining (?.) to be safe if dedupe object is missing.
  // If dedupe was skipped, action is 'pending' or undefined, so !== 'delete' is true.
  const keepers = manifest.filter((entry) => entry.dedupe?.action !== "delete");

  // It is unlikely to happen, but theoretically possible.
  if (keepers.length === 0) {
    return;
  }

  // Stage 2: collect a Set of all tags required by all registered handlers.
  const readTags = [...new Set(Object.values(handlers).flatMap((h) => h.readTags))];

  // Calculate total number of batches needed (round up for partial batches)
  const batchSize = 512;
  const batches = Math.ceil(keepers.length / batchSize);

  const bar = progressBar("⧗ Reconciling metadata |{bar}| {percentage}% | {value}/{total} batches");

  bar.start(batches, 0);

  // Stage 3: sliding window loop to process files in chunks to prevent OOM.
  for (let offset = 0; offset < keepers.length; offset += batchSize) {
    // Stage 3.1: slice the batch (up to batchSize items)
    const batch = keepers.slice(offset, offset + batchSize);

    // Stage 3.2: prepare paths for exiftool.
    const batchPaths = batch.map((entry) => entry.mediaPath);

    // Stage 3.3: contains a Map<Path, ExifObject>.
    const batchExifMap = await readMetadata(batchPaths, readTags);

    // Stage 3.4: process the batch in parallel using promises.
    const tasks = batch.map(async (entry) => {
      // Look up tags returned by exiftool.
      const rawDiskTags = batchExifMap.get(entry.mediaPath);

      try {
        entry.metadata = await resolve(entry.mediaPath, entry.json?.path, rawDiskTags);
      } catch (error) {
        if (options.strict) {
          throw error;
        }

        logger.error(error.message);
        entry.metadata = {
          status: "error",
          writeTags: [],
          dates: [],
        };
      }
    });

    await Promise.all(tasks);

    bar.increment();
  }

  bar.stop();
}

async function resolve(mediaPath, jsonPath, rawDiskTags) {
  // If exiftool has not reported on a file, then something went wrong.
  if (!rawDiskTags) {
    throw new Error(`ExifTool did not report on ${mediaPath}, skipping.`);
  }

  const extension = extname(mediaPath).toLowerCase();
  const handler = handlers[extension];

  // If there is no handler for a file type, pixelkasten will not be able to process it.
  if (!handler) {
    throw new Error(`Encountered file of unsupported type ${extension}, skipping.`);
  }

  // Normalize raw, file type specific tags to a common shape.
  const diskData = handler.parse(rawDiskTags);

  // The starting point for the metadata object. If no writes happen, the status is "noop".
  const metadata = { status: "noop", writeTags: [], dates: [...diskData.dates] };

  // Retrieve and parse sidecar data.
  const sidecarData = await readSidecar(jsonPath);

  // If there is no sidecar data, there is nothing to resolve.
  if (!sidecarData) {
    return metadata;
  }

  // If there is no primary timestamp on disk, we can embed the value from sidecar.
  if (!diskData.timestamp && sidecarData.timestamp) {
    const { iso, exif } = parsePhotoTakenTime(sidecarData.timestamp);

    // Ensure that new timestamp gets written back to the file.
    metadata.writeTags.push(...handler.timestamp(exif));

    // Make sure that timestamp is stored as the primary date
    metadata.dates.unshift(iso);
  }

  if (!diskData.geo && sidecarData.geo) {
    metadata.writeTags.push(...handler.geo(sidecarData.geo));
  }

  if (metadata.writeTags.length > 0) {
    metadata.status = "processed";
  }

  return metadata;
}
