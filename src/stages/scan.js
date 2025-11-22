import cliProgress from "cli-progress";
import { readdir, stat } from "fs/promises";
import { extname, join } from "path";
import { allKnownMediaExtensions } from "../handlers/index.js";
import { canShowProgress } from "../logger.js";

export async function scan(sourcePath) {
  // Let's ensure that sourcePath exists and it is a directory.
  validatePath(sourcePath);

  // This is the object returned by the `scan` stage.
  const stats = {
    filesMedia: [],
    filesMetadata: [],
    filesMetadataAlbums: [],
    filesOtherIgnored: [],
    filesTotal: 0,
  };

  // An exhaustive list of files and directories on disk.
  const dirents = await readdir(sourcePath, { withFileTypes: true, recursive: true });

  // Create progress bar (only if not in verbose mode)
  const progressBar = canShowProgress()
    ? new cliProgress.SingleBar(
        {
          format: "⧗ Scanning files |{bar}| {percentage}% | {value}/{total} entries",
          hideCursor: true,
        },
        cliProgress.Presets.shades_classic
      )
    : null;

  if (canShowProgress()) {
    progressBar.start(dirents.length, 0);
  }

  // Walk through entries and categorize them into buckets.
  for (let index = 0; index < dirents.length; index++) {
    const dirent = dirents[index];

    // Update the progress here to account for the 'continue' below.
    if (canShowProgress()) {
      progressBar.update(index + 1);
    }

    // We only care about files. Skip directories, symlinks, etc.
    if (!dirent.isFile()) {
      continue;
    }

    // We need to keep track of the total number of files for accounting later.
    stats.filesTotal++;

    // Extract name and extension (in lowercase)
    const name = dirent.name;
    const path = join(dirent.path, name);
    const extl = extname(name).toLowerCase();

    if (name === "metadata.json") {
      // Collecting album metadata files.
      stats.filesMetadataAlbums.push(path);
    } else if (extl === ".json") {
      // Collecting .json sidecar files.
      stats.filesMetadata.push(path);
    } else if (allKnownMediaExtensions.has(extl)) {
      // Collecting *all* media files.
      stats.filesMedia.push(path);
    } else {
      // Collecting unsupported files for "accounting".
      stats.filesOtherIgnored.push(path);
    }
  }

  if (canShowProgress()) {
    progressBar.stop();
  }

  checkInvariants(stats);

  return stats;
}

async function validatePath(sourcePath) {
  const stats = await stat(sourcePath).catch(() => {
    throw new Error(`Path does not exist or is unreadable: ${sourcePath}`);
  });

  if (!stats.isDirectory()) {
    throw new Error(`Path provided is not a directory: ${sourcePath}`);
  }
}

function checkInvariants(stats) {
  const { filesMedia, filesMetadata, filesMetadataAlbums, filesOtherIgnored, filesTotal } = stats;

  const filesCollected =
    filesMedia.length +
    filesMetadata.length +
    filesMetadataAlbums.length +
    filesOtherIgnored.length;

  if (filesCollected !== filesTotal) {
    throw new Error(`File count mismatch: collected ${filesCollected}, expected ${filesTotal}`);
  }
}
