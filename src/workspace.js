import { stat, readdir } from "fs/promises";
import { extensions } from "./fs.js";
import { join, extname } from "path";
import { createHash } from "crypto";
import { createReadStream } from "fs";
import { consola } from "consola";
import cliProgress from "cli-progress";
import { canShowProgress } from "./logging.js";

export async function workspace(path) {
  const stats = await stat(path);
  if (!stats.isDirectory()) {
    consola.fail(`The path provided is not a directory: ${path}`);
    process.exit(1);
  }

  const entries = await readdir(path, {
    withFileTypes: true,
    recursive: true,
  });

  const mediaFiles = new Map();
  const mediaMetadataFiles = new Map();
  const albumMetadataFiles = new Map();
  const unsupportedEntries = new Map();
  const directories = new Map();

  // Create progress bar (only if not in verbose mode)
  const progressBar = canShowProgress()
    ? new cliProgress.SingleBar(
        {
          format: "⧗ Phase 1: scanning files |{bar}| {percentage}% | {value}/{total} entries",
          barCompleteChar: "\u2588",
          barIncompleteChar: "\u2591",
          hideCursor: true,
        },
        cliProgress.Presets.shades_classic
      )
    : null;

  if (canShowProgress()) {
    progressBar.start(entries.length, 0);
  }

  // Walk through entries and categorize them into buckets
  for (let index = 0; index < entries.length; index++) {
    const entry = entries[index];

    // Extract name and extension (in lowercase)
    const name = entry.name;
    const extl = extname(name).toLowerCase();

    if (entry.isDirectory()) {
      const path = join(entry.path, name);
      directories.set(path, entry);

      consola.debug(`Encoutered a directory: ${path}.`);
    } else if (entry.isFile()) {
      if (name === "metadata.json") {
        const path = join(entry.path, name);
        albumMetadataFiles.set(path, entry);

        consola.debug(`Encountered an album metadata file: ${path}`);
      } else if (extl === ".json") {
        const path = join(entry.path, normalizeMetadataName(name));
        mediaMetadataFiles.set(path, entry);

        consola.debug(`Encountered a media metadata file: ${path}`);
      } else if (extensions.images.includes(extl) || extensions.videos.includes(extl)) {
        const path = join(entry.path, name);
        const sha256 = await calculateFileSha256(path);

        mediaFiles.set(path, { entry, sha256 });

        consola.debug(`Encountered a media file: ${path}`);
      } else {
        const path = join(entry.path, name);
        unsupportedEntries.set(path, entry);

        consola.debug(`Encountered unsupported file: type=${extl}, path=${path}`);
      }
    } else {
      const path = join(entry.path, name);
      unsupportedEntries.set(path, entry);

      consola.debug(`Encountered unsupported file system entry: ${path}`);
    }

    if (canShowProgress()) {
      progressBar.update(index + 1);
    }
  }

  if (canShowProgress()) {
    progressBar.stop();
  }

  const project = {
    entries: entries.length,
    unsupportedEntries: unsupportedEntries,
    directories: directories,
    albums: albumMetadataFiles,
    media: connect(mediaFiles, mediaMetadataFiles),
  };

  if (check(project)) {
    consola.success(`Scanned ${entries.length} entries!`);
    return project;
  } else {
    process.exit(1);
  }
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

export function calculateFileSha256(path) {
  return new Promise((resolve, reject) => {
    const hash = createHash("sha256");
    const stream = createReadStream(path);

    stream.on("error", (err) => {
      reject(err);
    });

    stream.on("data", (chunk) => {
      hash.update(chunk);
    });

    stream.on("end", () => {
      resolve(hash.digest("hex"));
    });
  });
}

export function dropExtension(name) {
  const segments = name.split(".");

  if (segments.length > 1) {
    segments.pop();
    return segments.join(".");
  }

  return name;
}

export function check({ entries, media, albums, directories, unsupportedEntries }) {
  const unlinkedMediaFiles = [];
  const unlinkedMetadataFiles = [];
  const mediaFiles = [];

  for (const [mediaFilePath, mediaFile] of media) {
    if (!mediaFile.metadata && !mediaFile.media) {
      // Encountered an empty entry.
      consola.fail(`Encountered an empty entry ❌!`, mediaFilePath);

      // Fail early!
      process.exit(1);
    } else if (!mediaFile.metadata) {
      // A case when a media file has no metadata. Video files often don't have associated sidecar/metadata files.
      unlinkedMediaFiles.push(mediaFile);
    } else if (!mediaFile.media) {
      // This is an edge case when media file is not present.
      unlinkedMetadataFiles.push(mediaFile);
    } else {
      // Media file is linked correctly.
      mediaFiles.push(mediaFile);
    }
  }

  if (unlinkedMetadataFiles.length > 0) {
    // The program should not encounter this case.
    consola.fail(`Encountered orphan metadata files ❌!`, unlinkedMetadataFiles);

    // If it does, fail early.
    process.exit(1);
  }

  // The reason why mediaFiles is multiplied by two is that one entry corresponds to two files: media and metadata files.
  const totalMediaFiles = mediaFiles.length * 2 + unlinkedMediaFiles.length;
  const totalFiles = totalMediaFiles + unsupportedEntries.size + directories.size + albums.size;

  if (entries !== totalFiles) {
    // The total number of files the script encountered, including directories,
    // has to match what was initially observed on the file system.
    consola.fail(`Failed the integrity check ❌!`);
    consola.fail(`Total entries=${entries}, but processed=${totalFiles}`);

    process.exit(1);
  }

  return true;
}
