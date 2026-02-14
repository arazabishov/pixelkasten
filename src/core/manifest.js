/**
 * Returns true if the entry should be processed (not deleted or errored during dedupe).
 * When dedupe was skipped, the dedupe property is undefined, so the entry is kept.
 *
 * @param {{ dedupe?: { status: string } }} entry
 * @returns {boolean}
 */
export function canKeep(entry) {
  return entry.dedupe?.status !== "delete" && entry.dedupe?.status !== "error";
}
