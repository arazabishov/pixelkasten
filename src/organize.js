import { join } from "path";
import { consola } from "consola";

export function deduplicate(workspace) {
  const { media: mediaEntries, albums: albumMetadataFiles } = workspace;

  const duplicates = new Map();
  const library = new Map();

  // Process albums first, and fold them into output directory
  for (const albumMetadataFile of albumMetadataFiles.values()) {
    consola.debug(`Album path: ${albumMetadataFile.path}`);

    if (library.has(albumMetadataFile.path)) {
      consola.error(`Encountered duplicate album directory: ${albumMetadataFile}`);
    } else {
      library.set(albumMetadataFile.path, []);
    }
  }

  // Iteration 1: we need to process images that belong to albums first
  const mediaFilesCopy = new Map(mediaEntries);
  for (const [mediaEntryKey, mediaEntry] of mediaEntries) {
    const { entry, sha256 } = mediaEntry.media;

    if (library.has(entry.path)) {
      consola.debug(`Found media=${entry.name} that belongs to an album=${entry.path}`);

      const album = library.get(entry.path);
      if (duplicates.has(sha256)) {
        const duplicate = duplicates.get(sha256);
        duplicate.push(mediaEntry);

        // Ensure that we do not process the same entry twice
        mediaFilesCopy.delete(mediaEntryKey);

        consola.debug(`Encountered duplicate: ${join(entry.path, entry.name)}`);
      } else {
        // We need to keep track of files that we have encountered
        duplicates.set(sha256, []);

        // Ensure that we do not process the same entry twice
        mediaFilesCopy.delete(mediaEntryKey);

        // Push the entry to an album
        album.push(mediaEntry);
      }
    }
  }

  // Iteration 2: process remaining files outside of albums
  for (const [mediaEntryKey, mediaEntry] of mediaFilesCopy) {
    const { entry, sha256 } = mediaEntry.media;
    const path = join(entry.path, entry.name);

    if (duplicates.has(sha256)) {
      const duplicate = duplicates.get(sha256);
      duplicate.push(mediaEntry);

      consola.debug(`Encountered duplicate: ${path}`);
    } else {
      // We need to keep track of files that we have encountered
      duplicates.set(sha256, []);

      if (library.has(mediaEntryKey)) {
        // We should not run into this scenario, because duplicates
        // should have been caught by the sha check
        consola.error(`Encountered unexpected duplicate: ${path}`);
      } else {
        library.set(mediaEntryKey, mediaEntry);
      }
    }
  }

  return {
    library,
    duplicates,
  };
}
