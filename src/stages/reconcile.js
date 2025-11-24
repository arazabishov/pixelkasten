import { logger } from "../utils/logger.js";
import { progressBar } from "../utils/progress.js";
import { readMetadata } from "../core/exiftool.js";
import { readSidecar } from "../core/sidecar.js";
import { supportedExtensions, handlers } from "../handlers/index.js";
import { extname } from "path";
import { transformPhotoTakenTime } from "../core/datetime.js";

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
      entry.metadata = {
        status: "pending",
        writeTags: [],
        dates: [],
      };

      // If exiftool has not reported on a file, we should not try to continue processing it.
      if (!batchExifMap.has(entry.mediaPath)) {
        const message = `ExifTool did not report on ${entry.mediaPath}, skipping.`;
        if (options.strict) {
          throw new Error(message);
        }

        logger.error(message);
        entry.metadata.status = "error";

        return;
      }

      const extension = extname(entry.mediaPath).toLowerCase();
      const handler = handlers[extension];

      if (!handler) {
        const message = `Encountered file of unsupported type ${extension}, skipping.`;
        if (options.strict) {
          throw new Error(message);
        }

        logger.error(message);
        file.metadata.status = "unsupported";

        return;
      }

      // Retrieve and parse sidecar data.
      const sidecarData = await readSidecar(entry.jsonPath);

      // If there is no sidecar data, there is no point to continue.
      if (!sidecarData) {
        file.metadata.status = "noop";

        return;
      }

      // Look up tags returned by exiftool.
      const rawDiskTags = batchExifMap.get(entry.mediaPath);

      // Normalize raw, file type specific tags to a common shape.
      const diskData = handler.parse(rawDiskTags);

      // If there is no primary timestamp on disk, we can embed the value from sidecar.
      if (!diskData.timestamp) {
        const timestamp = transformPhotoTakenTime(sidecarData.timestamp);
        entry.metadata.writeTags = [...entry.metadata.writeTags, ...handler.timestamp(timestamp)];

        // TODO: who will be processing dates into a proper shape? I think it should be done at the handler stage ...
        // TODO: remember that you will need to unshift / insert the primary disk timestamp, because it is not a part of the dates array!
        entry.metadata.dates = [timestamp, ...entry.metadata.dates];
      }

      if (!diskData.geo) {
        entry.metadata.writeTags = [...entry.metadata.writeTags, ...handler.geo(sidecarData.geo)];
      }

      entry.metadata.status = entry.metadata.writeTags.length === 0 ? "noop" : "processed";
    });

    await Promise.all(tasks);

    // Convert offset to 1-based batch number.
    // TODO: use .increment() instead of weird .update statements!
    bar.update(Math.floor(offset / batchSize) + 1);
  }

  bar.stop();
}
