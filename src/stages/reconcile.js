import { logger } from "../logger.js";
import { readMetadata } from "../core/exiftool.js";
import { supportedExtensions, handlers } from "../handlers/index.js";
import { readFile } from "fs/promises";
import { extname } from "path";

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

  // Stage 3: sliding window loop to process files in chunks to prevent OOM.
  for (let offset = 0; offset < keepers.length; offset += 512) {
    // Stage 3.1: slice the batch
    const batch = keepers.slice(offset, offset + 512);

    console.log("... batch", offset, batch.length);

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
  }

  console.log("Here");
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
