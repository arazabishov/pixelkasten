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

  // Count matches by confidence level.
  const confidenceCounts = { 3: 0, 2: 0, 1: 0 };
  for (const { json } of manifest) {
    if (json?.confidence) {
      confidenceCounts[json.confidence]++;
    }
  }

  const stats = new CliTable3({
    head: ["Category", "Count"],
    style: {
      head: ["cyan"],
    },
  });

  stats.push(
    [`Matched with high confidence`, confidenceCounts[3]],
    [`Matched with medium confidence`, confidenceCounts[2]],
    [`Matched with satisfactory confidence`, confidenceCounts[1]],
    ["Unmatched metadata files", unmatchedMetadataFiles.size],
    ["Unmatched media files", unmatchedMediaFiles.size]
  );

  logger.info(`${stats.toString()}\n`);
}
