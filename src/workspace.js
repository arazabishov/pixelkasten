import { stat, readdir } from "fs/promises";

export async function workspace(path, options) {
  const isDirectory = await isDir(path, options);

  if (isDirectory) {
    const entries = await readdir(path, {
      withFileTypes: true,
    });

    entries.map((entry) => {
      console.log(entry.name);
    });
  }
}

async function isDir(path, options) {
  try {
    const information = await stat(path);
    return information.isDirectory();
  } catch (err) {
    if (options.verbose) {
      console.error(`Error checking directory: ${path}`);
      console.error(err);
    }

    return false;
  }
}
