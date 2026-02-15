import { link } from "./stages/link.js";
import { scan } from "./stages/scan.js";
import { dedupeHash, dedupeResolve } from "./stages/dedupe.js";
import { reconcile } from "./stages/reconcile.js";
import { rename } from "./stages/rename.js";
import { apply } from "./stages/apply.js";
import { report } from "./core/report.js";

export async function runPipeline(options, hooks = {}) {
  // Phase 1: scan files
  const rawCollections = await scan(options.source, options);
  hooks.onScan?.(rawCollections, options.source);

  // Phase 2: link media to sidecar files
  const matches = link(rawCollections, options);
  hooks.onLink?.(matches);

  const { manifest } = matches;
  if (!options.skipDedupe) {
    // Phase 3: calculate hash values for media files
    await dedupeHash(manifest, options);

    // Phase 4: use hashes to dedupe files
    await dedupeResolve(manifest, options);
    hooks.onDedupe?.(manifest);
  }

  if (!options.skipEmbed || !options.skipRename) {
    // Phase 5: resolve disk and sidecar metadata
    await reconcile(manifest, options);
    hooks.onReconcile?.(manifest);
  }

  if (!options.skipRename) {
    // Phase 6: compute target paths for renaming
    rename(manifest, options);
    hooks.onRename?.(manifest);
  }

  if (!options.dryRun) {
    // Phase 7: apply changes to disk
    await apply(manifest, options);
    hooks.onApply?.(manifest);

    // Write per-file CSV report to destination
    await report(manifest, options);
  }
}
