import { stat, readdir } from "fs/promises";
import { getFileType } from "./fs.js";
import { join } from "path";

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

  const files = entries.map((entry) => ({
    path: join(entry.path, entry.name),
    type: entry.isDirectory() ? "directory" : getFileType(entry.name),
  }));

  return {
    entriesCount: entries.length,
    files: files,
  };
}
