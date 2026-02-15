import { writeFile } from "fs/promises";
import { join, relative } from "path";
import { stringify } from "csv-stringify/sync";

/**
 * Writes a per-file CSV report to the destination directory.
 *
 * @param {Array} manifest - The full manifest from the pipeline
 * @param {Object} options - Pipeline options
 * @param {string} options.source - Source directory path
 * @param {string} options.destination - Destination directory path
 * @returns {Promise<string>} The path to the written report file
 */
export async function report(manifest, options = {}) {
  const { logger } = options;

  const rows = manifest.map((entry) => {
    // All paths are relative to the source directory
    const media = relative(options.source, entry.mediaPath);

    // Empty if no sidecar was matched
    const metadata = entry.json?.path ? relative(options.source, entry.json.path) : "";

    // Empty if link stage did not assign a confidence level
    const confidence = entry.json?.confidence ?? "";

    const { status, reason } = resolveStatus(entry);

    return [media, metadata, String(confidence), status, reason];
  });

  const reportPath = join(options.destination, "report.csv");

  await writeFile(
    reportPath,
    stringify(rows, {
      header: true,
      columns: ["media", "metadata", "confidence", "status", "reason"],
    })
  );

  logger?.info(`Report written to ${reportPath}`);
  return reportPath;
}

// Walks the entry's stage properties to find its terminal status.
function resolveStatus(entry) {
  // Check apply stage first (terminal state for processed files)
  if (entry.apply?.status === "embedded") {
    return {
      status: "embedded",
      reason: "",
    };
  }

  if (entry.apply?.status === "copied") {
    return {
      status: "copied",
      reason: "",
    };
  }

  if (entry.apply?.status === "error") {
    return {
      status: "error",
      reason: entry.apply.reason ?? "",
    };
  }

  // Check reconcile stage
  if (entry.metadata?.status === "skipped") {
    return {
      status: "skipped",
      reason: entry.metadata.reason ?? "",
    };
  }

  // Check dedupe stage
  if (entry.dedupe?.status === "delete") {
    return {
      status: "deleted",
      reason: "",
    };
  }

  if (entry.dedupe?.status === "error") {
    return {
      status: "error",
      reason: entry.dedupe.reason ?? "",
    };
  }

  return {
    status: "error",
    reason: "Unknown state",
  };
}
