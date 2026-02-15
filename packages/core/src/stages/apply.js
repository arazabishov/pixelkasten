import { mkdir, copyFile } from "fs/promises";
import { join, dirname, basename } from "path";
import { writeMetadata } from "../core/exiftool.js";
import { canKeep } from "../core/manifest.js";

/**
 * Apply stage: copies files to destination and embeds metadata.
 *
 * For each file that is not marked for deletion:
 * 1. Copy to target path (from rename stage, or original filename if skipped)
 * 2. Embed metadata tags into the copy (if any tags to write)
 *
 * The source directory is never modified.
 *
 * @param {Array} manifest - The manifest array from previous stages
 * @param {Object} options - Options object
 * @param {string} options.destination - Target root directory
 */
export async function apply(manifest, options = {}) {
  const { logger, progress } = options;

  // Only process keepers - deletions and errors are handled by exclusion.
  // If dedupe was skipped, status is undefined, so !== 'delete' is true.
  const keepers = manifest.filter(canKeep);

  if (keepers.length === 0) {
    return;
  }

  const bar = progress?.();
  bar?.start(keepers.length, 0);

  for (const entry of keepers) {
    try {
      // Resolve destination path: use rename targetPath or fall back to original filename
      const targetPath = entry.rename?.targetPath ?? basename(entry.mediaPath);
      const destPath = join(options.destination, targetPath);

      // Ensure directory exists
      await mkdir(dirname(destPath), { recursive: true });

      // Copy file to destination
      await copyFile(entry.mediaPath, destPath);

      if (entry.metadata?.writeTags?.length > 0) {
        await writeMetadata(destPath, entry.metadata.writeTags);
        entry.apply = {
          status: "embedded",
          targetPath: destPath,
        };
      } else {
        entry.apply = {
          status: "copied",
          targetPath: destPath,
        };
      }

      // Copy sidecar when embedding is skipped and a sidecar exists
      if (options.skipEmbed && entry.json?.path) {
        await copyFile(entry.json.path, destPath + ".json");
      }
    } catch (error) {
      logger?.error(error.message);
      entry.apply = {
        status: "error",
        reason: error.message,
      };
    }

    bar?.increment();
  }

  bar?.stop();
}
