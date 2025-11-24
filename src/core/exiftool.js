import { execa } from "execa";

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
