import { stat, readdir } from "fs/promises";
import { extensions } from "./fs.js";
import { join, extname } from "path";

export async function workspace(path, options) {
  try {
    const stats = await stat(path);
    if (!stats.isDirectory()) {
      console.error(`The path provided is not a directory: ${path}`);
      return;
    }
  } catch (err) {
    console.error(`Cannot access path: ${path}`);
    if (options.verbose) {
      console.error(err);
    }
    return;
  }

  const entries = await readdir(path, {
    withFileTypes: true,
    recursive: true,
  });

  const workspace = {
    entries: entries.length,
    directories: new Map(),
    media: new Map(),
  };

  // Iteration 1: try to map metadata to media files assuming that their names match entirely
  entries.forEach((entry) => {
    const name = entry.name;

    if (entry.isFile()) {
      const ext = extname(name).toLowerCase();

      if (name.toLowerCase() === "metadata.json") {
        if (!workspace.directories.has(entry.path)) {
          workspace.directories.set(entry.path, {
            metadata: entry,
          });
        }
      } else if (extensions.images.includes(ext) || extensions.videos.includes(ext)) {
        const path = join(entry.path, name);

        if (workspace.media.has(path)) {
          workspace.media.get(path).file = entry;
        } else {
          workspace.media.set(path, {
            file: entry,
            metadata: undefined,
          });
        }
      } else if (ext === ".json") {
        const normalizedName = normalizeMetadataName(name);
        const path = join(entry.path, normalizedName);

        if (workspace.media.has(path)) {
          workspace.media.get(path).metadata = entry;
        } else {
          workspace.media.set(path, {
            file: undefined,
            metadata: entry,
          });
        }
      } else if (extensions.os.includes(ext) || extensions.os.includes(name.toLowerCase())) {
        // We can simply ignore this type of files
      } else if (extensions.unsupported.includes(ext)) {
        if (options.verbose) {
          console.warn(`Skipping unsupported file type: name=${name}, ext=${ext}`);
        }
      } else {
        console.warn(`Encountered unsupported file type: name=${name}, ext=${ext}`);
      }
    } else if (entry.isDirectory()) {
      // We can simply skip directories for now
    } else {
      console.warn(`Encountered unsupported file system entry: ${name}`);
    }
  });

  // Iteration 2: sometimes Google cuts the file name to fit some arbitrary constraint. For example:
  //  - CB6054D8-E1F4-419D-B5B5-4C74D81D6625-98855-000.json
  //  - CB6054D8-E1F4-419D-B5B5-4C74D81D6625-98855-0000.mov
  // Both file names are exactly 51 characters long. However, without their respective extensions, the names won't match.

  for (const [key, value] of new Map(workspace.media)) {
    if (value.file == undefined) {
      if (options.verbose) {
        const metadataFilePath = join(value.metadata.path, value.metadata.name);
        console.warn(`\nEncountered an orphaned metadata file: ${metadataFilePath}.`);
      }

      const segments = value.metadata.name.split(".");
      if (segments.length > 1) {
        const extension = segments.pop();
        if (extension !== "json") {
          // We should drop the extension only if it is .json.
          segments.push(extension);
        }
      }
      const name = segments.join(".");
      const mediaFileCandidates = [];

      for (const [mediaKey, mediaValue] of workspace.media) {
        if (
          mediaKey.includes(name) &&
          mediaValue.file &&
          mediaValue.file.path === value.metadata.path &&
          mediaValue.metadata === undefined
        ) {
          mediaFileCandidates.push(mediaValue);
        }
      }

      if (mediaFileCandidates.length > 1) {
        console.error("Matched the metadata file to more than one media file.");
        process.exit(1);
      } else if (mediaFileCandidates.length === 1) {
        // Grab the media file and assign it a metadata file
        const mediaFile = mediaFileCandidates[0];
        mediaFile.metadata = value.metadata;

        // Remove the orphan metadata file from the original workspace file
        workspace.media.delete(key);

        if (options.verbose) {
          console.info("Matched an orphan metadata file to a media file 🎉!");
          console.info(`  - metadata: ${join(mediaFile.metadata.path, mediaFile.metadata.name)}`);
          console.info(`  - file:     ${join(mediaFile.file.path, mediaFile.file.name)}`);
        }
      } else {
        console.error("Failed to find matching media file.");
        process.exit(1);
      }
    }
  }

  return workspace;
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
