#!/usr/bin/env node

import { Command } from "commander";
import { workspace } from "./workspace.js";

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

  const { entriesCount, files } = await workspace(options.source, {
    verbose: options.verbose,
    dryRun: options.dryRun,
  });

  const stats = {
    unsupported: 0,
    directories: 0,
    metadata: 0,
    images: 0,
    videos: 0,
  };

  files.forEach((item) => {
    if (item.type === "image") {
      stats.images += 1;
    } else if (item.type === "video") {
      stats.videos += 1;
    } else if (item.type === "metadata") {
      stats.metadata += 1;
    } else if (item.type === "directory") {
      stats.directories += 1;
    } else {
      stats.unsupported += 1;

      console.log("Unsupported file type:", item.path);
    }
  });

  console.log("All stats", stats);
  console.log(
    "All media files",
    stats.images + stats.videos,
    " all metadata files ",
    stats.metadata
  );
  console.log(
    "Total files",
    stats.images + stats.videos + stats.metadata + stats.unsupported + stats.directories,
    " all entries ",
    entriesCount
  );
} else {
  console.log("Please specify both source and destination directories.");
  console.log('Run "pixelkasten --help" for usage information.');
}
