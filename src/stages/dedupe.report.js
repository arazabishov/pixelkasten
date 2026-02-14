import CliTable3 from "cli-table3";
import { logger } from "../utils/logger.js";

export function logDuplicatesReport(manifest) {
  const stats = new CliTable3({
    head: ["Category", "Count"],
    style: {
      head: ["cyan"],
    },
  });

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
