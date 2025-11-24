import { readFile } from "fs/promises";

export async function readSidecar(jsonPath) {
  if (!jsonPath) {
    return null;
  }

  try {
    const { photoTakenTime, geoDataExif, geoData } = JSON.parse(await readFile(jsonPath, "utf8"));
    const geo = getGeoData(geoDataExif, geoData);

    return {
      timestamp: photoTakenTime?.timestamp,
      geo: geo,
    };
  } catch (error) {
    throw new Error(`Failed to read sidecar file at ${jsonPath}: ${error.message}`);
  }
}

function getGeoData(geoDataExif, geoData) {
  // If you take a look at sidecar files with geoData or geoDataExif, you will see that
  // these objects also contain latitudeSpan and longitudeSpan fields. The values of
  // these fields, when present, normally represent GPS accuracy. There is no
  // direct parallel concept in media file metadata, so we ignore them.
  if (hasGeoData(geoDataExif)) {
    return {
      longitude: geoDataExif.longitude,
      latitude: geoDataExif.latitude,
      altitude: geoDataExif.altitude,
    };
  }

  if (hasGeoData(geoData)) {
    return {
      longitude: geoData.longitude,
      latitude: geoData.latitude,
      altitude: geoData.altitude,
    };
  }

  return undefined;
}

function hasGeoData(geo) {
  // Contrary to parseCompositeGeo function at composite.js, we treat (0, 0) coordinates
  // as non-present. The reason is because Google decided to use (0, 0) as
  // default values for when location data is not present.
  return !!geo && geo.latitude !== 0 && geo.longitude !== 0;
}
