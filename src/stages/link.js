import { basename, dirname, extname } from "path";
import { progressBar } from "../utils/progress.js";

// Regex for Google Takeout metadata suffixes (longest to shortest for greedy matching).
const metadataSuffixPattern = new RegExp(
  [
    "\\.supplemental-metadata",
    "\\.supplemental-metadat",
    "\\.supplemental-metada",
    "\\.supplemental-metad",
    "\\.supplemental-meta",
    "\\.supplemental-met",
    "\\.supplemental-me",
    "\\.supplemental-m",
    "\\.supplemental-",
    "\\.supplemental",
    "\\.supplementa",
    "\\.supplement",
    "\\.supplemen",
    "\\.suppleme",
    "\\.supplem",
    "\\.supple",
    "\\.suppl",
    "\\.supp",
    "\\.sup",
    "\\.su",
    "\\.s",
  ].join("|") + "$"
);

// Regex for -edited variations (longest to shortest for greedy matching).
const editedSuffixPattern = new RegExp(
  ["-edited", "-edite", "-edit", "-edi", "-ed", "-e"].join("|") + "$"
);

/**
 * Matches media files to their JSON sidecar metadata files.
 *
 * For each media file, attempts an exact match first (name + extension + duplicate marker),
 * then falls back to fuzzy matching for truncated filenames if no exact match is found.
 *
 * @param {{
 *   filesMedia: string[],
 *   filesMetadata: string[],
 *   filesMetadataAlbums: string[]
 * }} rawCollections The raw file collections from the scan stage.
 * @param {{ fuzzyThreshold: number }} options Configuration for fuzzy matching.
 * @returns {{
 *   manifest: Array<{ mediaPath: string, jsonPath?: string, source: object }>,
 *   stats: { unmatchedMetadataFiles: Set<string>, unmatchedMediaFiles: Set<string> }
 * }} The manifest of linked files and matching statistics.
 */
export function link(rawCollections, options) {
  const { filesMedia, filesMetadata, filesMetadataAlbums } = rawCollections;
  const { fuzzyThreshold } = options;

  // Stage 1: index metadata by directory for O(1) lookups.
  const metadataByDir = new Map();
  for (const filePath of filesMetadata) {
    const dir = dirname(filePath);
    if (!metadataByDir.has(dir)) {
      metadataByDir.set(dir, []);
    }
    metadataByDir.get(dir).push({
      path: filePath,
      ...sidecar(filePath),
    });
  }

  // Stage 2: index albums by directory.
  const albums = new Map();
  for (const path of filesMetadataAlbums) {
    const dir = dirname(path);
    albums.set(dir, basename(dir));
  }

  // Stage 3: pre-parse media files for performance.
  const parsedMedia = [];
  for (const filePath of filesMedia) {
    parsedMedia.push({
      path: filePath,
      ...media(filePath),
    });
  }

  const manifest = [];

  const bar = progressBar("⧗ Linking files |{bar}| {percentage}% | {value}/{total} files");
  bar.start(filesMedia.length, 0);

  // Stage 4: match media files to their metadata sidecars. Try exact match first:
  // based on name, extension, duplicate marker, then fuzzy - prefix search.
  for (const media of parsedMedia) {
    const match =
      findMatch(media, metadataByDir, fuzzyThreshold, false) ??
      findMatch(media, metadataByDir, fuzzyThreshold, true);

    const albumDir = dirname(media.path);
    const source = albums.has(albumDir)
      ? { type: "album", name: albums.get(albumDir) }
      : { type: "loose" };

    manifest.push({ mediaPath: media.path, jsonPath: match?.path, source: source });

    bar.increment();
  }

  bar.stop();

  // Stage 5: compute statistics from the manifest.
  const unmatchedMetadataFiles = new Set(filesMetadata);
  const unmatchedMediaFiles = new Set(filesMedia);

  for (const { mediaPath, jsonPath } of manifest) {
    if (jsonPath) {
      unmatchedMetadataFiles.delete(jsonPath);
      unmatchedMediaFiles.delete(mediaPath);
    }
  }

  return {
    manifest,
    stats: {
      unmatchedMetadataFiles,
      unmatchedMediaFiles,
    },
  };
}

// Finds the best metadata match for a media file within the same directory.
function findMatch(media, metadataByDir, fuzzyThreshold, allowFuzzy) {
  const dir = dirname(media.path);
  const candidates = metadataByDir.get(dir) || [];

  let bestMatch = null;
  let bestScore = 0;

  for (const meta of candidates) {
    // Strict duplicate check: (1) must always match (1).
    // We never fuzzy match across indices.
    if (media.duplicate !== meta.duplicate) continue;

    const score = matchScore(media, meta, allowFuzzy, fuzzyThreshold);

    // In strict mode, ignore anything less than a perfect match.
    if (!allowFuzzy && score < 100) continue;

    if (score > bestScore) {
      bestScore = score;
      bestMatch = meta;
    }
  }

  return bestMatch;
}

// Calculates a match score between a media file and a metadata file.
// Score hierarchy:
//  - 150: Exact name + exact extension match (safest)
//  - 100: Exact name match OR embedded extension match (safe)
//  - 50+: Fuzzy/truncated name match (lowest priority)
//  - 0: No match
function matchScore(media, meta, allowFuzzy, fuzzyThreshold) {
  const { name: mediaName, extension: mediaExt } = media;
  const { name: metaName, extension: metaExt } = meta;

  // Case 1: direct name match.
  if (mediaName === metaName) {
    return metaExt && metaExt === mediaExt ? 150 : 100;
  }

  // Case 2: embedded extension match.
  // Handles cases where metadata includes the media extension in its name.
  // e.g. Media: "123.MP" (Name: "123", Ext: ".MP") vs Meta: "123.MP"
  const compositeName = `${mediaName}${mediaExt}`.toLowerCase();
  const normalizedMeta = metaName.toLowerCase();

  if (compositeName === normalizedMeta) {
    return 100; // Treated as an exact match.
  }

  if (!allowFuzzy) return 0;

  // Case 3: fuzzy matching requires sufficient filename length.
  // Google only truncates names > ~40 chars, so shorter names cannot be
  // truncation candidates. This prevents false positives like IMG_1234
  // matching IMG_123.json.
  const longerName = Math.max(mediaName.length, metaName.length);
  if (longerName < fuzzyThreshold) return 0;

  // Case 4: bidirectional fuzzy match.
  // Checks if A starts with B OR B starts with A.
  // Handles truncation on either file system side or Google side.
  const mediaStarts = mediaName.startsWith(metaName);
  const metaStarts = metaName.startsWith(mediaName);

  if (mediaStarts || metaStarts) {
    // Score is 50 + length of the shorter string (common prefix).
    return 50 + Math.min(mediaName.length, metaName.length);
  }

  return 0;
}

// Parses a media file path into its component parts for matching.
function media(filePath) {
  const extension = extname(filePath);
  let name = basename(filePath, extension);

  // Strip duplicate marker (N) from the end.
  const duplicateMatch = name.match(/\((\d+)\)$/);
  const duplicate = duplicateMatch ? parseInt(duplicateMatch[1]) : null;

  if (duplicateMatch) {
    name = name.slice(0, duplicateMatch.index);
  }

  // Strip -edited variants from the end.
  const editedMatch = name.match(editedSuffixPattern);
  if (editedMatch) {
    name = name.slice(0, editedMatch.index);
  }

  return { name, duplicate, extension: extension?.toLowerCase() };
}

// Parses a sidecar JSON file path into its component parts for matching.
function sidecar(filePath) {
  let name = basename(filePath, extname(filePath));

  // Strip duplicate marker (N) from the end.
  const duplicateMatch = name.match(/\((\d+)\)$/);
  const duplicate = duplicateMatch ? parseInt(duplicateMatch[1]) : null;

  if (duplicateMatch) {
    name = name.slice(0, duplicateMatch.index);
  }

  // Strip metadata suffix from the end.
  const metadataMatch = name.match(metadataSuffixPattern);
  if (metadataMatch) {
    name = name.slice(0, metadataMatch.index);
  }

  // Extract extension (e.g., .jpg from "photo.jpg").
  const extension = extname(name);
  if (extension) {
    name = basename(name, extension);
  }

  return { name, duplicate, extension: extension?.toLowerCase() };
}
