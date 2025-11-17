import { basename, dirname, join } from "path";

export function linkBackup(rawCollections) {
  const { filesMedia, filesMetadata, filesMetadataAlbums } = rawCollections;

  // Pass 1: build a map of metadata files with normalized names.
  const metadataFiles = new Map();
  for (const metadataFilePath of filesMetadata) {
    const metadataFileName = basename(metadataFilePath);
    const metadataFileDir = dirname(metadataFilePath);
    const key = join(metadataFileDir, normalizeMetadataName(metadataFileName));

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
  const unmatchedMediaFiles = new Set();
  const unmatchedMetadataFiles = new Set(metadataFiles.keys());

  // Pass 3: construct empty manifest entries and perform the first metadata look-up.
  for (const mediaFilePath of filesMedia) {
    const mediaFileDir = dirname(mediaFilePath);
    const mediaEntry = {
      mediaPath: mediaFilePath,
    };

    if (metadataFiles.has(mediaFilePath)) {
      mediaEntry.jsonPath = metadataFiles.get(mediaFilePath);
      unmatchedMetadataFiles.delete(mediaFilePath);
    } else {
      unmatchedMediaFiles.add(mediaFilePath);
    }

    if (albums.has(mediaFileDir)) {
      mediaEntry.source = {
        type: "album",
        name: albums.get(mediaFileDir),
      };
    } else {
      mediaEntry.source = {
        type: "loose",
      };
    }

    manifest.set(mediaFilePath, mediaEntry);
  }

  // Pass 4: link unmatched media files
  for (const mediaFilePath of new Set(unmatchedMediaFiles)) {
    // If there was no exact match, we can try to do a prefix search
    const mediaFileName = basename(mediaFilePath);
    const mediaFileDir = dirname(mediaFilePath);

    // Drop the extension and create a new path out of it.
    const nameWithoutExt = dropExtension(mediaFileName);
    const prefix = join(mediaFileDir, nameWithoutExt);

    for (const metadataFilePath of new Set(unmatchedMetadataFiles)) {
      if (metadataFilePath.startsWith(prefix)) {
        const entry = manifest.get(mediaFilePath);
        entry.jsonPath = metadataFiles.get(metadataFilePath);

        unmatchedMediaFiles.delete(mediaFilePath);
        unmatchedMetadataFiles.delete(metadataFilePath);

        break;
      }
    }
  }

  // Pass 5: link unmatched metadata files
  for (const metadataFilePath of new Set(unmatchedMetadataFiles)) {
    // If there was no exact match, we can try to do a prefix search
    const metadataFileName = basename(metadataFilePath);
    const metadataFileDir = dirname(metadataFilePath);

    // Drop the extension and create a new path out of it.
    const nameWithoutExt = dropExtension(metadataFileName);
    const prefix = join(metadataFileDir, nameWithoutExt);

    for (const mediaFilePath of new Set(unmatchedMediaFiles)) {
      if (mediaFilePath.startsWith(prefix)) {
        const entry = manifest.get(mediaFilePath);
        entry.jsonPath = metadataFiles.get(metadataFilePath);

        unmatchedMediaFiles.delete(mediaFilePath);
        unmatchedMetadataFiles.delete(metadataFilePath);

        break;
      }
    }
  }

  // TODO: consider calling link recursively, but second time only for -edited files?
  // Or better, extract steps above into its own files, and let -edited files handled separately?

  // Pass 6: handling media files with "-edited" suffix
  for (const mediaFilePath of new Set(unmatchedMediaFiles)) {
    const mediaFileName = basename(mediaFilePath);
    const mediaFileDir = dirname(mediaFilePath);

    // Remove -edited from the full filename, which might appear before any extension
    const mediaFileNameWithoutEditedSuffix = mediaFileName.replace(/-edited(\.|$)/, "$1");
    const mediaFilePathWithoutEditedSuffix = join(mediaFileDir, mediaFileNameWithoutEditedSuffix);

    if (mediaFileName === mediaFileNameWithoutEditedSuffix) {
      // Skipping this iteration because this pass is focused only on "-edited" files
      continue;
    }

    // Trying the exact match first
    if (metadataFiles.has(mediaFilePathWithoutEditedSuffix)) {
      const metadataFilePath = metadataFiles.get(mediaFilePathWithoutEditedSuffix);

      // We used mediaFilePathWithoutEditedSuffix for look-up of metadata file only.
      // We still use mediaFilePath as a key since the key always has to point at media file.
      const entry = manifest.get(mediaFilePath);
      entry.jsonPath = metadataFilePath;

      // Ensure the entry is deleted to pass through the integrity check at the end.
      unmatchedMetadataFiles.delete(mediaFilePathWithoutEditedSuffix);
    } else {
      // Drop the extension and create a new path out of it.
      const nameWithoutExt = dropExtension(mediaFileNameWithoutEditedSuffix);
      const prefix = join(mediaFileDir, nameWithoutExt);

      for (const metadataFilePath of metadataFiles.keys()) {
        if (metadataFilePath.startsWith(prefix)) {
          const entry = manifest.get(mediaFilePath);
          entry.jsonPath = metadataFiles.get(metadataFilePath);

          unmatchedMediaFiles.delete(mediaFilePath);
          unmatchedMetadataFiles.delete(metadataFilePath);

          break;
        }
      }
    }
  }

  return Array.from(manifest.values());
}

/**
 * Removes the '-edited' suffix from a media file path.
 * e.g., /path/to/IMG_001-edited.jpg -> /path/to/IMG_001.jpg
 * If no '-edited' suffix is present, it returns the original path.
 */
function getNonEditedPath(mediaFilePath) {
  const mediaFileDir = dirname(mediaFilePath);
  const mediaFileName = basename(mediaFilePath);

  // Remove -edited from the full filename, which might appear before any extension
  const mediaFileNameWithoutEditedSuffix = mediaFileName.replace(/-edited(\.|$)/, "$1");

  if (mediaFileName === mediaFileNameWithoutEditedSuffix) {
    return mediaFilePath; // Not an edited file
  }

  return join(mediaFileDir, mediaFileNameWithoutEditedSuffix);
}

/**
 * Gets the full path of a file without its extension.
 * e.g., /path/to/IMG_001.jpg -> /path/to/IMG_001
 */
function getPathPrefix(filePath) {
  const fileDir = dirname(filePath);
  const fileName = basename(filePath);
  const nameWithoutExt = dropExtension(fileName);
  return join(fileDir, nameWithoutExt);
}

export function link(rawCollections) {
  const { filesMedia, filesMetadata, filesMetadataAlbums } = rawCollections;

  // Pass 1: Build a map of metadata files with normalized names.
  const metadataFiles = new Map();
  for (const metadataFilePath of filesMetadata) {
    const metadataFileName = basename(metadataFilePath);
    const metadataFileDir = dirname(metadataFilePath);
    const key = join(metadataFileDir, normalizeMetadataName(metadataFileName));
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
  // We now run four distinct, prioritized passes.

  // Pass 4: Exact Match - Edited Files (non-consuming)
  for (const mediaFilePath of unlinkedEditedMedia) {
    const entry = manifest.get(mediaFilePath);
    const nonEditedPath = getNonEditedPath(mediaFilePath);

    if (unmatchedMetadata.has(nonEditedPath)) {
      entry.jsonPath = metadataFiles.get(nonEditedPath);
      unlinkedEditedMedia.delete(mediaFilePath); // Linked!
    }
  }

  // Pass 5: Exact Match - Original Files (consuming)
  for (const mediaFilePath of unlinkedOriginalMedia) {
    const entry = manifest.get(mediaFilePath);
    if (unmatchedMetadata.has(mediaFilePath)) {
      entry.jsonPath = metadataFiles.get(mediaFilePath);
      unmatchedMetadata.delete(mediaFilePath); // Consume the key
      unlinkedOriginalMedia.delete(mediaFilePath); // Linked!
    }
  }

  // Pass 6: Fuzzy Match - Edited Files (non-consuming)
  for (const mediaFilePath of unlinkedEditedMedia) {
    const entry = manifest.get(mediaFilePath);
    const nonEditedPath = getNonEditedPath(mediaFilePath);
    const nonEditedPrefix = getPathPrefix(nonEditedPath);

    for (const metadataKey of unmatchedMetadata) {
      const metadataPrefix = getPathPrefix(metadataKey);
      const isMatch =
        metadataKey.startsWith(nonEditedPrefix) || nonEditedPath.startsWith(metadataPrefix);

      if (isMatch) {
        entry.jsonPath = metadataFiles.get(metadataKey);
        unlinkedEditedMedia.delete(mediaFilePath);
        // DO NOT consume metadata
        break;
      }
    }
  }

  // Pass 7: Fuzzy Match - Original Files (consuming)
  for (const mediaFilePath of unlinkedOriginalMedia) {
    const entry = manifest.get(mediaFilePath);
    const mediaPrefix = getPathPrefix(mediaFilePath);

    for (const metadataKey of new Set(unmatchedMetadata)) {
      const metadataPrefix = getPathPrefix(metadataKey);
      const isMatch =
        metadataKey.startsWith(mediaPrefix) || mediaFilePath.startsWith(metadataPrefix);

      if (isMatch) {
        entry.jsonPath = metadataFiles.get(metadataKey);
        unmatchedMetadata.delete(metadataKey); // Consume the key
        unlinkedOriginalMedia.delete(mediaFilePath);
        break;
      }
    }
  }

  return Array.from(manifest.values());
}

export function normalizeMetadataName(fileName) {
  if (!fileName) {
    return fileName;
  }

  const segments = fileName.split(".");
  if (segments.length === 0) {
    return fileName;
  }

  const extension = segments.pop();
  if (extension.toLowerCase() !== "json") {
    return fileName;
  }

  if (segments.length > 1) {
    const supplementalMarker = segments.pop();
    if (supplementalMarker) {
      const match = supplementalMarker.match(/\(\d+\)/);

      if (match && match[0]) {
        const base = segments.shift();
        const duplicateMarker = match[0];

        segments.unshift(`${base}${duplicateMarker}`);
      }
    }

    return segments.join(".");
  } else {
    return segments[0];
  }
}

export function dropExtension(name) {
  const segments = name.split(".");

  if (segments.length > 1) {
    segments.pop();
    return segments.join(".");
  }

  return name;
}
