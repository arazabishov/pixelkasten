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
    const sha256 = await calculateHash(entry.mediaPath);

    manifest[index] = {
      ...entry,
      dedupe: {
        hash: sha256,
        action: "pending",
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

function calculateHash(filePath) {
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

export async function dedupeResolve(manifest, options) {
  const progressBar = canShowProgress()
    ? new cliProgress.SingleBar(
        {
          format: "⧗ Phase 4: resolving duplicates |{bar}| {percentage}% | {value}/{total} entries",
          hideCursor: true,
        },
        cliProgress.Presets.shades_classic
      )
    : null;

  // Group entries by hash
  const hashes = new Map();
  for (const entry of manifest) {
    const hash = entry.dedupe.hash;
    if (!hashes.has(hash)) {
      hashes.set(hash, []);
    }
    hashes.get(hash).push(entry);
  }

  if (canShowProgress()) {
    progressBar.start(hashes.size, 0);
  }

  // Resolve duplicates
  const hashGroups = Array.from(hashes.values());
  for (let index = 0; index < hashGroups.length; index++) {
    const duplicates = hashGroups[index];

    if (duplicates.length === 1) {
      // Unique file - always keep
      duplicates[0].dedupe.action = "keep";
    } else {
      // Multiple files with same hash - apply preference
      for (const entry of duplicates) {
        entry.dedupe.action = entry.source.type === options.prefer ? "keep" : "delete";
      }
    }

    if (canShowProgress()) {
      progressBar.update(index);
    }
  }

  if (canShowProgress()) {
    progressBar.stop();
  }

  checkInvariants(manifest);
}

function checkInvariants(manifest) {
  for (const entry of manifest) {
    const action = entry.dedupe.action;

    if (action !== "keep" && action !== "delete") {
      throw new Error(
        `Invalid dedupe action "${action}" for file: ${entry.mediaPath}. Expected "keep" or "delete".`
      );
    }
  }
}
