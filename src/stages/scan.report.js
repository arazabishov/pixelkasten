import CliTable3 from "cli-table3";
import { relative } from "path";
import { logger } from "../utils/logger.js";

export function logScanReport(rawCollections, sourcePath) {
  const {
    filesTotal,
    filesMetadata,
    filesMetadataAlbums: albums,
    filesOtherIgnored: others,
    filesMedia,
  } = rawCollections;

  const stats = new CliTable3({
    head: ["Category", "Count"],
    style: {
      head: ["cyan"],
    },
  });

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

  const filesIgnored = new CliTable3({
    head: ["Other files"],
    style: {
      head: ["cyan"],
    },
  });

  for (const file of others) {
    filesIgnored.push([relative(sourcePath, file)]);
  }

  logger.info(`${filesIgnored.toString()}\n`);
}
