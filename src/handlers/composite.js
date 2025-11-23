/**
 * Composite tags allow ExifTool to interpret data from multiple
 * underlying sources (EXIF, XMP, QuickTime) automatically.
 */
export const compositeGeoTags = [
  "Composite:GPSAltitude",
  "Composite:GPSLatitude",
  "Composite:GPSLongitude",
];

/**
 * Extracts and normalizes standard Geo data from ExifTool's Composite tags.
 * @param {Object} raw - The raw ExifTool JSON object containing Composite tags.
 * @returns {{longitude: number, latitude: number, altitude?: number}|null}
 *   The normalized geo object with coordinates, or null if geo data is not present.
 */
export function parseCompositeGeo(raw) {
  // Note: we check !== undefined because 0 is a valid coordinate
  if (raw["Composite:GPSLatitude"] !== undefined && raw["Composite:GPSLongitude"] !== undefined) {
    return {
      longitude: raw["Composite:GPSLongitude"],
      latitude: raw["Composite:GPSLatitude"],
      altitude: raw["Composite:GPSAltitude"],
    };
  }

  return null;
}
