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

  const incompleteEntries = {
    images: 0,
    videos: 0,
    others: 0,
  };

  for (const value of library.media.values()) {
    if (!value.metadata) {
      const ext = extname(value.file.name).toLowerCase();
      if (extensions.images.includes(ext)) {
        incompleteEntries.images += 1;
      } else if (extensions.videos.includes(ext)) {
        incompleteEntries.videos += 1;
      } else {
        incompleteEntries.others += 1;
      }
    }
  }

  // console.log(incompleteEntries);
  // console.log(library);
} else {
  console.log("Please specify both source and destination directories.");
  console.log('Run "pixelkasten --help" for usage information.');
}
