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
