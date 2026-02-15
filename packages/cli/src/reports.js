import CliTable3 from "cli-table3";
import { relative } from "path";
import { canKeep } from "@pixelkasten/core";
import { logger } from "./logger.js";

function table(head) {
  return new CliTable3({
    head,
    style: {
      head: ["cyan"],
    },
  });
}

export function logScanReport(rawCollections, sourcePath) {
  const {
    filesTotal,
    filesMetadata,
    filesMetadataAlbums: albums,
    filesOtherIgnored: others,
    filesMedia,
  } = rawCollections;

  const stats = table(["Category", "Count"]);

  stats.push(
    ["Albums", albums.length],
    ["Media files", filesMedia.length],
    ["Metadata files", filesMetadata.length],
    ["Other files", others.length],
    ["All files", filesTotal]
  );

  const isOthersEmpty = others.length === 0;

  // We do not want a trailing \n if this is not the last table to print.
  logger.info(isOthersEmpty ? `${stats.toString()}\n` : stats.toString());

  if (isOthersEmpty) {
    return;
  }

  const filesIgnored = table(["Other files"]);

  for (const file of others) {
    filesIgnored.push([relative(sourcePath, file)]);
  }

  logger.info(`${filesIgnored.toString()}\n`);
}

export function logLinkReport(matches) {
  const {
    manifest,
    stats: { unmatchedMetadataFiles, unmatchedMediaFiles },
  } = matches;

  for (const entry of unmatchedMediaFiles) {
    logger.warn(entry);
  }

  for (const entry of unmatchedMetadataFiles) {
    logger.warn(entry);
  }

  // Count matches by confidence level.
  const confidenceCounts = { 3: 0, 2: 0, 1: 0 };
  for (const { json } of manifest) {
    if (json?.confidence) {
      confidenceCounts[json.confidence]++;
    }
  }

  const stats = table(["Category", "Count"]);

  stats.push(
    [`Matched with high confidence`, confidenceCounts[3]],
    [`Matched with medium confidence`, confidenceCounts[2]],
    [`Matched with satisfactory confidence`, confidenceCounts[1]],
    ["Unmatched metadata files", unmatchedMetadataFiles.size],
    ["Unmatched media files", unmatchedMediaFiles.size]
  );

  logger.info(`${stats.toString()}\n`);
}

export function logDuplicatesReport(manifest) {
  const stats = table(["Category", "Count"]);

  let toDelete = 0;
  let toKeep = 0;
  let errors = 0;

  for (const entry of manifest) {
    if (entry.dedupe.status === "error") {
      errors += 1;
    } else if (entry.dedupe.status === "delete") {
      toDelete += 1;
    } else {
      toKeep += 1;
    }
  }

  stats.push(["To delete", toDelete]);
  stats.push(["To keep", toKeep]);
  stats.push(["Errors", errors]);

  logger.info(`${stats.toString()}\n`);
}

export function logReconcileReport(manifest) {
  const keepers = manifest.filter(canKeep);

  const stats = table(["Action", "Count"]);

  let updates = 0;
  let skipped = 0;
  let errors = 0;
  let noop = 0;

  for (const entry of keepers) {
    if (entry.metadata.status === "processed") {
      updates += 1;
    } else if (entry.metadata.status === "skipped") {
      skipped += 1;
    } else if (entry.metadata.status === "error") {
      errors += 1;
    } else if (entry.metadata.status === "noop") {
      noop += 1;
    }
  }

  stats.push(["To update", updates]);
  stats.push(["Unsupported", skipped]);
  stats.push(["Errors", errors]);
  stats.push(["Noop", noop]);

  logger.info(`${stats.toString()}\n`);
}

export function logRenameReport(manifest) {
  const keepers = manifest.filter(canKeep);

  const stats = table(["Action", "Count"]);

  let processed = 0;
  let skipped = 0;
  let errors = 0;

  for (const entry of keepers) {
    if (entry.rename?.status === "processed") {
      processed += 1;
    } else if (entry.metadata?.status === "skipped") {
      skipped += 1;
    } else if (entry.rename?.status === "error") {
      errors += 1;
    }
  }

  stats.push(["To rename", processed]);
  stats.push(["Unsupported", skipped]);
  stats.push(["Errors", errors]);

  logger.info(`${stats.toString()}\n`);
}

export function logApplyReport(manifest) {
  const stats = table(["Action", "Count"]);

  let skipped = 0;
  let copied = 0;
  let embedded = 0;
  let errors = 0;

  for (const entry of manifest) {
    if (entry.dedupe?.status === "delete") {
      skipped += 1;
    } else if (entry.apply?.status === "copied") {
      copied += 1;
    } else if (entry.apply?.status === "embedded") {
      embedded += 1;
    } else if (entry.apply?.status === "error") {
      errors += 1;
    }
  }

  stats.push(["Skipped (duplicates)", skipped]);
  stats.push(["Copied", copied]);
  stats.push(["Embedded", embedded]);
  stats.push(["Errors", errors]);

  logger.info(`${stats.toString()}\n`);
}
