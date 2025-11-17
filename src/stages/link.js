import { basename, dirname, join, extname } from "path";

export function link(rawCollections) {
  const { filesMedia, filesMetadata, filesMetadataAlbums } = rawCollections;

  // Pass 1: Build a map of metadata files with normalized names.
  const metadataFiles = new Map();
  for (const metadataFilePath of filesMetadata) {
    const metadataFileName = basename(metadataFilePath);
    const metadataFileDir = dirname(metadataFilePath);
    const key = join(metadataFileDir, getNormalizedMetadataName(metadataFileName));
    metadataFiles.set(key, metadataFilePath);
  }

  // Pass 2: Build a map of album directories.
  const albums = new Map();
  for (const metadataFilePath of filesMetadataAlbums) {
    const metadataFileDir = dirname(metadataFilePath);
    const albumName = basename(metadataFileDir);
    albums.set(metadataFileDir, albumName);
  }

  // --- Manifest Generation ---

  const manifest = new Map();
  const unmatchedMetadata = new Set(metadataFiles.keys());

  // Pass 3: Create initial manifest entries AND partition media files.
  const unlinkedEditedMedia = new Set();
  const unlinkedOriginalMedia = new Set();

  for (const mediaFilePath of filesMedia) {
    const mediaFileDir = dirname(mediaFilePath);
    const mediaEntry = {
      mediaPath: mediaFilePath,
      source: albums.has(mediaFileDir)
        ? { type: "album", name: albums.get(mediaFileDir) }
        : { type: "loose" },
    };
    manifest.set(mediaFilePath, mediaEntry);

    const nonEditedPath = getNonEditedPath(mediaFilePath);
    if (mediaFilePath !== nonEditedPath) {
      unlinkedEditedMedia.add(mediaFilePath);
    } else {
      unlinkedOriginalMedia.add(mediaFilePath);
    }
  }

  // --- Linking Passes ---

  // Pass 4: Exact Match - Edited Files (non-consuming)
  for (const mediaFilePath of unlinkedEditedMedia) {
    const entry = manifest.get(mediaFilePath);
    const nonEditedPath = getNonEditedPath(mediaFilePath);

    if (unmatchedMetadata.has(nonEditedPath)) {
      entry.jsonPath = metadataFiles.get(nonEditedPath);
      unlinkedEditedMedia.delete(mediaFilePath); // Linked!
    }
  }

  // Pass 5: Exact Match - Original Files (NON-CONSUMING)
  // This is the FIX. We make this non-consuming to allow
  // dependent files (like .MP) to also link to this metadata.
  for (const mediaFilePath of unlinkedOriginalMedia) {
    const entry = manifest.get(mediaFilePath);
    if (unmatchedMetadata.has(mediaFilePath)) {
      entry.jsonPath = metadataFiles.get(mediaFilePath);
      // unmatchedMetadata.delete(mediaFilePath); // <-- REMOVED
      unlinkedOriginalMedia.delete(mediaFilePath); // Linked!
    }
  }

  // Pass 6: Fuzzy Match - Edited Files (non-consuming)
  for (const mediaFilePath of unlinkedEditedMedia) {
    const entry = manifest.get(mediaFilePath);
    const nonEditedPath = getNonEditedPath(mediaFilePath);
    const nonEditedPrefix = getPathPrefix(nonEditedPath);

    for (const metadataKey of new Set(unmatchedMetadata)) {
      const metadataPrefix = getPathPrefix(metadataKey);
      const isMatch =
        metadataKey.startsWith(nonEditedPrefix) || nonEditedPath.startsWith(metadataPrefix);

      if (isMatch) {
        entry.jsonPath = metadataFiles.get(metadataKey);
        unlinkedEditedMedia.delete(mediaFilePath);
        break;
      }
    }
  }

  // Pass 7: Fuzzy Match - Original Files (non-consuming)
  // This will now successfully link the .MP file.
  for (const mediaFilePath of unlinkedOriginalMedia) {
    const entry = manifest.get(mediaFilePath);
    const mediaPrefix = getPathPrefix(mediaFilePath);

    for (const metadataKey of new Set(unmatchedMetadata)) {
      const metadataPrefix = getPathPrefix(metadataKey);
      const isMatch =
        metadataKey.startsWith(mediaPrefix) || mediaFilePath.startsWith(metadataPrefix);

      if (isMatch) {
        entry.jsonPath = metadataFiles.get(metadataKey);
        // We make this pass non-consuming as well to be safe.
        // unmatchedMetadata.delete(metadataKey); // <-- Ensure this is non-consuming
        unlinkedOriginalMedia.delete(mediaFilePath);
        break;
      }
    }
  }

  // Pass 8: [NEW] Metadata Cleanup Pass (consuming)
  // Any "main" file (e.g., .jpg) that was linked in Pass 5
  // can now "claim" its metadata from the unmatched set.
  for (const metadataKey of new Set(unmatchedMetadata)) {
    // If a media file exists with the *exact* name as this metadata key...
    if (manifest.has(metadataKey)) {
      // ...and that media file *was successfully linked* (to this key)...
      const entry = manifest.get(metadataKey);
      if (entry.jsonPath === metadataFiles.get(metadataKey)) {
        // ...then we consume the key.
        unmatchedMetadata.delete(metadataKey);
      }
    }
  }

  return Array.from(manifest.values());
}

// Removes an '-edited' suffix from a file path's basename, if present.
// For example: '/path/to/image-edited.jpg' -> '/path/to/image.jpg'
function getNonEditedPath(filePath) {
  return join(dirname(filePath), basename(filePath).replace(/-edited(\.|$)/, "$1"));
}

// Gets the full path of a file without its file extension.
// For example: '/path/to/file.txt' -> '/path/to/file'
function getPathPrefix(filePath) {
  return join(dirname(filePath), basename(filePath, extname(filePath)));
}

export function getNormalizedMetadataName(fileName) {
  if (!fileName) {
    return fileName;
  }

  // 1. Guard: check for .json extension (case-insensitive)
  const ext = extname(fileName);
  if (ext.toLowerCase() !== ".json") {
    return fileName;
  }

  // 2. Get the name part *without* the extension: "A.B.C (1)" or "A.B.C" or "A"
  const head = basename(fileName, ext);

  // 3. Split the name part into its segments
  const segments = head.split(".");

  // 4. Handle simple case where there are no dots.
  if (segments.length === 1) {
    return head;
  }

  // 5. Handle complex cases: "A.B.C (1).json" or "A.B.C.json". We pop the last part to inspect it.
  const tail = segments.pop();
  const match = tail.match(/\(\d+\)/);

  if (match) {
    // Case: "A.B.C (1).json"
    // We want to transform "A.B" -> "A(1).B"
    const duplicateMarker = match[0]; // e.g., "(1)"
    const base = segments.shift(); // e.g., "A"
    segments.unshift(`${base}${duplicateMarker}`); // segments is now ["A(1)", "B"]
    return segments.join("."); // "A(1).B"
  } else {
    // Case: "A.B.C.json"
    // We want "A.B"
    // `segments` is already ["A", "B"] because of the .pop()
    return segments.join("."); // "A.B"
  }
}
