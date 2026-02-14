import CliTable3 from "cli-table3";
import { canKeep } from "../core/manifest.js";
import { logger } from "../utils/logger.js";

export function logReconcileReport(manifest) {
  const keepers = manifest.filter(canKeep);

  const stats = new CliTable3({
    head: ["Action", "Count"],
    style: {
      head: ["cyan"],
    },
  });

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
