import { logger, canShowProgress } from "../logger.js";
import { readMetadata } from "../core/exiftool.js";
import { supportedExtensions, handlers } from "../handlers/index.js";
import { readFile } from "fs/promises";
import { extname } from "path";
import cliProgress from "cli-progress";

export async function reconcile(manifest, options) {
  // Stage 1: filter keepers. We use optional chaining (?.) to be safe if dedupe object is missing.
  // If dedupe was skipped, action is 'pending' or undefined, so !== 'delete' is true.
  const keepers = manifest.filter((entry) => entry.dedupe?.action !== "delete");

  // It is unlikely to happen, but theoretically possible.
  if (keepers.length === 0) {
    return;
  }

  // Stage 2: collect a Set of all tags required by all registered handlers.
  const extensions = [...supportedExtensions].flatMap((ext) => ["-ext", ext]);
  const readTags = [
    ...new Set(
      Object.values(handlers).flatMap((h) => {
        return h.readTags.map((t) => `-${t}`);
      })
    ),
  ];
  const args = [...readTags, ...extensions];

  // Calculate total number of batches needed (round up for partial batches)
  const batchSize = 512;
  const batches = Math.ceil(keepers.length / batchSize);

  const progressBar = canShowProgress()
    ? new cliProgress.SingleBar(
        {
          format: "⧗ Reconciling metadata |{bar}| {percentage}% | {value}/{total} batches",
          hideCursor: true,
        },
        cliProgress.Presets.shades_classic
      )
    : null;

  if (canShowProgress()) {
    progressBar.start(batches, 0);
  }

  // Stage 3: sliding window loop to process files in chunks to prevent OOM.
  for (let offset = 0; offset < keepers.length; offset += batchSize) {
    // Stage 3.1: slice the batch (up to batchSize items)
    const batch = keepers.slice(offset, offset + batchSize);

    // Stage 3.2: prepare paths for exiftool.
    const batchPaths = batch.map((entry) => entry.mediaPath);

    // Stage 3.3: contains a Map<Path, ExifObject>.
    const batchExifMap = await readMetadata(batchPaths, args);

    // Stage 3.4: process the batch in parallel using promises.
    const tasks = batch.map(async (entry) => {
      // If exiftool has not reported on a file, we should not try to continue processing it.
      if (!batchExifMap.has(entry.mediaPath)) {
        const error = `ExifTool failed to report on file: ${file.mediaPath}. Skipping to prevent overwrite.`;

        if (options.strict) {
          throw new Error(error);
        }

        logger.error(error);
        return;
      }

      const extension = extname(entry.mediaPath).toLowerCase();
      const handler = handlers[extension];

      // Look up tags returned by exiftool.
      const rawDiskTags = batchExifMap.get(entry.mediaPath);

      // Normalize raw, file type specific tags to a common shape.
      const diskData = handler.parse(rawDiskTags);

      // Retrieve and parse sidecar data.
      const sidecarData = await fetchSidecarData(entry.jsonPath);

      entry.metadata = resolve(sidecarData, diskData);
    });

    await Promise.all(tasks);

    if (canShowProgress()) {
      // Calculate current batch number: divide offset by batch size and add 1 for 1-based indexing
      progressBar.update(Math.floor(offset / batchSize) + 1);
    }
  }

  if (canShowProgress()) {
    progressBar.stop();
  }
}

async function fetchSidecarData(jsonPath) {
  if (!jsonPath) {
    return null;
  }

  try {
    return JSON.parse(await readFile(jsonPath, "utf8"));
  } catch (error) {
    throw new Error(`Failed to read sidecar file at ${jsonPath}: ${error.message}`);
  }
}

function resolve(sidecarData, diskData) {
  return {
    timestamp: "hello, world",
  };
}
