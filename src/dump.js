import { mkdir, copyFile } from "fs/promises";
import { basename, join } from "path";
import { normalizeMetadataName } from "./workspace.js";

export async function dump(library, destination) {
  // Ensure that directory exists before writing anything to it
  await mkdir(destination, { recursive: true });

  for (const [entryPath, entry] of library) {
    if (entry.items && Array.isArray(entry.items)) {
      // This is an album
      const albumName = basename(entryPath);
      const albumPath = join(destination, albumName);

      await mkdir(albumPath, { recursive: true });

      for (const mediaEntry of entry.items) {
        await copyEntry(mediaEntry, albumPath);
      }
    } else {
      // This is a media file
      await copyEntry(entry, destination);
    }
  }
}

async function copyEntry(mediaEntry, directory) {
  const { media, metadata } = mediaEntry;

  const mediaPathSource = join(media.entry.path, media.entry.name);
  const mediaPathDestination = join(directory, media.entry.name);

  await copyFile(mediaPathSource, mediaPathDestination);

  if (metadata) {
    // TODO: this is temporary code. Once we start embedding metadata
    // into image's exif, we will not need to copy .json files over.
    const normalizedMetadataName = `${normalizeMetadataName(metadata.name)}.json`;

    const metadataPathSource = join(metadata.path, metadata.name);
    const metadataPathDestination = join(directory, normalizedMetadataName);

    await copyFile(metadataPathSource, metadataPathDestination);
  }
}
