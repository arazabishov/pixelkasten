import { extname } from "path";
import { logger } from "../utils/logger.js";
import { parseIsoDate } from "../core/datetime.js";

const monthFormatter = new Intl.DateTimeFormat("en-US", {
  month: "long",
});
/**
 * Rename stage: computes target paths for media files based on their timestamps.
 *
 * Structure: yyyy/mm - Month/yyyymmddhhmm.ext
 * Collisions are handled with -1, -2, -3 suffixes.
 *
 * @param {Array} manifest - The manifest array from previous stages
 * @param {Object} options - Options object
 * @param {boolean} options.strict - If true, throw on files without dates
 */
export function rename(manifest, options = {}) {
  // Stage 1: filter keepers. Skip files marked for deletion.
  const keepers = manifest.filter((entry) => entry.dedupe?.action !== "delete");

  if (keepers.length === 0) {
    return;
  }

  // Track used paths for collision detection
  const usedPaths = new Map();

  // Stage 2: compute target paths for each entry
  for (const entry of keepers) {
    try {
      entry.rename = computeTargetPath(entry, usedPaths);
    } catch (error) {
      if (options.strict) {
        throw error;
      }

      logger.error(error.message);
      entry.rename = {
        status: "error",
      };
    }
  }
}

/**
 * Computes the target path for a single entry.
 *
 * @param {Object} entry - Manifest entry with metadata
 * @param {Map} usedPaths - Map tracking used paths for collision detection
 * @returns {Object} Rename result with status and targetPath
 */
function computeTargetPath(entry, usedPaths) {
  const dates = entry.metadata?.dates;

  // Validate that we have at least one date
  if (!dates || dates.length === 0) {
    throw new Error(`No timestamp available for ${entry.mediaPath}`);
  }

  // Try each date in order until one parses successfully
  const parsed = dates.map(parseIsoDate).find(Boolean);

  if (!parsed) {
    throw new Error(`No valid date format found for ${entry.mediaPath}`);
  }

  // Build path components
  const { year, month, day, hour, minute, second } = parsed;
  const monthName = monthFormatter.format(new Date(year, month - 1));
  const ext = extname(entry.mediaPath).toLowerCase();

  // Helper for zero-padding
  const pad2 = (num) => String(num).padStart(2, "0");

  // Format: yyyy/mm - Month/yyyymmdd-hhmmss.ext
  const monthFolder = `${year}/${pad2(month)} - ${monthName}`;
  const timestamp = `${year}${pad2(month)}${pad2(day)}-${pad2(hour)}${pad2(minute)}${pad2(second)}`;

  // Build base path and handle collisions
  const basePath = `${monthFolder}/${timestamp}${ext}`;
  const targetPath = resolveCollision(basePath, usedPaths);

  // Track this path as used
  usedPaths.set(targetPath, true);

  return {
    status: "processed",
    targetPath,
  };
}

/**
 * Resolves path collisions by appending -1, -2, etc.
 *
 * @param {string} basePath - Original target path
 * @param {Map} usedPaths - Map of already used paths
 * @returns {string} Unique path (original or with suffix)
 */
function resolveCollision(basePath, usedPaths) {
  if (!usedPaths.has(basePath)) {
    return basePath;
  }

  // Extract path parts for suffix insertion
  const ext = extname(basePath);
  const pathWithoutExt = basePath.slice(0, -ext.length);

  let counter = 1;
  let candidatePath;

  do {
    candidatePath = `${pathWithoutExt}-${counter}${ext}`;
    counter++;
  } while (usedPaths.has(candidatePath));

  return candidatePath;
}
