import { logger } from "../utils/logger.js";
import CliTable3 from "cli-table3";

export function logApplyReport(manifest) {
  const stats = new CliTable3({
    head: ["Action", "Count"],
    style: {
      head: ["cyan"],
    },
  });

  let skipped = 0;
  let copied = 0;
  let embedded = 0;
  let errors = 0;

  for (const entry of manifest) {
    if (entry.dedupe?.action === "delete") {
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
