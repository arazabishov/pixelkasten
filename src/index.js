#!/usr/bin/env node

import { Command } from "commander";
import { consola } from "consola";
import { workspace } from "./workspace.js";
import { extensions } from "./fs.js";
import { extname } from "path";
import { deduplicate } from "./organize.js";

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
  consola.log("Pixelkasten - Photo Archive Organizer");
  consola.log("=====================================");
  consola.log("Options:", options);
}

if (options.source && options.destination) {
  consola.log(`Organizing photos from: ${options.source}`);
  consola.log(`Destination: ${options.destination}`);

  if (options.dryRun) {
    consola.log("(Dry run mode - no files will be modified)");
  }

  const project = await workspace(options.source, options);

  const filesWithoutMetadata = {
    images: 0,
    videos: 0,
    others: 0,
  };

  const metadataWithoutFiles = [];
  const duplicatesOne = new Map();

  for (const [mediaFilePath, mediaFile] of project.media) {
    if (!mediaFile.media) {
      metadataWithoutFiles.push({ key: mediaFilePath, value: mediaFile.metadata });
    } else {
      const { entry, sha256 } = mediaFile.media;
      const ext = extname(entry.name).toLowerCase();

      if (!mediaFile.metadata) {
        if (extensions.images.includes(ext)) {
          filesWithoutMetadata.images += 1;
        } else if (extensions.videos.includes(ext)) {
          filesWithoutMetadata.videos += 1;
        } else {
          filesWithoutMetadata.others += 1;
        }
      }

      if (duplicatesOne.has(sha256)) {
        const count = duplicatesOne.get(sha256);
        duplicatesOne.set(sha256, count + 1);
      } else {
        duplicatesOne.set(sha256, 0);
      }
    }
  }

  // Count duplicates based on hash values of files SHA256
  const duplicatesCountOne = Array.from(duplicatesOne.values()).reduce(
    (sum, count) => sum + count,
    0
  );

  consola.log(metadataWithoutFiles);
  consola.log(filesWithoutMetadata);
  consola.log(duplicatesCountOne);

  const { duplicates } = deduplicate(project, options);

  // Count duplicates based on hash values of files SHA256
  const duplicatesCount = Array.from(duplicates.values()).reduce(
    (sum, duplicate) => sum + duplicate.length,
    0
  );

  // consola.log("Keys: ", library.keys());
  consola.log(duplicatesCount);
} else {
  consola.log("Please specify both source and destination directories.");
  consola.log('Run "pixelkasten --help" for usage information.');
}
