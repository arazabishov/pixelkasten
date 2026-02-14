import { extname } from "path";
import { parseIsoDate } from "../core/datetime.js";
import { canKeep } from "../core/manifest.js";
import { logger } from "../utils/logger.js";

const monthFormatter = new Intl.DateTimeFormat("en-US", {
  month: "long",
});

/**
 * Rename stage: resolves target paths for media files based on their timestamps.
 *
 * Structure: yyyy/mm - Month/yyyymmddhhmm.ext
 * Collisions are handled with -1, -2, -3 suffixes.
 *
 * @param {Array} manifest - The manifest array from previous stages
 */
export function rename(manifest) {
  // Stage 1: filter out deletions, errors, and unsupported formats.
  const candidates = manifest.filter(
    (entry) => canKeep(entry) && entry.metadata?.status !== "skipped"
  );

  if (candidates.length === 0) {
    return;
  }

  // Stage 2: resolve earliest dates for each album
  const albumDates = resolveAlbumDates(candidates);

  // Track used paths for collision detection
  const usedPaths = new Set();

  // Stage 3: resolve target paths for each entry
  for (const entry of candidates) {
    try {
      entry.rename = resolveTargetPath(entry, usedPaths, albumDates);
    } catch (error) {
      logger.error(error.message);
      entry.rename = {
        status: "error",
        reason: error.message,
      };
    }
  }
}

// Resolves the earliest valid date for each album.
function resolveAlbumDates(candidates) {
  const albumDates = new Map();

  for (const entry of candidates.filter((e) => e.source?.type === "album")) {
    const dates = entry.metadata?.dates;
    const parsed = dates?.length > 0 ? dates.map(parseIsoDate).find(Boolean) : null;

    if (parsed) {
      const albumName = entry.source.name;
      const existing = albumDates.get(albumName);

      if (!existing || isEarlierDate(parsed, existing)) {
        albumDates.set(albumName, parsed);
      }
    }
  }

  return albumDates;
}

// Returns true if date a is earlier than date b.
function isEarlierDate(a, b) {
  if (a.year !== b.year) {
    return a.year < b.year;
  } else if (a.month !== b.month) {
    return a.month < b.month;
  } else if (a.day !== b.day) {
    return a.day < b.day;
  } else if (a.hour !== b.hour) {
    return a.hour < b.hour;
  } else if (a.minute !== b.minute) {
    return a.minute < b.minute;
  }
  return a.second < b.second;
}

// Resolves the target path for a single entry.
function resolveTargetPath(entry, usedPaths, albumDates) {
  const pad2 = (num) => String(num).padStart(2, "0");

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

  const { year, month, day, hour, minute, second } = parsed;
  const timestamp = `${year}${pad2(month)}${pad2(day)}-${pad2(hour)}${pad2(minute)}${pad2(second)}`;
  const ext = extname(entry.mediaPath).toLowerCase();

  // Determine directory structure based on album membership
  const isAlbum = entry.source?.type === "album";
  const albumDate = isAlbum ? albumDates.get(entry.source.name) : null;

  // Use album's earliest date for directory structure, or entry's own date
  const dirDate = albumDate ?? parsed;

  // Format: yyyy/mm - MonthName (e.g., 2023/05 - May)
  const monthName = monthFormatter.format(new Date(dirDate.year, dirDate.month - 1));
  const monthDir = `${dirDate.year}/${pad2(dirDate.month)} - ${monthName}`;

  // Build path with optional album subdirectory
  const albumDatePrefix = `${dirDate.year}${pad2(dirDate.month)}${pad2(dirDate.day)}`;
  const basePath = isAlbum
    ? `${monthDir}/${albumDatePrefix} - ${entry.source.name}/${timestamp}${ext}`
    : `${monthDir}/${timestamp}${ext}`;

  const targetPath = resolveCollision(basePath, usedPaths);

  // Track this path as used
  usedPaths.add(targetPath);

  return {
    status: "processed",
    targetPath,
  };
}

// Resolves path collisions by appending -1, -2, etc.
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
