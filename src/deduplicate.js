import { join } from "path";
import { consola } from "consola";
import cliProgress from "cli-progress";
import { canShowProgress } from "./utils/logger.js";

export function deduplicate(workspace) {
  const { media: mediaEntries, albums: albumMetadataFiles } = workspace;

  const duplicates = new Map();
  const library = new Map();

  // Process albums first, and fold them into output directory
  for (const albumMetadataFile of albumMetadataFiles.values()) {
    consola.debug(`Album path: ${albumMetadataFile.path}`);

    if (library.has(albumMetadataFile.path)) {
      consola.fail(`Encountered duplicate album directory: ${albumMetadataFile}`);

      // Fail early!
      process.exit(1);
    } else {
      library.set(albumMetadataFile.path, {
        metadata: albumMetadataFile,
        items: [],
      });
    }
  }

  // Create progress bar for processing media entries
  const progressBar = canShowProgress()
    ? new cliProgress.SingleBar(
        {
          format: "⧗ Phase 2: deduplicating |{bar}| {percentage}% | {value}/{total} media files",
          barCompleteChar: "\u2588",
          barIncompleteChar: "\u2591",
          hideCursor: true,
        },
        cliProgress.Presets.shades_classic
      )
    : null;

  if (canShowProgress()) {
    progressBar.start(mediaEntries.size, 0);
  }

  // Keep track of progress made for progress bar
  const mediaEntriesProcessed = [];

  // Iteration 1: we need to process images that belong to albums first
  const mediaEntriesCopy = new Map(mediaEntries);
  for (const [mediaEntryKey, mediaEntry] of mediaEntries) {
    const { entry, sha256 } = mediaEntry.media;

    if (library.has(entry.path)) {
      consola.debug(`Found media=${entry.name} that belongs to an album=${entry.path}`);

      const album = library.get(entry.path);
      if (duplicates.has(sha256)) {
        const duplicate = duplicates.get(sha256);
        duplicate.push(mediaEntry);

        // Ensure that we do not process the same entry twice
        mediaEntriesCopy.delete(mediaEntryKey);

        consola.debug(`Encountered duplicate: ${join(entry.path, entry.name)}`);
      } else {
        // We need to keep track of files that we have encountered
        duplicates.set(sha256, []);

        // Ensure that we do not process the same entry twice
        mediaEntriesCopy.delete(mediaEntryKey);

        // Push the entry to an album
        album.items.push(mediaEntry);
      }

      mediaEntriesProcessed.push(mediaEntry);

      if (canShowProgress()) {
        progressBar.update(mediaEntriesProcessed.length);
      }
    }
  }

  // Iteration 2: process remaining files outside of albums
  for (const [mediaEntryKey, mediaEntry] of mediaEntriesCopy) {
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
        consola.fail(`Encountered unexpected duplicate: ${path}`);
      } else {
        library.set(mediaEntryKey, mediaEntry);
      }
    }

    mediaEntriesProcessed.push(mediaEntry);

    if (canShowProgress()) {
      progressBar.update(mediaEntriesProcessed.length);
    }
  }

  if (canShowProgress()) {
    progressBar.stop();
  }

  const { totalMediaFiles, totalDuplicates, totalFiles } = introspect(library, duplicates);

  if (totalFiles !== mediaEntries.size) {
    consola.fail(`After dedupe: expected ${mediaEntries.size} files, found ${totalFiles}`);
    process.exit(1);
  }

  return {
    library: library,
    librarySize: totalMediaFiles,
    duplicates: duplicates,
    duplicatesSize: totalDuplicates,
  };
}

function introspect(library, duplicates) {
  let totalMediaFiles = 0;
  for (const mediaEntry of library.values()) {
    if (mediaEntry.items && Array.isArray(mediaEntry.items)) {
      totalMediaFiles += mediaEntry.items.length;
    } else {
      totalMediaFiles += 1;
    }
  }

  let totalDuplicates = 0;
  for (const duplicate of duplicates.values()) {
    totalDuplicates += duplicate.length;
  }

  return {
    totalMediaFiles: totalMediaFiles,
    totalDuplicates: totalDuplicates,
    totalFiles: totalMediaFiles + totalDuplicates,
  };
}
