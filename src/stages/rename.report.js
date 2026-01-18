import { logger } from "../utils/logger.js";
import CliTable3 from "cli-table3";

export function logRenameReport(manifest) {
  const keepers = manifest.filter((entry) => entry.dedupe?.action !== "delete");

  const stats = new CliTable3({
    head: ["Status", "Count"],
    style: {
      head: ["cyan"],
    },
  });

  let processed = 0;
  let errors = 0;

  for (const entry of keepers) {
    const rename = entry.rename;

    if (!rename) {
      continue;
    }

    if (rename.status === "processed") {
      processed += 1;
    } else if (rename.status === "error") {
      errors += 1;
    }
  }

  stats.push(["To rename", processed]);
  stats.push(["Errors", errors]);

  logger.info(`${stats.toString()}\n`);
}
