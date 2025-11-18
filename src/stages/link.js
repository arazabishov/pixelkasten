import { basename, dirname, join, extname } from "path";

// TODO: thoroughly document what and why we are doing here, including -edited scenario. .mp, .mp.jpg conflict scenarios, etc.
export function link(rawCollections) {
  const { filesMedia, filesMetadata, filesMetadataAlbums } = rawCollections;

  // --- Step 1: Indexing ---

  // Map: Normalized Metadata Key (Full Path) -> Original JSON Path
  const metadataFiles = new Map();
  for (const metadataFilePath of filesMetadata) {
    const metadataFileName = basename(metadataFilePath);
    const metadataFileDir = dirname(metadataFilePath);
    const key = join(metadataFileDir, getNormalizedMetadataName(metadataFileName));
    metadataFiles.set(key, metadataFilePath);
  }

  // Map: Album Directory -> Album Name
  const albums = new Map();
  for (const metadataFilePath of filesMetadataAlbums) {
    const dir = dirname(metadataFilePath);
    albums.set(dir, basename(dir));
  }

  // --- Step 2: Linking (Single Pass) ---

  const manifest = [];

  // We maintain a Set of all available metadata keys to iterate over for fuzzy matching.
  // Note: We do NOT remove items from this set during the loop. This enables
  // "One-to-Many" matching (e.g., Original + Edited + Live Video all matching one JSON).
  const allMetadataKeys = new Set(metadataFiles.keys());

  for (const mediaFilePath of filesMedia) {
    const mediaDir = dirname(mediaFilePath);

    const entry = {
      mediaPath: mediaFilePath,
      source: albums.has(mediaDir)
        ? { type: "album", name: albums.get(mediaDir) }
        : { type: "loose" },
    };

    // 1. Determine the "Target"
    // This unifies logic for Original and Edited files.
    const targetPath = getNonEditedPath(mediaFilePath);

    if (metadataFiles.has(targetPath)) {
      // 2. Attempt Exact Match (Fast O(1))
      entry.jsonPath = metadataFiles.get(targetPath);
    } else {
      // 3. Attempt Fuzzy Match (Fallback)
      // Necessary for truncated filenames or mismatched extensions
      const targetPrefix = getPathPrefix(targetPath);

      for (const metadataKey of allMetadataKeys) {
        // STRICT CHECK: Only consider metadata in the exact same directory.
        // This prevents the "Sibling Directory" false positive AND optimizes performance.
        if (dirname(metadataKey) !== mediaDir) {
          continue;
        }

        const metadataPrefix = getPathPrefix(metadataKey);

        // Bi-directional check:
        // A) Metadata starts with Media (e.g. media="img.jpg", meta="img.jpg.json")
        // B) Media starts with Metadata (e.g. media="img.MOV", meta="img.json")
        const isMatch =
          metadataKey.startsWith(targetPrefix) || targetPath.startsWith(metadataPrefix);

        if (isMatch) {
          entry.jsonPath = metadataFiles.get(metadataKey);
          break; // Found a match, stop searching for this file
        }
      }
    }

    manifest.push(entry);
  }

  // --- Step 3: Cleanup / Reporting ---

  // Now we calculate which metadata files were *actually* consumed.
  // We return the full manifest, but this logic allows us to know
  // strictly which JSON files are left over (unmatched).
  const usedMetadata = new Set();
  for (const entry of manifest) {
    if (entry.jsonPath) {
      usedMetadata.add(entry.jsonPath);
    }
  }

  // Note: In a real reporting scenario, you would compare 'usedMetadata'
  // against 'filesMetadata' to list the orphans.

  return manifest;
}

// Removes an '-edited' suffix from a file path's basename, if present.
// For example: '/path/to/image-edited.jpg' -> '/path/to/image.jpg'
function getNonEditedPath(filePath) {
  return join(dirname(filePath), basename(filePath).replace(/-edited(\.|$)/, "$1"));
}

// Gets the full path of a file without its file extension.
// For example: '/path/to/file.txt' -> '/path/to/file'
function getPathPrefix(filePath) {
  return join(dirname(filePath), basename(filePath, extname(filePath)));
}

export function getNormalizedMetadataName(fileName) {
  if (!fileName) {
    return fileName;
  }

  // 1. Guard: check for .json extension (case-insensitive)
  const ext = extname(fileName);
  if (ext.toLowerCase() !== ".json") {
    return fileName;
  }

  // 2. Get the name part *without* the extension: "A.B.C (1)" or "A.B.C" or "A"
  const head = basename(fileName, ext);

  // 3. Split the name part into its segments
  const segments = head.split(".");

  // 4. Handle simple case where there are no dots.
  if (segments.length === 1) {
    return head;
  }

  // 5. Handle complex cases: "A.B.C (1).json" or "A.B.C.json". We pop the last part to inspect it.
  const tail = segments.pop();
  const match = tail.match(/\(\d+\)/);

  if (match) {
    // Case: "A.B.C (1).json"
    // We want to transform "A.B" -> "A(1).B"
    const duplicateMarker = match[0]; // e.g., "(1)"
    const base = segments.shift(); // e.g., "A"
    segments.unshift(`${base}${duplicateMarker}`); // segments is now ["A(1)", "B"]
    return segments.join("."); // "A(1).B"
  } else {
    // Case: "A.B.C.json"
    // We want "A.B"
    // `segments` is already ["A", "B"] because of the .pop()
    return segments.join("."); // "A.B"
  }
}
