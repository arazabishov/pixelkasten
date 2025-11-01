import { stat, readdir } from "fs/promises";
import { extensions } from "./fs.js";
import { join, extname } from "path";
import { createHash } from "crypto";
import { createReadStream } from "fs";

export async function workspace(path, options) {
  const stats = await stat(path);
  if (!stats.isDirectory()) {
    console.error(`The path provided is not a directory: ${path}`);
    return undefined;
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

  // Walk through entries and categorize them into buckets
  for (const entry of entries) {
    const name = entry.name;
    const extl = extname(name).toLowerCase();

    if (entry.isDirectory()) {
      const path = join(entry.path, name);
      directories.set(path, entry);

      if (options.verbose) {
        console.info(`Encoutered a directory: ${path}.`);
      }
    } else if (entry.isFile()) {
      if (name === "metadata.json") {
        const path = join(entry.path, name);
        albumMetadataFiles.set(path, entry);

        if (options.verbose) {
          console.info(`Encountered an album metadata file: ${path}`);
        }
      } else if (extl === ".json") {
        const path = join(entry.path, normalizeMetadataName(name));
        mediaMetadataFiles.set(path, entry);

        if (options.verbose) {
          console.info(`Encountered a media metadata file: ${path}`);
        }
      } else if (extensions.images.includes(extl) || extensions.videos.includes(extl)) {
        const path = join(entry.path, name);
        const sha256 = await calculateFileSha256(path);

        mediaFiles.set(path, { entry, sha256 });

        if (options.verbose) {
          console.info(`Encountered a media file: ${path}`);
        }
      } else {
        const path = join(entry.path, name);
        unsupportedEntries.set(path, entry);

        if (options.verbose) {
          console.warn(`Encountered unsupported file: type=${extl}, path=${path}`);
        }
      }
    } else {
      const path = join(entry.path, name);
      unsupportedEntries.set(path, entry);

      if (options.verbose) {
        console.info(`Encountered unsupported file system entry: ${path}`);
      }
    }
  }

  return {
    entries: entries.length,
    unsupportedEntries: unsupportedEntries,
    directories: directories,
    albums: albumMetadataFiles,
    media: connect(mediaFiles, mediaMetadataFiles, options),
  };
}

export function connect(mediaFiles, mediaMetadataFiles, options) {
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

    for (const [metadataFilePath, metadataFile] of mediaMetadataFilesUnmatched) {
      if (metadataFilePath.startsWith(prefix)) {
        media.set(mediaFilePath, {
          media: mediaFile,
          metadata: metadataFile,
        });

        mediaFilesUnmatched.delete(mediaFilePath);
        mediaMetadataFilesUnmatched.delete(metadataFilePath);

        if (options.verbose) {
          console.info("Matched an orphan media file to a metadata file 🎉!");
          console.info(`  - file:     ${join(mediaFile.entry.path, mediaFile.entry.name)}`);
          console.info(`  - metadata: ${join(metadataFile.path, metadataFile.name)}`);
        }
        break;
      }
    }
  }

  // Iteration 3: link unmatched metadata files
  for (const [metadataFilePath, metadataFile] of new Map(mediaMetadataFilesUnmatched)) {
    // If there was no exact match, we can try to do a prefix search
    const nameWithoutExt = dropExtension(metadataFile.name);
    const prefix = join(metadataFile.path, nameWithoutExt);

    for (const [mediaFilePath, mediaFile] of mediaFilesUnmatched) {
      if (mediaFilePath.startsWith(prefix)) {
        // We use mediaFilePath as a key here since the key always
        // has to point at media file, not metadata one
        media.set(mediaFilePath, {
          media: mediaFile,
          metadata: metadataFile,
        });
        mediaFilesUnmatched.delete(mediaFilePath);
        mediaMetadataFilesUnmatched.delete(metadataFilePath);

        if (options.verbose) {
          console.info("Matched an orphan metadata file to a media file 🎉!");
          console.info(`  - file:     ${join(mediaFile.entry.path, mediaFile.entry.name)}`);
          console.info(`  - metadata: ${join(metadataFile.path, metadataFile.name)}`);
        }
        break;
      }
    }
  }

  // Iteration 4: place media files that had no metadata into media map
  for (const [mediaFilePath, mediaFile] of new Map(mediaFilesUnmatched)) {
    if (mediaMetadataFiles.has(mediaFilePath)) {
      console.error(`Encountered a conflict at the following path: ${mediaFilePath}`);
    } else {
      media.set(mediaFilePath, {
        media: mediaFile,
      });
    }
  }

  // Ensure that we have no metadata files left
  if (mediaMetadataFilesUnmatched.size !== 0) {
    console.error("Unmatched metadata files left!");
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
