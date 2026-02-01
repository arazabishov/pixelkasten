#!/usr/bin/env node

import { Command } from "commander";
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
  .option("--dry-run", "preview changes without modifying files")
  .option(
    "--prefer <type>",
    "prefer which files to keep when deduplicating: 'album' or 'loose'",
    "album"
  )
  .option("--strict", "exit on first error instead of continuing")
  .option("--skip-dedupe", "skip deduplication step")
  .option("--skip-embed", "skip metadata embedding step")
  .option("--skip-rename", "skip rename step")
  .option("--no-fuzzy", "disable fuzzy matching for metadata linking");

program.parse(process.argv);

const options = program.opts();

// Validate --prefer option
if (options.prefer && !["album", "loose"].includes(options.prefer)) {
  logger.error(`Invalid --prefer value: "${options.prefer}". Must be either "album" or "loose".`);
  process.exit(1);
}

if (options.source && options.destination) {
  if (options.dryRun) {
    logger.warn("Dry run mode - no files will be modified");
  }

  await runPipeline(options);

  logger.info("Finished!");
} else {
  logger.error("Please specify both source and destination directories.");
  logger.info('Run "pixelkasten --help" for usage information.');

  process.exit(1);
}
