import { basename, dirname, join, extname } from "path";

// TODO: thoroughly document what and why we are doing here, including -edited scenario. .mp, .mp.jpg conflict scenarios, etc.
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
  const unlinkedMedia = new Set(); // Back to a single set!

  // Pass 3: Create initial manifest entries
  for (const mediaFilePath of filesMedia) {
    const mediaFileDir = dirname(mediaFilePath);
    const mediaEntry = {
      mediaPath: mediaFilePath,
      source: albums.has(mediaFileDir)
        ? { type: "album", name: albums.get(mediaFileDir) }
        : { type: "loose" },
    };
    manifest.set(mediaFilePath, mediaEntry);
    unlinkedMedia.add(mediaFilePath); // All media starts as unlinked
  }

  // --- Linking Passes ---

  // Pass 4: All Exact Matches (Non-consuming)
  // We combine old Passes 4 & 5 into one.
  for (const mediaFilePath of new Set(unlinkedMedia)) {
    const entry = manifest.get(mediaFilePath);
    const nonEditedPath = getNonEditedPath(mediaFilePath);
    const isEditedFile = mediaFilePath !== nonEditedPath;

    // Strategy 1: Edited file exact match
    if (isEditedFile && unmatchedMetadata.has(nonEditedPath)) {
      entry.jsonPath = metadataFiles.get(nonEditedPath);
      unlinkedMedia.delete(mediaFilePath);
    }
    // Strategy 2: Original file exact match
    else if (unmatchedMetadata.has(mediaFilePath)) {
      entry.jsonPath = metadataFiles.get(mediaFilePath);
      unlinkedMedia.delete(mediaFilePath);
    }
  }

  // Pass 5: All Fuzzy Matches (Non-consuming)
  // We combine old Passes 6 & 7 into one.
  for (const mediaFilePath of new Set(unlinkedMedia)) {
    const entry = manifest.get(mediaFilePath);
    const mediaPrefix = getPathPrefix(mediaFilePath);

    const nonEditedPath = getNonEditedPath(mediaFilePath);
    const isEditedFile = mediaFilePath !== nonEditedPath;
    const nonEditedPrefix = isEditedFile ? getPathPrefix(nonEditedPath) : null;

    for (const metadataKey of new Set(unmatchedMetadata)) {
      const metadataPrefix = getPathPrefix(metadataKey);

      const matchOnEdited =
        isEditedFile &&
        (metadataKey.startsWith(nonEditedPrefix) || nonEditedPath.startsWith(metadataPrefix));

      const matchOnOriginal =
        !isEditedFile &&
        (metadataKey.startsWith(mediaPrefix) || mediaFilePath.startsWith(metadataPrefix));

      if (matchOnEdited || matchOnOriginal) {
        entry.jsonPath = metadataFiles.get(metadataKey);
        unlinkedMedia.delete(mediaFilePath);
        break; // Stop searching for this media file
      }
    }
  }

  // Pass 6: Metadata Cleanup Pass (Consuming)
  // (This is the same as our previous "Pass 8")
  for (const metadataKey of new Set(unmatchedMetadata)) {
    if (manifest.has(metadataKey)) {
      const entry = manifest.get(metadataKey);
      if (entry.jsonPath === metadataFiles.get(metadataKey)) {
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
