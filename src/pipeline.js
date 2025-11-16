import CliTable3 from "cli-table3";
import { scan } from "./stages/scan.js";
import { relative } from "path";

export async function runPipeline(options) {
  // Phase 1: scan files
  const rawCollections = await scan(options.source);
  report(rawCollections, options.source);
}

function report(rawCollections, sourcePath) {
  const {
    filesTotal,
    filesMetadata,
    filesMetadataAlbums: albums,
    filesOtherIgnored: others,
    filesMedia,
  } = rawCollections;

  const stats = new CliTable3({
    head: ["Category", "Count"],
    style: { head: ["cyan"] },
  });

  stats.push(
    ["Albums", albums.length],
    ["Media files", filesMedia.length],
    ["Metadata files", filesMetadata.length],
    ["Other files", others.length],
    ["All files", filesTotal]
  );

  // TODO: replace consola/console, as it ruins the output of CliTable with prefixed icons
  console.info(stats.toString());

  const isOthersEmpty = others.length === 0;
  if (isOthersEmpty) {
    return;
  }

  const filesIgnored = new CliTable3({
    head: ["Other files"],
    style: { head: ["cyan"] },
  });

  for (const file of others) {
    filesIgnored.push([relative(sourcePath, file)]);
  }

  console.info(filesIgnored.toString());
}
