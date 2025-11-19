import cliProgress from "cli-progress";
import { createHash } from "crypto";
import { createReadStream } from "fs";
import { canShowProgress } from "../logger.js";

export async function dedupeHash(manifest) {
  // Create progress bar (only if not in verbose mode)
  const progressBar = canShowProgress()
    ? new cliProgress.SingleBar(
        {
          format: "⧗ Phase 3: calculating hashes |{bar}| {percentage}% | {value}/{total} entries",
          hideCursor: true,
        },
        cliProgress.Presets.shades_classic
      )
    : null;

  if (canShowProgress()) {
    progressBar.start(manifest.length, 0);
  }

  for (let index = 0; index < manifest.length; index++) {
    const entry = manifest[index];
    const sha256 = await calculateFileSha256(entry.mediaPath);

    manifest[index] = {
      ...entry,
      dedupe: {
        hash: sha256,
        action: "keep",
      },
    };

    if (canShowProgress()) {
      progressBar.update(index + 1);
    }
  }

  if (canShowProgress()) {
    progressBar.stop();
  }
}

export async function dedupeResolve(manifest) {
  // TODO: add a flag that controls which duplicates live and which should be removed
  // TODO: figure out which files to keep and which to delete
}

function calculateFileSha256(filePath) {
  return new Promise((resolve, reject) => {
    const hash = createHash("sha256");
    const stream = createReadStream(filePath);

    stream.on("error", (err) => {
      reject(err);
    });

    stream.on("data", (chunk) => {
      hash.update(chunk);
    });

    stream.on("end", () => {
      resolve(hash.digest("hex"));
    });
  });
}
