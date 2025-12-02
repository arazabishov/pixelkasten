import { logger } from "../utils/logger.js";
import CliTable3 from "cli-table3";

export function logLinkReport(matches) {
  const {
    manifest,
    stats: { unmatchedMetadataFiles, unmatchedMediaFiles },
  } = matches;

  for (const entry of unmatchedMediaFiles) {
    console.log(entry);
  }

  for (const entry of unmatchedMetadataFiles) {
    console.log(entry);
  }

  const stats = new CliTable3({
    head: ["Category", "Count"],
    style: {
      head: ["cyan"],
    },
  });

  stats.push(
    ["Media files matched", manifest.length],
    ["Unmatched media files", unmatchedMediaFiles.size],
    ["Unmatched metadata files", unmatchedMetadataFiles.size]
  );

  logger.info(`${stats.toString()}\n`);
}
