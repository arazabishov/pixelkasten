import consola from "consola";
import cliProgress from "cli-progress";
import { readFile, mkdir, copyFile } from "fs/promises";
import { join, basename } from "path";
import { execa } from "execa";
import { canShowProgress } from "./logging.js";
import { extensions } from "./fs.js";
import { normalizeMetadataName } from "./workspace.js";

// TODO: add support for dryRun
export async function transform(library, { destination, dryRun }) {
  // Ensure that directory exists before writing anything to it
  await mkdir(destination, { recursive: true });

  for (const [entryPath, entry] of library) {
    if (entry.items && Array.isArray(entry.items)) {
      // This is an album
      const albumName = basename(entryPath);
      const albumPath = join(destination, albumName);

      await mkdir(albumPath, { recursive: true });

      for (const mediaEntry of entry.items) {
        await copyEntry(mediaEntry, albumPath);
      }
    } else {
      // This is a media file
      await copyEntry(entry, destination);
    }
  }
}

async function copyEntry(mediaEntry, directory) {
  const { media, metadata } = mediaEntry;

  const mediaPathSource = join(media.entry.path, media.entry.name);
  const mediaPathDestination = join(directory, media.entry.name);

  await copyFile(mediaPathSource, mediaPathDestination);

  if (metadata) {
    // TODO: this is temporary code. Once we start embedding metadata
    // into image's exif, we will not need to copy .json files over.
    const normalizedMetadataName = `${normalizeMetadataName(metadata.name)}.json`;

    const metadataPathSource = join(metadata.path, metadata.name);
    const metadataPathDestination = join(directory, normalizedMetadataName);

    await copyFile(metadataPathSource, metadataPathDestination);
  }
}

/**
 * Metadata embedding strategy for Google Photos Takeout files.
 *
 * For images, we target EXIF:DateTimeOriginal as the primary timestamp field. This is the EXIF
 * standard for photo capture time, with timezone stored separately in OffsetTimeOriginal. Empirical
 * observation shows that DateTimeOriginal is always present when CreateDate exists, making it the
 * reliable primary field. When missing, we write photoTakenTime from sidecar files to both
 * DateTimeOriginal and OffsetTimeOriginal.
 *
 * For videos, we target QuickTime:CreationDate as the primary timestamp field. This is the user-facing
 * timestamp for MP4/MOV files and must include timezone information or some applications will fail.
 * While QuickTime:CreateDate is always present in video files, CreationDate is sometimes missing.
 * We avoid modifying CreateDate since it's embedded in the binary header and stored in UTC. When
 * CreationDate is missing, we write photoTakenTime from sidecar files with proper timezone information.
 */

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
export async function embed({ library, duplicatesCount }, source) {
  const allItems = count(library) + duplicatesCount;
  const allExifMetadata = await readExifMetadata(source);

  if (allItems !== allExifMetadata.size) {
    consola.fail(
      `Media file count (${allItems}) doesn't match EXIF metadata count (${allExifMetadata.size})`
    );
    process.exit(1);
  }

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
    // progressBar.start(allItems, 0);
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
          await updateMetadata(item, allExifMetadata);
        } else {
          consola.debug(`Encountered a media item without metadata=${mediaItemFilePath}`);
        }

        processedItems.push(item);
        if (canShowProgress()) {
          // progressBar.update(processedItems.length);
        }
      }
    } else {
      const entryFilePath = join(entry.media.entry.path, entry.media.entry.name);

      if (entry.metadata) {
        await updateMetadata(entry, allExifMetadata);
      } else {
        consola.debug(`Encountered a media item without metadata=${entryFilePath}`);
      }

      processedItems.push(entry);
      if (canShowProgress()) {
        // progressBar.update(processedItems.length);
      }
    }
  }

  if (canShowProgress()) {
    // progressBar.stop();
  }

  consola.success(`Analyzed metadata of ${allItems} media files!`);
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

async function updateMetadata(item, allExifMetadata) {
  const itemMetadataFilePath = join(item.metadata.path, item.metadata.name);
  const itemMetadata = JSON.parse(await readFile(itemMetadataFilePath));

  checkMetadata(itemMetadataFilePath, itemMetadata);

  // Read current EXIF data
  const mediaItemFilePath = join(item.media.entry.path, item.media.entry.name);
  const exifData = allExifMetadata.get(mediaItemFilePath);

  if (exifData === undefined) {
    consola.fail(`Missing metadata for ${mediaItemFilePath}`);

    // If we did not find EXIF metadata, something went wrong.
    process.exit(1);
  }

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

async function readExifMetadata(source) {
  const extensionArguments = [];
  for (const extension of extensions.images.concat(extensions.videos)) {
    extensionArguments.push("-ext");
    extensionArguments.push(extension);
  }

  try {
    // By reading composite properties, we let exiftool do the heavy lifting and account for differences in metadata formats:
    // QuickTime stores these values in GPSCoordinates, while EXIF uses separate fields like GPSLatitude.
    const { stdout } = await execa("exiftool", [
      // TODO: remove it when done debugging
      "-File:FileTypeExtension",
      "-Composite:GPSAltitude",
      "-Composite:GPSLatitude",
      "-Composite:GPSLongitude",
      // This tag is the one that is read by
      "-QuickTime:CreationDate",
      // It is a part of the QuickTime movie header, which is a part of the binary file.
      // It is designed to be a universal timestamp, so it is always stored in UTC.
      "-QuickTime:CreateDate",
      // It is considered to be defacto standard timestamp for images.
      // The timezone value is stored separately in OffsetTimeOriginal.
      "-EXIF:DateTimeOriginal",
      // Also known as DateTimeDigitized by the EXIF spec.
      "-EXIF:CreateDate",
      "-json",
      "-n",
      "-r",
      ...extensionArguments,
      source,
    ]);
    const metadata = JSON.parse(stdout);
    const metadataMap = new Map();

    for (const entry of metadata) {
      metadataMap.set(entry.SourceFile, entry);
    }

    return metadataMap;
  } catch (error) {
    consola.fail(`Failed to read EXIF metadata from ${source}:`, error);

    // TODO: consider switching to throwing errors instead of explicitly exiting the process
    process.exit(1);
  }
}

function hasNonZeroGeoData(geoData) {
  if (!geoData) {
    return false;
  }

  // If you take a look at sidecar files with geoData or geoDataExif, you will see
  // that these objects also contain latitudeSpan and longitudeSpan fields.
  // The values of these fields, when present, normally represent GPS accuracy.
  // There is no direct parallel concept in media file metadata,
  // so we ignore them.
  return geoData.latitude !== 0 && geoData.longitude !== 0;
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

  const hasLat = exifLat !== undefined && exifLat !== 0;
  const hasLon = exifLon !== undefined && exifLon !== 0;

  // Only report if EXIF is missing GPS coordinates
  const hasExifGPS = hasLat && hasLon;

  if (!hasExifGPS) {
    consola.debug(`Missing GPS coordinates in EXIF for item=${itemTitle}`);
    consola.debug(
      `  Sidecar has source=${source}: lat=${data.latitude}, lon=${data.longitude}, alt=${data.altitude}`
    );
  }
}

function compareDateTime(exifData, sidecarMetadata, itemTitle) {
  // DateTimeOriginal is normally found in EXIF/image metadata. It is considered
  // to be defacto standard timestamp for images. The timezone value is
  // stored separately in OffsetTimeOriginal.
  const dateTimeOriginal = exifData.DateTimeOriginal;

  // CreateDate can be found both in videos and images.
  const createDate = exifData.CreateDate;

  // CreationDate is mostly found in metadata files for video.
  const creationDate = exifData.CreationDate;

  // TODO: it looks like QuickTime:CreateDate is a critical timestamp and should be
  // present almost always in .mp4 and .mov files. Let's check if that's true
  const extension = `.${exifData.FileTypeExtension.toLowerCase()}`;
  if (extensions.videos.includes(extension)) {
    // if (!creationDate) {
    //   console.log(exifData);
    //   console.log(`Missing QuickTime:CreationDate in metadata for item=${itemTitle}`);
    // }
    // if (!createDate) {
    //   console.log(exifData);
    //   console.log(`Missing QuickTime:CreateDate in metadata for item=${itemTitle}`);
    // }
    // ===================================
    // Observation: it looks like CreateDate is always present in video files, but CreationDate is sometimes missing.
    // What is also interesting is that when CreationDate is missing, CreateDate matches photoTakenTime available in sidecar.
    // I think it would make sense to go ahead and write photoTakenTime into CreationDate, and call it a day. Given that
    // CreateDate is embedded into binary data itself, we likely should not be touching it at all.
    // ====
    // - What is not very clear to me, should I overwrite CreateDate in various headers? IMO, it does not make sense?
    // - CreationDate must have timezone, otherwise some apps freak out.
  }

  if (extensions.images.includes(extension)) {
    // if (!dateTimeOriginal) {
    //   console.log(exifData);
    //   console.log(`Missing EXIF:DateTimeOriginal in metadata for item=${itemTitle}`);
    // }
    // if (!createDate) {
    //   console.log(exifData);
    //   console.log(`Missing EXIF:CreateDate in metadata for item=${itemTitle}`);
    // }
    // if (createDate && !dateTimeOriginal) {
    //   console.log(exifData);
    //   console.log(`Missing EXIF:CreateDate in metadata for item=${itemTitle}`);
    // }
    // Observation: it does not look like there is a scenario where CreateDate is present, but DateTimeOriginal does not.
    // I lean towards an approach where:
    //   - If DateTimeOriginal is not present, parse photoTakenTime, write its value into DateTimeOriginal + OffsetTimeOriginal (probably always will be UTC).
    //   - It is not very clear to me, if I should write into CreateDate as well?
  }

  // Only report if EXIF is missing both date fields
  if (!dateTimeOriginal && !createDate && !creationDate) {
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
