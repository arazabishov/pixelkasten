import { readMetadata } from "../core/exiftool.js";
import { supportedExtensions, handlers } from "../handlers/index.js";
import { execa } from "execa";

export async function reconcile(manifest) {
  const extensions = [...supportedExtensions].flatMap((ext) => ["-ext", ext]);
  const readTags = [
    ...new Set(
      handlers.flatMap((h) => {
        return h.readTags.map((t) => `-${t}`);
      })
    ),
  ];
  const args = [...readTags, ...extensions];

  const paths = manifest.slice(0, 10).map((entry) => entry.mediaPath);

  const metadat = await readMetadata(paths, args);
  console.log(metadat);
}
