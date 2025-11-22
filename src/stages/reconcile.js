import { supportedExtensions, handlers } from "../handlers/index.js";
import { execa } from "execa";

export async function reconcile(manifest, sourcePath) {
  // TODO:
  await readExifMetadata(sourcePath);
}

async function readExifMetadata(sourcePath) {
  const extensions = [...supportedExtensions].flatMap((ext) => ["-ext", ext]);
  const readTags = [...new Set(handlers.flatMap((h) => h.readTags))];
  const args = [
    "-api",
    "largefilesupport=1",
    "-json",
    "-n",
    "-r",
    "-File:FileTypeExtension",
    ...readTags,
    ...extensions,
    sourcePath,
  ];

  console.log(args);

  try {
    const { stdout } = await execa("exiftool", args);

    const metadata = JSON.parse(stdout);
    const metadataMap = new Map();

    for (const entry of metadata) {
      metadataMap.set(entry.SourceFile, entry);
    }

    return metadataMap;
  } catch (error) {
    console.error(`Failed to read EXIF metadata from ${sourcePath}:`, error);

    // TODO: consider switching to throwing errors instead of explicitly exiting the process
    process.exit(1);
  }
}
