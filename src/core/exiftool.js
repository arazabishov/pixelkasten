import { execa } from "execa";

/**
 * Checks whether exiftool is available on the system PATH.
 *
 * @returns {Promise<boolean>}
 */
export async function isAvailable() {
  try {
    await execa("exiftool", ["-ver"]);
    return true;
  } catch {
    return false;
  }
}

/**
 * Reads metadata from files using exiftool.
 *
 * @param {string[]} filePaths - Paths to the files to read metadata from
 * @param {string[]} tags - Metadata tags to extract (e.g., ["EXIF:DateTimeOriginal"])
 * @returns {Promise<Map<string, object>>} Map of file paths to their metadata
 */
export async function readMetadata(filePaths, tags = []) {
  const args = [
    "-api",
    // Enable support for files >2GB
    "largefilesupport=1",
    // Output metadata as JSON
    "-json",
    // Print values as numbers/dates instead of human-readable format
    "-n",
    // Print group names with each tag (e.g., "EXIF:DateTimeOriginal")
    "-G",
    // Increase processing speed by not parsing all metadata
    "-fast",
    // Specify which metadata tags to extract
    ...tags.map((t) => `-${t}`),
    // Read file list from stdin
    "-@",
    // Read from stdin
    "-",
  ];

  try {
    const { stdout } = await execa("exiftool", args, {
      // Pipe filenames to stdin.
      input: filePaths.join("\n"),

      // 128MB buffer for safety.
      maxBuffer: 128 * 1024 * 1024,
    });

    const metadata = JSON.parse(stdout);
    const metadataMap = new Map();
    for (const item of metadata) {
      metadataMap.set(item.SourceFile, item);
    }

    return metadataMap;
  } catch (error) {
    throw new Error(`Failed to read metadata using exiftool ${error.message}`);
  }
}

/**
 * Writes metadata tags to a single file using exiftool.
 *
 * @param {string} filePath - Path to the file to write metadata to
 * @param {string[]} tags - Tags to write (e.g., ["DateTimeOriginal=2023:01:01 12:00:00"])
 * @returns {Promise<void>}
 */
export async function writeMetadata(filePath, tags) {
  if (tags.length === 0) {
    return;
  }

  const args = [
    "-api",
    // Enable support for files >2GB
    "largefilesupport=1",
    // Don't create backup files
    "-overwrite_original",
    // Tags to write
    ...tags.map((t) => `-${t}`),
    // File to write to
    filePath,
  ];

  try {
    await execa("exiftool", args);
  } catch (error) {
    throw new Error(`Failed to write metadata using exiftool: ${error.message}`);
  }
}
