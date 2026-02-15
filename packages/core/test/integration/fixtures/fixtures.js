import { mkdtemp, rm, writeFile, mkdir, copyFile } from "fs/promises";
import { join } from "path";
import { tmpdir } from "os";

const mediaFixturesDir = join(import.meta.dirname, "media");

/**
 * Builds a Google Photos Takeout directory structure from a declarative spec.
 * Each folder maps to an array of entries: { media, name, sidecar? } or { album: true }.
 */
export async function buildTakeout(baseDir, spec) {
  for (const [folderName, entries] of Object.entries(spec)) {
    const folderPath = join(baseDir, folderName);
    await mkdir(folderPath, { recursive: true });

    for (const entry of entries) {
      if (entry.album) {
        const album = JSON.stringify(buildAlbum(folderName));
        const albumPath = join(folderPath, "metadata.json");
        await writeFile(albumPath, album);
      } else {
        await copyFile(join(mediaFixturesDir, entry.media), join(folderPath, entry.name));

        if (entry.sidecar) {
          const sidecar = JSON.stringify(buildSidecar(entry.name, entry.sidecar));
          const sidecarPath = join(folderPath, `${entry.name}.supplemental-metadata.json`);
          await writeFile(sidecarPath, sidecar);
        }
      }
    }
  }
}

// Builds a sidecar JSON object matching real Google Takeout structure.
function buildSidecar(title, data) {
  const geo = data.geo
    ? {
        latitude: data.geo.latitude,
        longitude: data.geo.longitude,
        altitude: data.geo.altitude ?? 0,
        latitudeSpan: 0.0,
        longitudeSpan: 0.0,
      }
    : {
        latitude: 0.0,
        longitude: 0.0,
        altitude: 0.0,
        latitudeSpan: 0.0,
        longitudeSpan: 0.0,
      };

  const photoTakenTime = data.timestamp
    ? {
        timestamp: data.timestamp,
      }
    : {};

  return {
    title,
    description: "",
    photoTakenTime,
    geoData: geo,
    ...(data.geo && {
      geoDataExif: geo,
    }),
  };
}

// Builds an album metadata.json matching real Google Takeout structure.
function buildAlbum(title) {
  return {
    title,
    description: "",
  };
}

/**
 * Creates a temp directory that is automatically cleaned up when the test finishes.
 */
export async function createTempDir(context) {
  const dir = await mkdtemp(join(tmpdir(), "pixelkasten-"));
  context.after(async () => {
    await rm(dir, { recursive: true, force: true });
  });
  return dir;
}
