import { basename, dirname, extname } from "path";
import { progressBar } from "../utils/progress.js";

// Default minimum filename length to allow fuzzy matching.
// Google only truncates filenames > ~40 characters, so shorter names
// should never be fuzzy matched (they weren't truncated).
const DEFAULT_MIN_FUZZY_LENGTH = 40;

// Exhaustive list of Google Takeout suffixes.
// Order matters: longest to shortest to ensure greedy matching.
const knownSuffixes = [
  ".supplemental-metadata",
  ".supplemental-metadat",
  ".supplemental-metada",
  ".supplemental-metad",
  ".supplemental-meta",
  ".supplemental-met",
  ".supplemental-me",
  ".supplemental-m",
  ".supplemental-",
  ".supplemental",
  ".supplementa",
  ".supplement",
  ".supplemen",
  ".suppleme",
  ".supplem",
  ".supple",
  ".suppl",
  ".supp",
  ".sup",
  ".su",
  ".s",
  ".json",
  ".",
];

// Exhaustive list of -edited variations (longest to shortest).
// We include "-e" but EXCLUDE "-" to prevent separating legitimate filenames
// (e.g. "Vacation-2023") from becoming false positives for "Vacation".
const editedSuffixes = ["-edited", "-edite", "-edit", "-edi", "-ed", "-e"];

/**
 * The link stage matches media files to their JSON sidecar metadata files.
 * * Strategy:
 * 1. Exact Match Pass: Consumes JSON files that match 100% (Name + Index).
 * - Allows multiple media files to share a JSON (e.g. IMG.HEIC and IMG.MOV).
 * 2. Fuzzy Match Pass: Attempts to match remaining media to remaining JSONs.
 * - Checks for truncation in both directions.
 * - STRICTLY prevents stealing JSONs already claimed by Exact matches.
 */
export function link(rawCollections, options = {}) {
  const { filesMedia, filesMetadata, filesMetadataAlbums } = rawCollections;
  const minFuzzyLength = options.minFuzzyLength ?? DEFAULT_MIN_FUZZY_LENGTH;

  // 1. Index metadata by directory for O(1) lookups
  const metadataByDir = new Map();
  for (const filePath of filesMetadata) {
    const dir = dirname(filePath);
    if (!metadataByDir.has(dir)) metadataByDir.set(dir, []);
    metadataByDir.get(dir).push(parseMetadata(filePath));
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
    ...parseMedia(path),
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
      if (allowFuzzy && usedByFuzzy.has(meta.originalPath)) continue;

      // Strict Duplicate Check:
      // (1) must always match (1). We never fuzzy match across indices.
      if (media.duplicate !== meta.duplicate) continue;

      const score = matchScore(media, meta, allowFuzzy, minFuzzyLength);

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
      usedByExact.add(match.originalPath);
      manifest.push(createEntry(media.originalPath, match.originalPath, albums));
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
      usedByFuzzy.add(match.originalPath);
      manifest.push(createEntry(media.originalPath, match.originalPath, albums));
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
function matchScore(media, meta, allowFuzzy, minFuzzyLength) {
  const { name: mediaName, extension: mediaExt } = media;
  const { name: metaName, relatedExtension: metaExt } = meta;

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
  if (longerName < minFuzzyLength) return 0;

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

function parseMedia(filePath) {
  const extension = extname(filePath);
  let name = basename(filePath, extension);
  let duplicate = null;

  // 1. Strip duplicate marker (N) from the end
  const dupMatch = name.match(/\((\d+)\)$/);
  if (dupMatch) {
    duplicate = parseInt(dupMatch[1], 10);
    name = name.slice(0, dupMatch.index);
  }

  // 2. Strip -edited variants from the end (longest to shortest)
  for (const suffix of editedSuffixes) {
    if (name.endsWith(suffix)) {
      name = name.slice(0, -suffix.length);
      break;
    }
  }

  return {
    name,
    duplicate,
    extension: extension.toLowerCase(),
  };
}

function parseMetadata(filePath) {
  const ext = extname(filePath);
  let name = basename(filePath, ext);
  let duplicate = null;
  let relatedExtension = null;

  let changed;
  do {
    changed = false;
    const startName = name;

    // 1. Clean known metadata suffixes
    for (const suffix of knownSuffixes) {
      if (name.endsWith(suffix)) {
        name = name.slice(0, -suffix.length);
        changed = true;
        break;
      }
    }

    // 2. Detect Duplicate Marker (N)
    const dupMatch = name.match(/\((\d+)\)(?:\.[^.]+)?$/);
    if (dupMatch) {
      if (duplicate === null) {
        duplicate = parseInt(dupMatch[1], 10);
      }
      const fullMatch = dupMatch[0];
      const marker = `(${dupMatch[1]})`;
      const suffix = fullMatch.slice(marker.length);
      name = name.slice(0, dupMatch.index) + suffix;
      changed = true;
    }
  } while (changed);

  // 3. Extract Related Extension (if present)
  const potentialExt = extname(name);
  if (potentialExt) {
    relatedExtension = potentialExt.toLowerCase();
    name = basename(name, potentialExt);
  }

  return {
    originalPath: filePath,
    name,
    duplicate,
    relatedExtension,
  };
}
