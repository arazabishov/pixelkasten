#!/usr/bin/env node

import { Command } from "commander";
import { consola } from "consola";
import { workspace } from "./workspace.js";
import { extensions } from "./fs.js";
import { extname } from "path";
import { deduplicate } from "./deduplicate.js";
import CliTable3 from "cli-table3";
import { transform } from "./transform.js";
import { scan } from "./stages/scan.js";
import { runPipeline } from "./pipeline.js";
import { logger } from "./utils/logger.js";

const program = new Command();

program
  .name("pixelkasten")
  .description("A script that helps you organize and manage your photo archive")
  .version("0.0.1");

program
  .option("-s, --source <path>", "source directory containing takout from Google Photos")
  .option("-d, --destination <path>", "destination directory for organized photos")
  .option("-v, --verbose", "enable verbose output")
  .option("--dry-run", "preview changes without modifying files")
  .option(
    "--prefer <type>",
    "prefer which files to keep when deduplicating: 'album' or 'loose'",
    "album"
  )
  .option("--strict", false)
  .option("--skip-dedupe", "skip deduplication step")
  .option("--no-fuzzy", "disable fuzzy matching for metadata linking");

program.parse(process.argv);

const options = program.opts();

// Validate --prefer option
if (options.prefer && !["album", "loose"].includes(options.prefer)) {
  consola.fail(`Invalid --prefer value: "${options.prefer}". Must be either "album" or "loose".`);
  process.exit(1);
}

// Set log level based on verbose flag
if (options.verbose) {
  // Show debug messages
  consola.level = 4;
  logger.verbose = true;
} else {
  // Default: info, warn, error, success
  consola.level = 3;
}

if (options.source && options.destination) {
  consola.debug(`Organizing photos from: ${options.source}`);
  consola.debug(`Destination: ${options.destination}`);

  if (options.dryRun) {
    consola.warn("Dry run mode - no files will be modified");
  }

  await runPipeline(options);

  // // Phase 1: scan files, calculate hashes, and link metadata
  // const project = await workspace(options.source);

  // // Collect stats for transparency
  // const projectStats = {
  //   images: 0,
  //   imagesWithoutMetadata: 0,
  //   videos: 0,
  //   videosWithoutMetadata: 0,
  //   others: 0,
  // };

  // for (const mediaFile of project.media.values()) {
  //   const { entry } = mediaFile.media;
  //   const ext = extname(entry.name).toLowerCase();

  //   if (extensions.images.includes(ext)) {
  //     projectStats.images += 1;

  //     if (!mediaFile.metadata) {
  //       projectStats.imagesWithoutMetadata += 1;
  //     }
  //   } else if (extensions.videos.includes(ext)) {
  //     projectStats.videos += 1;

  //     if (!mediaFile.metadata) {
  //       projectStats.videosWithoutMetadata += 1;
  //     }
  //   } else {
  //     projectStats.others += 1;
  //   }
  // }

  // const projectStatsTable = new CliTable3({ head: ["Category", "Count"] });
  // projectStatsTable.push(
  //   ["Total media files", project.media.size],
  //   ["Images (total/no metadata)", `${projectStats.images}/${projectStats.imagesWithoutMetadata}`],
  //   ["Videos (total/no metadata)", `${projectStats.videos}/${projectStats.videosWithoutMetadata}`],
  //   ["Albums", project.albums.size],
  //   ["Other files", project.unsupportedEntries.size + projectStats.others]
  // );

  // // Using console instead of consola here to ensure proper formatting.
  // console.info(projectStatsTable.toString());

  // // For a new line
  // console.info();

  // const mediaLibrary = deduplicate(project);

  // // For a new line
  // console.info();

  // // Copy and embed metadata at destination
  // await transform(mediaLibrary, options);

  // // For a new line
  // console.info();

  consola.success("Finished!");
} else {
  consola.fail("Please specify both source and destination directories.");
  consola.info('Run "pixelkasten --help" for usage information.');

  process.exit(1);
}
