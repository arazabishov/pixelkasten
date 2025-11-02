import consola from "consola";
import { readFile } from "fs/promises";
import { join } from "path";
import { execa } from "execa";
import cliProgress from "cli-progress";
import { canShowProgress } from "./logging.js";

// To ensure that the tool does not miss any critical properties in the sidecar files,
// we keep track of known properties here.
const metadataKeys = new Set([
  "title",
  "description",
  "imageViews",
  "creationTime",
  "photoTakenTime",
  "googlePhotosOrigin",
  "geoDataExif",
  "geoData",
  "appSource",
  "url",
]);

// TODO: this method will likely need to be submerged into organize file, because we want to combine
// copy and write actions (we don't want to modify original files).
export async function embed(library) {
  const totalItems = count(library);

  // Create progress bar
  const progressBar = canShowProgress()
    ? new cliProgress.SingleBar(
        {
          format:
            "⧗ Phase 3: analyzing metadata |{bar}| {percentage}% | {value}/{total} media files",
          barCompleteChar: "\u2588",
          barIncompleteChar: "\u2591",
          hideCursor: true,
        },
        cliProgress.Presets.shades_classic
      )
    : null;

  if (canShowProgress()) {
    progressBar.start(totalItems, 0);
  }

  const processedItems = [];
  for (const entry of library.values()) {
    if (entry.items && Array.isArray(entry.items)) {
      // We need to parse album metadata files to ensure correct directory names
      const albumMetadataFilePath = join(entry.metadata.path, entry.metadata.name);
      const albumMetadata = JSON.parse(await readFile(albumMetadataFilePath));

      consola.debug(`Processing album: ${albumMetadata.title}`);

      for (const item of entry.items) {
        const mediaItemFilePath = join(item.media.entry.path, item.media.entry.name);

        if (item.metadata) {
          await updateMetadata(item);
        } else {
          consola.debug(`Encountered a media item without metadata=${mediaItemFilePath}`);
        }

        processedItems.push(item);
        if (canShowProgress()) {
          progressBar.update(processedItems.length);
        }
      }
    } else {
      const entryFilePath = join(entry.media.entry.path, entry.media.entry.name);

      if (entry.metadata) {
        await updateMetadata(entry);
      } else {
        consola.debug(`Encountered a media item without metadata=${entryFilePath}`);
      }

      processedItems.push(entry);
      if (canShowProgress()) {
        progressBar.update(processedItems.length);
      }
    }
  }

  if (canShowProgress()) {
    progressBar.stop();
  }

  consola.success(`Analyzed metadata of ${totalItems} media files!`);
}

function count(library) {
  // Count total items to process
  let totalItems = 0;
  for (const entry of library.values()) {
    if (entry.items && Array.isArray(entry.items)) {
      totalItems += entry.items.length;
    } else {
      totalItems += 1;
    }
  }

  return totalItems;
}

async function updateMetadata(item) {
  const itemMetadataFilePath = join(item.metadata.path, item.metadata.name);
  const itemMetadata = JSON.parse(await readFile(itemMetadataFilePath));

  checkMetadata(itemMetadataFilePath, itemMetadata);

  // Read current EXIF data
  const mediaItemFilePath = join(item.media.entry.path, item.media.entry.name);
  const exifData = await readExifMetadata(mediaItemFilePath);

  // Select the best geo data source from sidecar
  const sidecarGeoData = geoData(itemMetadata);

  // The title will be used only for logging
  const itemTitle = itemMetadata.title || mediaItemFilePath;

  // Compare GPS data
  compareGeoData(exifData, sidecarGeoData, itemTitle);

  // Compare date/time
  compareDateTime(exifData, itemMetadata, itemTitle);
}

function checkMetadata(metadataFilePath, metadata) {
  const metadataProperties = new Set(Object.keys(metadata));
  for (const key of metadataProperties) {
    if (!metadataKeys.has(key)) {
      consola.fail(`Encountered an unknown metadata file key=${key} at ${metadataFilePath}`);
      process.exit(1);
    }
  }
}

async function readExifMetadata(mediaPath) {
  try {
    // The -n flag is used for numeric output for GPS coordinates
    const { stdout } = await execa("exiftool", ["-json", "-n", mediaPath]);
    const metadata = JSON.parse(stdout);

    if (metadata.length === 1) {
      return metadata[0];
    } else {
      consola.fail(`Received more EXIF metadata than expected for ${mediaPath}:`, error);
    }
  } catch (error) {
    consola.fail(`Failed to read EXIF metadata from ${mediaPath}:`, error);

    // TODO: consider switching to throwing errors instead of explicitly exiting the process
    process.exit(1);
  }
}

function hasNonZeroGeoData(geoData) {
  if (!geoData) {
    return false;
  }

  return geoData.latitude !== 0 || geoData.longitude !== 0;
}

function geoData(sidecarMetadata) {
  // Prefer geoDataExif if it has non-zero values
  if (hasNonZeroGeoData(sidecarMetadata.geoDataExif)) {
    return { data: sidecarMetadata.geoDataExif, source: "geoDataExif" };
  }

  // Fall back to geoData if it has non-zero values
  if (hasNonZeroGeoData(sidecarMetadata.geoData)) {
    return { data: sidecarMetadata.geoData, source: "geoData" };
  }

  return null;
}

function compareGeoData(exifData, sidecarGeoData, itemTitle) {
  if (!sidecarGeoData) {
    // If there is no sidecar metadata, we can simply return
    return;
  }

  const { data, source } = sidecarGeoData;
  const exifLat = exifData.GPSLatitude;
  const exifLon = exifData.GPSLongitude;

  // Only report if EXIF is missing GPS coordinates
  const hasExifGPS = exifLat !== undefined && exifLon !== undefined;

  if (!hasExifGPS) {
    consola.debug(`Missing GPS coordinates in EXIF for item=${itemTitle}`);
    consola.debug(
      `  Sidecar has source=${source}: lat=${data.latitude}, lon=${data.longitude}, alt=${data.altitude}`
    );
  }
}

function compareDateTime(exifData, sidecarMetadata, itemTitle) {
  const dateTimeOriginal = exifData.DateTimeOriginal;
  const createDate = exifData.CreateDate;

  // Only report if EXIF is missing both date fields
  if (!dateTimeOriginal && !createDate) {
    const photoTakenTimestamp = sidecarMetadata.photoTakenTime?.timestamp;
    const creationTimestamp = sidecarMetadata.creationTime?.timestamp;

    if (photoTakenTimestamp || creationTimestamp) {
      consola.debug(`Missing date/time in EXIF for item=${itemTitle}`);

      if (photoTakenTimestamp) {
        const sidecarDate = new Date(parseInt(photoTakenTimestamp) * 1000);
        consola.debug(
          `  Sidecar has photoTakenTime: ${sidecarDate.toISOString()} (timestamp=${photoTakenTimestamp})`
        );
      }

      if (creationTimestamp) {
        const sidecarDate = new Date(parseInt(creationTimestamp) * 1000);
        consola.debug(
          `  Sidecar has creationTime: ${sidecarDate.toISOString()} (timestamp=${creationTimestamp})`
        );
      }
    }
  }
}
