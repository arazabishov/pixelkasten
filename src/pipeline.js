import { link } from "./stages/link.js";
import { scan } from "./stages/scan.js";
import { logScanReport } from "./stages/scan.report.js";
import { logger } from "./logger.js";

// TODO: manifest structure

// {
//   // --- Set by `scan` stage (Stage 1) ---

//   /**
//    * The relative path to the media file from the root directory.
//    * This is the "primary key" for the file.
//    * Example: 'Photos from 2023/IMG_1234.jpg'
//    */
//   "mediaPath": "Photos from 2023/IMG_1234.jpg",

//   /**
//    * The relative path to the matching .json file.
//    * This will be `null` if no matching JSON was found.
//    */
//   "jsonPath": "Photos from 2023/IMG_1234.jpg.json",

//   /**
//    * Describes the "source" of the file, based on its path.
//    * This is used for both the "Album Priority" dedupe rule
//    * and for building the final output directory structure.
//    */
//   "source": {
//     /** 'album' = A user-created album (high priority).
//      * 'loose' = A "Photos from YYYY" folder (low priority).
//      */
//     "type": "album",

//     /** The name of the group, extracted from the path. */
//     "name": "My Trip" // e.g., "My Trip", "Photos from 2023"
//   },

//   // --- Set by `dedupe-hash` & `dedupe-resolve` stages (Stages 2 & 3) ---
//   "dedupe": {
//     /** The sha256 hash of the *original* file. Set by `dedupe-hash`. */
//     "hash": "a1b2c3d4e5f6...",

//     /** The final decision. Set by `dedupe-resolve`. */
//     "action": "pending" // 'pending' | 'keep' | 'delete'
//   },

//   // --- Set by `resolve-metadata` stage (Stage 4) ---
//   /**
//    * The "single source of truth" for the file's metadata.
//    * This is determined by applying Principle 1 (Do Not Overwrite).
//    * All other stages (embed-plan, rename-plan) MUST read from this.
//    */
//   "authoritativeMetadata": {
//     /** * The file's "final" timestamp (as a UTC epoch string).
//      * This is: diskMeta.timestamp || jsonMeta.timestamp || null
//      */
//     "timestamp": "1589000000",

//     /** The file's "final" geo data. */
//     "geo": { "latitude": 34.1, "longitude": -118.2 },

//     // --- Private fields used *only* by `embed-plan` ---

//     /** The timestamp read directly from the disk (or null). */
//     "diskTimestamp": null,

//     /** The geo data read directly from the disk (or null). */
//     "diskGeo": null
//   },

//   // --- Set by `embed-plan` stage (Stage 5) ---
//   "embed": {
//     /** The plan's status, based on comparing authoritative vs. disk. */
//     "status": "pending", // 'pending' | 'processed' | 'skipped_exists' | 'skipped_duplicate'

//     /** The array of exiftool arguments to execute in the `apply` stage. */
//     "writeArgs": ["-DateTimeOriginal=2020:05:09 04:53:20", "-OffsetTimeOriginal=+00:00"]
//   },

//   // --- Set by `rename-plan` stage (Stage 6) ---
//   "rename": {
//     /** The new file name, generated from `authoritativeMetadata.timestamp`. */
//     "newName": "2020-05-09_04-53-20.jpg"
//   }
// }

export async function runPipeline(options) {
  // Phase 1: scan files
  const rawCollections = await scan(options.source);
  logScanReport(rawCollections, options.source);

  const manifest = link(rawCollections);
  // logger.info(manifest);

  // Phase 2: linking metadata to media files
}
