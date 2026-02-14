import { createHash } from "crypto";
import { createReadStream } from "fs";
import { logger } from "../utils/logger.js";
import { progressBar } from "../utils/progress.js";

/**
 * Calculates SHA-256 hashes for all media files in the manifest.
 *
 * This is the first phase of deduplication. It computes a cryptographic hash
 * for each media file to enable content-based duplicate detection. Files with
 * identical hashes are considered duplicates regardless of filename or location.
 *
 * @param {Array<{
 *   mediaPath: string,
 *   json: { path: string, confidence: number } | null,
 *   source: { type: 'album', name: string } | { type: 'loose' }
 * }>} manifest - The manifest of media files to hash.
 * @returns {Promise<void>} Modifies the manifest in-place by adding a `dedupe` property
 *   to each entry containing the calculated hash and initial action state.
 */
export async function dedupeHash(manifest) {
  const bar = progressBar("⧗ Calculating hashes |{bar}| {percentage}% | {value}/{total} entries");
  bar.start(manifest.length, 0);

  for (const [index, entry] of manifest.entries()) {
    try {
      const sha256 = await calculateHash(entry.mediaPath);

      manifest[index] = {
        ...entry,
        dedupe: {
          hash: sha256,
          status: "pending",
        },
      };
    } catch (error) {
      logger.error(error.message);
      manifest[index] = {
        ...entry,
        dedupe: {
          hash: null,
          status: "error",
          reason: error.message,
        },
      };
    }

    bar.increment();
  }

  bar.stop();
}

function calculateHash(filePath) {
  return new Promise((resolve, reject) => {
    const hash = createHash("sha256");
    const stream = createReadStream(filePath);

    stream.on("error", (err) => {
      reject(err);
    });

    stream.on("data", (chunk) => {
      hash.update(chunk);
    });

    stream.on("end", () => {
      resolve(hash.digest("hex"));
    });
  });
}

/**
 * Resolves deduplication actions for files based on content hashes and user preferences.
 *
 * This is the second phase of deduplication. It analyzes files with identical hashes
 * and determines which should be kept or deleted based on the following rules:
 *  - Unique files (no duplicates) are always kept.
 *  - When duplicates have mixed source types (album and loose), files matching the
 *    preferred type are kept and others are deleted.
 *  - When duplicates are all the same type (all album or all loose), all are kept
 *    to preserve files across different albums or locations.
 *
 * @param {Array<{
 *   mediaPath: string,
 *   json: { path: string, confidence: number } | null,
 *   source: { type: 'album', name: string } | { type: 'loose' },
 *   dedupe: { hash: string, status: 'pending' }
 * }>} manifest - The manifest with calculated hashes from dedupeHash.
 * @param {{ prefer: 'album' | 'loose' }} options - Configuration specifying which source
 *   type to prefer when resolving mixed-type duplicates.
 * @returns {Promise<void>} Modifies the manifest in-place by setting each entry's
 *   `dedupe.status` to either 'keep' or 'delete'.
 * @throws {Error} If any entry ends up with an invalid status after resolution.
 */
export async function dedupeResolve(manifest, options) {
  const bar = progressBar("⧗ Resolving duplicates |{bar}| {percentage}% | {value}/{total} entries");

  // Group entries by hash, skipping entries that failed hashing
  const hashes = new Map();
  for (const entry of manifest) {
    const hash = entry.dedupe.hash;
    if (hash) {
      hashes.set(hash, hashes.get(hash) ?? []);
      hashes.get(hash).push(entry);
    }
  }

  bar.start(hashes.size, 0);

  // Resolve duplicates
  const hashGroups = Array.from(hashes.values());
  for (const duplicates of hashGroups) {
    if (duplicates.length === 1) {
      // Unique file - always keep
      duplicates[0].dedupe.status = "keep";
    } else {
      // Multiple files with same hash - check if mixed types
      const hasPreferred = duplicates.some((e) => e.source.type === options.prefer);
      const hasOther = duplicates.some((e) => e.source.type !== options.prefer);

      if (hasPreferred && hasOther) {
        // Mixed types - keep preferred, delete other
        for (const entry of duplicates) {
          entry.dedupe.status = entry.source.type === options.prefer ? "keep" : "delete";
        }
      } else {
        // Same type - keep all
        for (const entry of duplicates) {
          entry.dedupe.status = "keep";
        }
      }
    }

    bar.increment();
  }

  bar.stop();

  checkInvariants(manifest);
}

function checkInvariants(manifest) {
  for (const entry of manifest) {
    const status = entry.dedupe.status;

    if (status !== "keep" && status !== "delete" && status !== "error") {
      throw new Error(
        `Invalid dedupe status "${status}" for file: ${entry.mediaPath}. Expected "keep", "delete", or "error".`
      );
    }
  }
}
