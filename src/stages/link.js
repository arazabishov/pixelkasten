import { basename, dirname, join, extname } from "path";

export function link(rawCollections) {
  const { filesMedia, filesMetadata, filesMetadataAlbums } = rawCollections;

  // Pass 1: build a map of metadata files with normalized names.
  const metadataFiles = new Map();
  for (const metadataFilePath of filesMetadata) {
    const metadataFileName = basename(metadataFilePath);
    const metadataFileDir = dirname(metadataFilePath);
    const key = join(metadataFileDir, getNormalizedMetadataName(metadataFileName));

    // The key most of the time should match to the path of media file it belongs to.
    metadataFiles.set(key, metadataFilePath);
  }

  // Pass 2: build a map of albums directories
  const albums = new Map();
  for (const metadataFilePath of filesMetadataAlbums) {
    const metadataFileDir = dirname(metadataFilePath);
    const albumName = basename(metadataFileDir);

    // We will need the album name at later point when constructing manifest entries.
    albums.set(metadataFileDir, albumName);
  }

  const manifest = new Map();
  const unmatchedMetadataFiles = new Set(metadataFiles.keys());
  const unmatchedMediaEditedFiles = new Set();
  const unmatchedMediaFiles = new Set();

  // Pass 3: construct manifest entries and partition media files.
  for (const mediaFilePath of filesMedia) {
    const mediaFileDir = dirname(mediaFilePath);
    manifest.set(mediaFilePath, {
      mediaPath: mediaFilePath,
      source: albums.has(mediaFileDir)
        ? { type: "album", name: albums.get(mediaFileDir) }
        : { type: "loose" },
    });

    const nonEditedPath = getNonEditedPath(mediaFilePath);
    if (mediaFilePath !== nonEditedPath) {
      unmatchedMediaEditedFiles.add(mediaFilePath);
    } else {
      unmatchedMediaFiles.add(mediaFilePath);
    }
  }

  // Pass 4: exact match - edited files (non-consuming)
  for (const mediaFilePath of unmatchedMediaEditedFiles) {
    const nonEditedPath = getNonEditedPath(mediaFilePath);

    if (unmatchedMetadataFiles.has(nonEditedPath)) {
      const entry = manifest.get(mediaFilePath);
      entry.jsonPath = metadataFiles.get(nonEditedPath);

      unmatchedMediaEditedFiles.delete(mediaFilePath);
    }
  }

  // Pass 5: exact match - original files (consuming)
  for (const mediaFilePath of unmatchedMediaFiles) {
    if (unmatchedMetadataFiles.has(mediaFilePath)) {
      const entry = manifest.get(mediaFilePath);
      entry.jsonPath = metadataFiles.get(mediaFilePath);

      // Remove both metadata and media files
      unmatchedMetadataFiles.delete(mediaFilePath);
      unmatchedMediaFiles.delete(mediaFilePath);
    }
  }

  // TODO: is it okay to iterate over collection that you're deleting from?
  // Pass 6: fuzzy match - edited Files (non-consuming)
  for (const mediaFilePath of unmatchedMediaEditedFiles) {
    const nonEditedPath = getNonEditedPath(mediaFilePath);
    const nonEditedPrefix = getPathPrefix(nonEditedPath);

    for (const metadataKey of unmatchedMetadataFiles) {
      const metadataPrefix = getPathPrefix(metadataKey);

      if (metadataKey.startsWith(nonEditedPrefix) || nonEditedPath.startsWith(metadataPrefix)) {
        const entry = manifest.get(mediaFilePath);
        entry.jsonPath = metadataFiles.get(metadataKey);

        unmatchedMediaEditedFiles.delete(mediaFilePath);
        break;
      }
    }
  }

  // Pass 7: fuzzy match - original files (consuming)
  for (const mediaFilePath of unmatchedMediaFiles) {
    const mediaPrefix = getPathPrefix(mediaFilePath);

    for (const metadataKey of new Set(unmatchedMetadataFiles)) {
      const metadataPrefix = getPathPrefix(metadataKey);

      if (metadataKey.startsWith(mediaPrefix) || mediaFilePath.startsWith(metadataPrefix)) {
        const entry = manifest.get(mediaFilePath);
        entry.jsonPath = metadataFiles.get(metadataKey);

        unmatchedMetadataFiles.delete(metadataKey);
        unmatchedMediaFiles.delete(mediaFilePath);
        break;
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
