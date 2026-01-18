import { link } from "./stages/link.js";
import { scan } from "./stages/scan.js";
import { logScanReport } from "./stages/scan.report.js";
import { logLinkReport } from "./stages/link.report.js";
import { dedupeHash, dedupeResolve } from "./stages/dedupe.js";
import { logDuplicatesReport } from "./stages/dedupe.report.js";
import { reconcile } from "./stages/reconcile.js";
import { logReconcileReport } from "./stages/reconcile.report.js";

export async function runPipeline(options) {
  // Phase 1: scan files
  const rawCollections = await scan(options.source);
  logScanReport(rawCollections, options.source);

  // Phase 2: link media to sidecar files
  const matches = link(rawCollections, options);
  logLinkReport(matches);

  const { manifest } = matches;
  if (!options.skipDedupe) {
    // Phase 3: calculate hash values for media files
    await dedupeHash(manifest);

    // Phase 4: use hashes to dedupe files
    await dedupeResolve(manifest, options);
    logDuplicatesReport(manifest);
  }

  if (!options.skipEmbed || !options.skipRename) {
    // Phase 5: resolve disk and sidecar metadata
    await reconcile(manifest);
    logReconcileReport(manifest);
  }

  if (!options.skipRename) {
    // TODO: call rename functions
  }

  // TODO: call apply function that applies changes
}
