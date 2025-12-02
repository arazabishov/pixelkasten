import { basename, dirname, extname } from "path";
import { progressBar } from "../utils/progress.js";

// Regex for Google Takeout metadata suffixes (longest to shortest for greedy matching).
// Matches: .supplemental-metadata, .supplemental-metadat, ..., .s
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
// We include "-e" but EXCLUDE "-" to prevent separating legitimate filenames
// (e.g. "Vacation-2023") from becoming false positives for "Vacation".
const editedSuffixPattern = new RegExp(
  ["-edited", "-edite", "-edit", "-edi", "-ed", "-e"].join("|") + "$"
);

/**
 * The link stage matches media files to their JSON sidecar metadata files.
 * * Strategy:
 * 1. Exact Match Pass: Consumes JSON files that match 100% (Name + Index).
 * - Allows multiple media files to share a JSON (e.g. IMG.HEIC and IMG.MOV).
 * 2. Fuzzy Match Pass: Attempts to match remaining media to remaining JSONs.
 * - Checks for truncation in both directions.
 * - STRICTLY prevents stealing JSONs already claimed by Exact matches.
 */
export function link(rawCollections, options) {
  const { filesMedia, filesMetadata, filesMetadataAlbums } = rawCollections;
  const { fuzzyThreshold } = options;

  // 1. Index metadata by directory for O(1) lookups
  const metadataByDir = new Map();
  for (const filePath of filesMetadata) {
    const dir = dirname(filePath);
    if (!metadataByDir.has(dir)) metadataByDir.set(dir, []);
    metadataByDir.get(dir).push({ path: filePath, ...sidecar(filePath) });
  }

  // 2. Index albums
  const albums = new Map();
  for (const path of filesMetadataAlbums) {
    const dir = dirname(path);
    albums.set(dir, basename(dir));
  }

  // 3. Pre-parse media files for performance
  const parsedMedia = filesMedia.map((path) => ({
    originalPath: path,
    ...media(path),
  }));

  const manifest = [];
  const matchedMediaIndices = new Set();

  // Consumption Tracking:
  // usedByExact: JSONs claimed by Pass 1. Can be shared by other Exact matches.
  // usedByFuzzy: JSONs claimed by Pass 2. Exclusive (cannot be shared).
  const usedByExact = new Set();
  const usedByFuzzy = new Set();

  const bar = progressBar("⧗ Linking files |{bar}| {percentage}% | {value}/{total} files");
  bar.start(filesMedia.length, 0);

  /**
   * Helper to find the best metadata match within the same directory.
   */
  const findMatch = (media, allowFuzzy) => {
    const dir = dirname(media.originalPath);
    const candidates = metadataByDir.get(dir) || [];

    let bestMatch = null;
    let bestScore = 0;

    for (const meta of candidates) {
      // Safety: If we are in Fuzzy mode, we cannot touch JSONs that are
      // already claimed by another Fuzzy match. However, we CAN share
      // sidecars claimed by Exact matches (Live Photo scenario where
      // one component is truncated but should still share the sidecar).
      if (allowFuzzy && usedByFuzzy.has(meta.path)) continue;

      // Strict Duplicate Check:
      // (1) must always match (1). We never fuzzy match across indices.
      if (media.duplicate !== meta.duplicate) continue;

      const score = matchScore(media, meta, allowFuzzy, fuzzyThreshold);

      // In strict mode, ignore anything less than a perfect match
      if (!allowFuzzy && score < 100) continue;

      if (score > bestScore) {
        bestScore = score;
        bestMatch = meta;
      }
    }
    return bestMatch;
  };

  // --- PASS 1: EXACT MATCHES ---
  // We match files that we are 100% sure about.
  // We allow sharing here (e.g. IMG.MP and IMG.MP.jpg share IMG.MP.jpg.json).
  for (let i = 0; i < parsedMedia.length; i++) {
    const media = parsedMedia[i];
    const match = findMatch(media, false);

    if (match) {
      matchedMediaIndices.add(i);
      usedByExact.add(match.path);
      manifest.push(createEntry(media.originalPath, match.path, albums));
      bar.increment();
    }
  }

  // --- PASS 2: FUZZY MATCHES ---
  // We match remaining files using fuzzy logic.
  for (let i = 0; i < parsedMedia.length; i++) {
    if (matchedMediaIndices.has(i)) continue;

    const media = parsedMedia[i];
    const match = findMatch(media, true);

    if (match) {
      usedByFuzzy.add(match.path);
      manifest.push(createEntry(media.originalPath, match.path, albums));
    } else {
      manifest.push(createEntry(media.originalPath, undefined, albums));
    }
    bar.increment();
  }

  bar.stop();

  // Statistics
  const allUsed = new Set([...usedByExact, ...usedByFuzzy]);
  const unmatchedMetadataFiles = new Set(filesMetadata.filter((f) => !allUsed.has(f)));
  const unmatchedMediaFiles = new Set(manifest.filter((m) => !m.jsonPath).map((m) => m.mediaPath));

  return {
    manifest,
    stats: { unmatchedMetadataFiles, unmatchedMediaFiles },
  };
}

function createEntry(mediaPath, jsonPath, albums) {
  const dir = dirname(mediaPath);
  return {
    mediaPath,
    source: albums.has(dir) ? { type: "album", name: albums.get(dir) } : { type: "loose" },
    jsonPath,
  };
}

/**
 * Calculates match score.
 * Hierarchy:
 * - 150: Exact Name + Exact Extension Match (Safest)
 * - 100: Exact Name Match OR Embedded Extension Match (Safe)
 * - 50+: Fuzzy/Truncated Name Match (Lowest Priority)
 * - 0: No Match
 */
function matchScore(media, meta, allowFuzzy, fuzzyThreshold) {
  const { name: mediaName, extension: mediaExt } = media;
  const { name: metaName, extension: metaExt } = meta;

  // 1. Direct Name Match
  if (mediaName === metaName) {
    return metaExt && metaExt === mediaExt ? 150 : 100;
  }

  // 2. Embedded Extension Match
  // Handles cases where metadata includes the media extension in its name.
  // e.g. Media: "123.MP" (Name: "123", Ext: ".MP") vs Meta: "123.MP"
  const compositeName = `${mediaName}${mediaExt}`.toLowerCase();
  const normalizedMeta = metaName.toLowerCase();

  if (compositeName === normalizedMeta) {
    return 100; // Treated as an Exact Match
  }

  if (!allowFuzzy) return 0;

  // 3. Fuzzy matching requires sufficient filename length.
  // Google only truncates names > ~40 chars, so shorter names cannot be
  // truncation candidates. This prevents false positives like IMG_1234
  // matching IMG_123.json.
  const longerName = Math.max(mediaName.length, metaName.length);
  if (longerName < fuzzyThreshold) return 0;

  // 4. Bidirectional Fuzzy Match
  // Checks if A starts with B OR B starts with A.
  // Handles truncation on either file system side or Google side.
  const mediaStarts = mediaName.startsWith(metaName);
  const metaStarts = metaName.startsWith(mediaName);

  if (mediaStarts || metaStarts) {
    // Score is 50 + length of the SHORTER string (common prefix).
    return 50 + Math.min(mediaName.length, metaName.length);
  }

  return 0;
}

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

  return { name, duplicate, extension: extension.toLowerCase() };
}

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
