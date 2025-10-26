import { stat, readdir } from "fs/promises";
import { getFileType, supportedExtensions } from "./fs.js";
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

  entries.forEach((entry) => {
    const name = entry.name.toLowerCase();

    if (entry.isFile()) {
      const ext = extname(name);

      if (name.toLowerCase() === "metadata.json") {
        if (!workspace.directories.has(entry.path)) {
          workspace.directories.set(entry.path, {
            metadata: entry,
          });
        }
      } else if (
        supportedExtensions.images.includes(ext) ||
        supportedExtensions.videos.includes(ext)
      ) {
        if (workspace.media.has(name)) {
          workspace.media.get(name).file = entry;
        } else {
          workspace.media.set(name, {
            file: entry,
            metadata: undefined,
          });
        }
      } else if (ext === ".json") {
        const normalizedName = normalizeMetadataName(name);

        if (workspace.media.has(normalizedName)) {
          workspace.media.get(normalizedName).metadata = entry;
        } else {
          workspace.media.set(normalizedName, {
            file: undefined,
            metadata: entry,
          });
        }
      } else if (supportedExtensions.os.includes(ext)) {
        // We can simply ignore this type of files
      } else {
        console.warn(`Encountered unsupported file type: name=${name}, ext=${ext}`);
      }
    } else if (entry.isDirectory()) {
      // We can simply skip directories for now
    } else {
      console.warn(`Encountered unsupported file system entry: ${name}`);
    }
  });

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
}
