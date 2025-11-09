import consola from "consola";
import cliProgress from "cli-progress";
import { readFile, mkdir, copyFile } from "fs/promises";
import { join, basename } from "path";
import { execa } from "execa";
import { canShowProgress } from "./logging.js";
import { extensions } from "./fs.js";

export async function transform(mediaLibrary, options) {
  const { library, librarySize, duplicatesSize } = mediaLibrary;
  const { source, destination, dryRun } = options;

  // Count all items and compare the result against the result size of exiftool
  const allItems = librarySize + duplicatesSize;
  const allExifMetadata = await readExifMetadata(source);

  if (allItems !== allExifMetadata.size) {
    consola.fail(
      `Media file count (${allItems}) doesn't match EXIF metadata count (${allExifMetadata.size})`
    );
    process.exit(1);
  }

  if (!dryRun) {
    // Ensure that directory exists before writing anything to it
    await mkdir(destination, { recursive: true });
  }

  // Create progress bar
  const progressBar = canShowProgress()
    ? new cliProgress.SingleBar(
        {
          format: `⧗ Phase 3: ${dryRun ? "analyzing" : "embedding"} metadata |{bar}| {percentage}% | {value}/{total} media files`,
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
  for (const [entryPath, entry] of library) {
    if (entry.items && Array.isArray(entry.items)) {
      // Extracting the name from the existing directory is more reliable since
      // album names may contain characters that filesystems don't allow.
      const albumName = basename(entryPath);
      const albumDestinationPath = join(destination, albumName);

      consola.debug(`Processing album: ${albumName}`);

      if (!dryRun) {
        await mkdir(albumDestinationPath, { recursive: true });
      }

      for (const item of entry.items) {
        if (!dryRun) {
          const mediaItemDestinationFilePath = await copyEntry(item, albumDestinationPath);
          await updateMetadata(allExifMetadata, item, mediaItemDestinationFilePath);
        } else {
          await updateMetadata(allExifMetadata, item);
        }

        processedItems.push(item);
        if (canShowProgress()) {
          // progressBar.update(processedItems.length);
        }
      }
    } else {
      if (!dryRun) {
        const entryDestinationFilePath = await copyEntry(item, destination);
        await updateMetadata(allExifMetadata, entry, entryDestinationFilePath);
      } else {
        await updateMetadata(allExifMetadata, entry);
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

async function copyEntry(mediaEntry, directory) {
  const { media } = mediaEntry;

  const mediaPathSource = join(media.entry.path, media.entry.name);
  const mediaPathDestination = join(directory, media.entry.name);

  await copyFile(mediaPathSource, mediaPathDestination);

  return mediaPathDestination;
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
      "-File:FileTypeExtension",
      "-Composite:GPSAltitude",
      "-Composite:GPSLatitude",
      "-Composite:GPSLongitude",
      "-QuickTime:CreationDate",
      "-EXIF:DateTimeOriginal",
      "-api",
      "largefilesupport=1",
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

/**
 *
 * For images, we target EXIF:DateTimeOriginal as the primary timestamp field. This is the
 * EXIF standard for photo capture time, with timezone stored separately in OffsetTimeOriginal.
 * Empirical observation shows that DateTimeOriginal is always present when CreateDate exists,
 * making it the reliable primary field. When missing, we write photoTakenTime from sidecar
 * files to both DateTimeOriginal and OffsetTimeOriginal.
 *
 * For videos, we target QuickTime:CreationDate as the primary timestamp field. This is the
 * user-facing timestamp for MP4/MOV files and must include timezone information or some
 * applications will fail. While QuickTime:CreateDate is present in video files exported from
 * Google most of the time, CreationDate is sometimes missing. We avoid modifying CreateDate
 * since it's embedded in the binary header and stored in UTC. When CreationDate is missing,
 * we write photoTakenTime from sidecar files with proper timezone information.
 */
async function updateMetadata(allExifMetadata, item, itemDestinationFilePath) {
  const mediaItemFilePath = join(item.media.entry.path, item.media.entry.name);

  if (!item.metadata) {
    consola.debug(`Encountered a media item without metadata=${mediaItemFilePath}`);

    // If item does not contain metadata, we cannot do much
    return;
  }

  const itemMetadataFilePath = join(item.metadata.path, item.metadata.name);
  const itemMetadata = JSON.parse(await readFile(itemMetadataFilePath));

  checkMetadata(itemMetadataFilePath, itemMetadata);

  // Read current EXIF data
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

  // Compare date/time
  const updateDateTimeArgs = updateDateTime(exifData, itemMetadata, itemTitle);
  const updateGeoDataArgs = updateGeoData(exifData, sidecarGeoData, itemTitle);
  const updateArgs = updateDateTimeArgs.concat(updateGeoDataArgs);

  if (updateArgs.length > 0) {
    console.log("Received args:", updateArgs, itemTitle);
  }
}

function checkMetadata(metadataFilePath, metadata) {
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

  const metadataProperties = new Set(Object.keys(metadata));
  for (const key of metadataProperties) {
    if (!metadataKeys.has(key)) {
      consola.fail(`Encountered an unknown metadata file key=${key} at ${metadataFilePath}`);
      process.exit(1);
    }
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

  // TODO: should this condition be revisited?
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

// What other file types can we expect from Google Photos besides the ones that
// already present in extensions?

// Now, all that works for jpegs, RAW files (.NEF, .CR2), and tiffs. For PNGs, that command would work but
// most software has poor support of metadata in PNG files, so some minor changes would need
// to be made. For example, to get the time stamp to show up under windows, you would
// use PNG:CreationTime instead of Alldates.

// For MP4, Mov, and CR3 files, also, the above command would work, but most of that data might not be in
// the best place, as exiftool would be mostly writing to the XMP group which Adobe programs would read
// fine but other programs may not.

// So double-check your files to make sure you're not overwriting the original data, because when it comes
// to the date/time values, Google saves it as UTC, not the original time. Copying from the Google takeout
// files overwrites the correct date with an incorrect one.

function updateGeoData(metadata, sidecarGeoData, itemTitle) {
  if (!sidecarGeoData) {
    // If there is no sidecar metadata, we can simply return
    return [];
  }

  const hasLat = metadata.GPSLatitude !== undefined && metadata.GPSLatitude !== 0;
  const hasLon = metadata.GPSLongitude !== undefined && metadata.GPSLongitude !== 0;
  const hasMetadataGPS = hasLat || hasLon;

  if (!hasMetadataGPS) {
    const { data, source } = sidecarGeoData;

    consola.debug(`Missing GPS coordinates in EXIF for item=${itemTitle}`);
    consola.debug(
      `  Sidecar has source=${source}: lat=${data.latitude}, lon=${data.longitude}, alt=${data.altitude}`
    );

    // We need the file extension to prepare appropriate args for exiftool.
    const extension = `.${metadata.FileTypeExtension.toLowerCase()}`;

    if (extensions.videos.includes(extension)) {
      // TODO: check if this works for MP4 files, and other video types?

      // For QuickTime/MP4 files, coordinates need to be written into tags different compared to images.
      return [`-Keys:GPSCoordinates="${data.latitude}, ${data.longitude}, ${data.altitude}"`];
    } else if (extensions.images.includes(extension)) {
      // For some reason, exiftool does not support writing into Composite:GPSAltitude.
      // Hence, we need to write into GPSAltitude and GPSAltitudeRef separately. GPSAltitudeRef automatically
      // assigns correct value based on the passed value of altitude. For example: if > 0, it will
      // write 0 (above sea level), if < 0, it will write 1 (below sea level).
      return [
        `-Composite:GPSLatitude=${data.latitude}`,
        `-Composite:GPSLongitude=${data.longitude}`,
        `-GPSAltitude=${data.altitude}`,
        `-GPSAltitudeRef=${data.altitude}`,
      ];
    } else {
      // Fail early if we encounter unsupported file type
      throw new Error(`Encountered unsupported file type=${extension} for file=${itemTitle}`);
    }
  }

  return [];
}

function updateDateTime(metadata, sidecarMetadata, itemTitle) {
  // This timestamp, if present, points at datetime when media was taken.
  const photoTakenTimestamp = transformPhotoTakenTime(sidecarMetadata.photoTakenTime);

  // We need the file extension to prepare appropriate args for exiftool.
  const extension = `.${metadata.FileTypeExtension.toLowerCase()}`;

  if (extensions.videos.includes(extension)) {
    if (!metadata.CreationDate) {
      consola.debug(`The video file=${itemTitle} is missing QuickTime:CreationDate`);

      // We use CreationDate since that's what most apps use in UX. Also, based on experience,
      // data taken out from Google Photos almost always has QuickTime:CreateDate set already.
      return [`-CreationDate="${photoTakenTimestamp}"`];
    }
  } else if (extensions.images.includes(extension)) {
    if (!metadata.DateTimeOriginal) {
      consola.debug(`The image file=${itemTitle} is missing EXIF:DateTimeOriginal`);

      // We use SubSecDateTimeOriginal to update both EXIF:DateTimeOriginal and EXIF:OffsetTimeOriginal properties.
      // The timezone offset will always be set to +00:00 (UTC), because that's what we get from Google.
      return [`-SubSecDateTimeOriginal="${photoTakenTimestamp}"`];
    }
  } else {
    // Fail early if we encounter unsupported file type
    throw new Error(`Encountered unsupported file type=${extension} for file=${itemTitle}`);
  }

  // Returning an empty array means that we do not need to update the datetime timestamps.
  return [];
}

export function transformPhotoTakenTime(photoTakenTime) {
  if (!photoTakenTime || !photoTakenTime.timestamp) {
    throw new Error("Invalid photoTakenTime: missing timestamp property");
  }

  const timestamp = photoTakenTime.timestamp;

  // Parse the timestamp (it's in seconds, not milliseconds)
  const timestampSeconds = parseInt(timestamp);

  // Convert to milliseconds for JavaScript Date constructor
  const timestampMilliseconds = timestampSeconds * 1000;

  // Create Date object (always in UTC since Unix timestamps are UTC-based)
  const date = new Date(timestampMilliseconds);

  // Validate that we got a valid date
  if (isNaN(date.getTime())) {
    throw new Error(`Failed to parse photoTakenTime timestamp: ${timestamp}`);
  }

  // Helper function for padding
  const pad2 = (num) => String(num).padStart(2, "0");

  // Get the parts in UTC
  const YYYY = date.getUTCFullYear();

  // getUTCMonth() is 0-indexed
  const MM = pad2(date.getUTCMonth() + 1);
  const DD = pad2(date.getUTCDate());
  const HH = pad2(date.getUTCHours());
  const mm = pad2(date.getUTCMinutes());
  const ss = pad2(date.getUTCSeconds());

  // Assemble the string: the timezone always will be in UTC,
  // because that's what we get from Google.
  return `${YYYY}:${MM}:${DD} ${HH}:${mm}:${ss}+00:00`;
}
