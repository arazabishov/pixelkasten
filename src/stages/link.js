import { basename, dirname, join, extname } from "path";
import { progressBar } from "../utils/progress.js";

/**
 * The link stage is responsible for associating media files with their corresponding
 * JSON sidecar metadata files. It handles complex matching scenarios including:
 *  - Exact filename matches.
 *  - Truncated filenames (common in Google Takeout).
 *  - Duplicate markers (e.g., file(1).jpg).
 *  - Edited versions of files (e.g., file-edited.jpg).
 *
 * It also determines the source of the media file (album vs loose) based on directory
 * structure.
 *
 * @param {Object} rawCollections The collection of file paths to process.
 * @param {string[]} rawCollections.filesMedia List of absolute paths to media files.
 * @param {string[]} rawCollections.filesMetadata List of absolute paths to metadata files.
 * @param {string[]} rawCollections.filesMetadataAlbums List of absolute paths to album metadata files.
 * @returns {{
 *   manifest: Array<{
 *     mediaPath: string,
 *     jsonPath?: string,
 *     source: { type: 'album', name: string } | { type: 'loose' }
 *   }>,
 *   stats: {
 *     unmatchedMetadataFiles: Set<string>,
 *     unmatchedMediaFiles: Set<string>
 *   }
 * }} The linked manifest and processing statistics.
 */
export function link(rawCollections) {
  const { filesMedia, filesMetadata, filesMetadataAlbums } = rawCollections;

  // Pass 1: map metadata files to path based on normalized name.
  const metadataFiles = new Map();
  for (const metadataFilePath of filesMetadata) {
    const metadataFileName = basename(metadataFilePath);
    const metadataFileDir = dirname(metadataFilePath);
    const metadataFileKey = join(metadataFileDir, getNormalizedMetadataName(metadataFileName));

    metadataFiles.set(metadataFileKey, {
      path: metadataFilePath,
      dir: metadataFileDir,
    });
  }

  // Pass 2: map album directories to their names.
  const albums = new Map();
  for (const metadataFilePath of filesMetadataAlbums) {
    const albumDir = dirname(metadataFilePath);
    const albumName = basename(albumDir);

    albums.set(albumDir, albumName);
  }

  const bar = progressBar("⧗ Linking files |{bar}| {percentage}% | {value}/{total} files");
  bar.start(filesMedia.length, 0);

  // Pass 3: linking media files to their metadata files.
  const manifest = [];
  for (const mediaFilePath of filesMedia) {
    bar.increment();

    const mediaDir = dirname(mediaFilePath);
    const entry = {
      mediaPath: mediaFilePath,
      source: albums.has(mediaDir)
        ? { type: "album", name: albums.get(mediaDir) }
        : { type: "loose" },
    };

    // Determine the "target" path: accounts for original and edited files.
    const targetPath = getNonEditedPath(mediaFilePath);
    if (metadataFiles.has(targetPath)) {
      // Matching metadata to media file based on map look-up.
      const metadataFile = metadataFiles.get(targetPath);
      entry.jsonPath = metadataFile.path;
    } else {
      // Trying to match files based on prefix search.
      for (const [metadataKey, metadataFile] of metadataFiles) {
        // We only consider metadata files that are in the exact same directory.
        // It handles the "sibling directory" false positive and optimizes
        // performance by skipping unrelated files.
        if (metadataFile.dir !== mediaDir) {
          continue;
        }

        const targetPrefix = getPathPrefix(targetPath);
        const metadataPrefix = getPathPrefix(metadataKey);

        // Bi-directional check handles both truncation scenarios:
        //  - metadata > media: "very-long-name-full.json" matches "very-long-name.jpg".
        //  - media > metadata: "very-long-name-full.mov" matches "very-long-name.json".
        if (metadataKey.startsWith(targetPrefix) || targetPath.startsWith(metadataPrefix)) {
          entry.jsonPath = metadataFile.path;
          break;
        }
      }
    }

    manifest.push(entry);
  }

  bar.stop();

  // Pass 4: determine umatched files, mostly for reporting.
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

// Removes an '-edited' suffix from a file path's basename, if present.
// For example: '/path/to/image-edited.jpg' -> '/path/to/image.jpg'.
function getNonEditedPath(filePath) {
  return join(dirname(filePath), basename(filePath).replace(/-edited(\.|$)/, "$1"));
}

// Gets the full path of a file without its file extension.
// For example: '/path/to/file.txt' -> '/path/to/file'.
function getPathPrefix(filePath) {
  return join(dirname(filePath), basename(filePath, extname(filePath)));
}

function getNormalizedMetadataName(fileName) {
  if (!fileName) {
    return fileName;
  }

  // Guard: Check for .json extension (case-insensitive).
  const ext = extname(fileName);
  if (ext.toLowerCase() !== ".json") {
    return fileName;
  }

  // Get the name part *without* the extension.
  // For example: "IMG_123.jpg.supplemental-metadata(1)" or "IMG_123.jpg".
  const head = basename(fileName, ext);

  // Split the name part into its segments.
  const segments = head.split(".");

  // Handle simple case where there are no dots.
  if (segments.length === 1) {
    return head;
  }

  // Handle complex cases: "IMG_123.jpg.supplemental-metadata(1).json", "IMG_123.jpg.json".
  const tail = segments.pop();

  // We pop the last part to inspect it.
  const match = tail.match(/\(\d+\)/);

  if (match) {
    // Case: "IMG_123.jpg.supplemental-metadata(1).json".
    // We want to transform "IMG_123.jpg" -> "IMG_123(1).jpg".

    // Example: "(1)".
    const duplicateMarker = match[0];

    // Example: "IMG_123".
    const baseSegment = segments.shift();

    // Segments is now ["IMG_123(1)", "jpg"].
    segments.unshift(`${baseSegment}${duplicateMarker}`);

    // Result: "IMG_123(1).jpg".
    return segments.join(".");
  } else {
    // Example: "IMG_123.jpg.json", but we want "IMG_123.jpg" without extension.
    // We already have only ["IMG_123", "jpg"] because of the .pop().

    // Result: "IMG_123.jpg".
    return segments.join(".");
  }
}
