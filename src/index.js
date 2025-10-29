#!/usr/bin/env node

import { Command } from "commander";
import { workspace } from "./workspace.js";
import { extensions } from "./fs.js";
import { extname } from "path";

const program = new Command();

program
  .name("pixelkasten")
  .description("A script that helps you organize and manage your photo archive")
  .version("0.0.1");

program
  .option("-s, --source <path>", "source directory containing takout from Google Photos")
  .option("-d, --destination <path>", "destination directory for organized photos")
  .option("-v, --verbose", "enable verbose output")
  .option("--dry-run", "preview changes without modifying files");

program.parse(process.argv);

const options = program.opts();

// Display parsed options
if (options.verbose) {
  console.log("Pixelkasten - Photo Archive Organizer");
  console.log("=====================================");
  console.log("Options:", options);
}

if (options.source && options.destination) {
  console.log(`Organizing photos from: ${options.source}`);
  console.log(`Destination: ${options.destination}`);

  if (options.dryRun) {
    console.log("(Dry run mode - no files will be modified)");
  }

  const library = await workspace(options.source, {
    verbose: options.verbose,
    dryRun: options.dryRun,
  });

  const filesWithoutMetadata = {
    images: 0,
    videos: 0,
    others: 0,
  };

  const metadataWithoutFiles = [];
  const duplicates = new Map();

  for (const [mediaFilePath, mediaFile] of library.media) {
    if (!mediaFile.media) {
      metadataWithoutFiles.push({ key: mediaFilePath, value: mediaFile.metadata });
    } else if (!mediaFile.metadata) {
      const { entry, sha256 } = mediaFile.media;
      const ext = extname(entry.name).toLowerCase();

      if (extensions.images.includes(ext)) {
        filesWithoutMetadata.images += 1;
      } else if (extensions.videos.includes(ext)) {
        filesWithoutMetadata.videos += 1;
      } else {
        filesWithoutMetadata.others += 1;
      }

      if (duplicates.has(sha256)) {
        const count = duplicates.get(sha256);
        duplicates.set(sha256, count + 1);
      } else {
        duplicates.set(sha256, 0);
      }
    }
  }

  // Count duplicates based on hash values of files SHA256
  const duplicatesCount = Array.from(duplicates.values()).reduce((sum, count) => sum + count, 0);

  console.log(metadataWithoutFiles);
  console.log(filesWithoutMetadata);
  console.log(duplicatesCount);
} else {
  console.log("Please specify both source and destination directories.");
  console.log('Run "pixelkasten --help" for usage information.');
}
