import CliTable3 from "cli-table3";
import { logger } from "../logger.js";

export function logDuplicatesReport(manifest) {
  const toDelete = manifest.filter((entry) => entry.dedupe.action === "delete").length;
  const toKeep = manifest.length - toDelete;

  const stats = new CliTable3({
    head: ["Category", "Count"],
    style: {
      head: ["cyan"],
    },
  });

  stats.push(["To delete", toDelete]);
  stats.push(["To keep", toKeep]);

  logger.info(`${stats.toString()}\n`);
}
