import { basename, dirname, join } from "path";

export function link(rawCollections) {
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

      // Once we a metadata file to a media file, we can remove it from
      // a set to reduce search space in the next pass.
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

        // Reduce the problem space further to reduce the cost of next iterations
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

        // Reduce the problem space further to reduce the cost of next iterations
        unmatchedMediaFiles.delete(mediaFilePath);
        unmatchedMetadataFiles.delete(metadataFilePath);

        break;
      }
    }
  }

  // TODO: do we want to perform a full blown search similar to the last
  // two loops above on a file name that lost -edited prefix?

  // Pass 6: match "-edited" files and files that had no metadata.
  for (const mediaFilePath of new Set(unmatchedMediaFiles)) {
    const mediaFileName = basename(mediaFilePath);
    const mediaFileDir = dirname(mediaFilePath);

    // Remove -edited from the full filename, which might appear before any extension
    const nameWithoutEditedSuffix = mediaFileName.replace(/-edited(\.|$)/, "$1");
    const mediaFilePathWithoutEditedSuffix = join(mediaFileDir, nameWithoutEditedSuffix);

    if (metadataFiles.has(mediaFilePathWithoutEditedSuffix)) {
      const metadataFilePath = metadataFiles.get(mediaFilePathWithoutEditedSuffix);

      // We used mediaFilePathWithoutEditedSuffix for look-up of metadata file only.
      // We still use mediaFilePath as a key since the key always has to point at media file.
      const entry = manifest.get(mediaFilePath);
      entry.jsonPath = metadataFilePath;

      // Ensure the entry is deleted to pass through the integrity check at the end.
      unmatchedMetadataFiles.delete(mediaFilePathWithoutEditedSuffix);
    }
  }

  return Array.from(manifest);
}

export function connect(mediaFiles, mediaMetadataFiles) {
  const media = new Map();
  const mediaFilesUnmatched = new Map(mediaFiles);
  const mediaMetadataFilesUnmatched = new Map(mediaMetadataFiles);

  // Iteration 1: link metadata and media files.
  for (const [mediaFilePath, mediaFile] of mediaFiles) {
    if (mediaMetadataFiles.has(mediaFilePath)) {
      // This is a happy case scenario when we have an exact match between metadata and media files
      const metadataFile = mediaMetadataFiles.get(mediaFilePath);
      media.set(mediaFilePath, {
        media: mediaFile,
        metadata: metadataFile,
      });

      // If we matched the metadata file, we can drop it to reduce problem space
      mediaFilesUnmatched.delete(mediaFilePath);
      mediaMetadataFilesUnmatched.delete(mediaFilePath);
    }
  }

  // Iteration 2: link unmatched media files
  for (const [mediaFilePath, mediaFile] of new Map(mediaFilesUnmatched)) {
    // If there was no exact match, we can try to do a prefix search
    const nameWithoutExt = dropExtension(mediaFile.entry.name);
    const prefix = join(mediaFile.entry.path, nameWithoutExt);

    for (const [metadataFilePath, metadataFile] of new Map(mediaMetadataFilesUnmatched)) {
      if (metadataFilePath.startsWith(prefix)) {
        media.set(mediaFilePath, {
          media: mediaFile,
          metadata: metadataFile,
        });

        mediaFilesUnmatched.delete(mediaFilePath);
        mediaMetadataFilesUnmatched.delete(metadataFilePath);

        consola.debug("Matched orphan media file to metadata 🎉");
        consola.debug(`  File:     ${join(mediaFile.entry.path, mediaFile.entry.name)}`);
        consola.debug(`  Metadata: ${join(metadataFile.path, metadataFile.name)}`);
        break;
      }
    }
  }

  // Iteration 3: link unmatched metadata files
  for (const [metadataFilePath, metadataFile] of new Map(mediaMetadataFilesUnmatched)) {
    // If there was no exact match, we can try to do a prefix search
    const nameWithoutExt = dropExtension(metadataFile.name);
    const prefix = join(metadataFile.path, nameWithoutExt);

    for (const [mediaFilePath, mediaFile] of new Map(mediaFilesUnmatched)) {
      if (mediaFilePath.startsWith(prefix)) {
        // We use mediaFilePath as a key here since the key always
        // has to point at media file, not metadata one
        media.set(mediaFilePath, {
          media: mediaFile,
          metadata: metadataFile,
        });
        mediaFilesUnmatched.delete(mediaFilePath);
        mediaMetadataFilesUnmatched.delete(metadataFilePath);

        consola.debug("Matched orphan metadata to media file 🎉");
        consola.debug(`  File:     ${join(mediaFile.entry.path, mediaFile.entry.name)}`);
        consola.debug(`  Metadata: ${join(metadataFile.path, metadataFile.name)}`);
        break;
      }
    }
  }

  // Iteration 4: match "-edited" files and files that had no metadata into media map
  for (const [mediaFilePath, mediaFile] of new Map(mediaFilesUnmatched)) {
    // Remove -edited from the full filename, which might appear before any extension
    const nameWithoutEditedSuffix = mediaFile.entry.name.replace(/-edited(\.|$)/, "$1");
    const mediaFilePathWithoutEditedSuffix = join(mediaFile.entry.path, nameWithoutEditedSuffix);

    if (
      mediaMetadataFiles.has(mediaFilePathWithoutEditedSuffix) ||
      mediaMetadataFilesUnmatched.has(mediaFilePathWithoutEditedSuffix)
    ) {
      const metadataFile = mediaMetadataFiles.get(mediaFilePathWithoutEditedSuffix);

      // We used mediaFilePathWithoutEditedSuffix for look-up of metadata file only. We still use
      // mediaFilePath as a key since the key always has to point at media file
      media.set(mediaFilePath, {
        media: mediaFile,
        metadata: metadataFile,
      });

      // Ensure the entry is deleted to pass through the integrity check at the end.
      mediaMetadataFilesUnmatched.delete(mediaFilePathWithoutEditedSuffix);

      consola.debug("Matched edited media file to metadata file 🎉");
      consola.debug(`  File:     ${join(mediaFile.entry.path, mediaFile.entry.name)}`);
      consola.debug(`  Metadata: ${join(metadataFile.path, metadataFile.name)}`);
    } else if (mediaMetadataFiles.has(mediaFilePath)) {
      consola.fail(`Encountered a conflict at the following path: ${mediaFilePath}`);
    } else {
      media.set(mediaFilePath, {
        media: mediaFile,
      });
    }
  }

  // Ensure that we have no metadata files left
  if (mediaMetadataFilesUnmatched.size !== 0) {
    consola.fail(`${mediaMetadataFilesUnmatched.size} unmatched metadata files remaining!`);
  }

  return media;
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
