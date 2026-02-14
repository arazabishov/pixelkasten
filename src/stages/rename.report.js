import CliTable3 from "cli-table3";
import { canKeep } from "../core/manifest.js";
import { logger } from "../utils/logger.js";

export function logRenameReport(manifest) {
  const keepers = manifest.filter(canKeep);

  const stats = new CliTable3({
    head: ["Action", "Count"],
    style: {
      head: ["cyan"],
    },
  });

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
