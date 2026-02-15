import { compositeGeoTags, parseCompositeGeo } from "../composite.js";
import { normalizeDiskDate } from "../../core/datetime.js";

export const exifHandler = {
  readTags: [
    ...compositeGeoTags,
    "Composite:GPSDateTime",
    "EXIF:DateTimeOriginal",
    "EXIF:CreateDate",
    "EXIF:ModifyDate",
    "File:FileCreateDate",
    "File:FileModifyDate",
  ],

  parse(raw) {
    const dates = [
      raw["EXIF:DateTimeOriginal"],
      raw["EXIF:CreateDate"],
      raw["Composite:GPSDateTime"],
      raw["EXIF:ModifyDate"],
      raw["File:FileCreateDate"],
      raw["File:FileModifyDate"],
    ];
    return {
      timestamp: normalizeDiskDate(raw["EXIF:DateTimeOriginal"]),
      dates: dates.map(normalizeDiskDate).filter(Boolean),
      geo: parseCompositeGeo(raw),
    };
  },

  timestamp(data) {
    // We use SubSecDateTimeOriginal to update both DateTimeOriginal and OffsetTimeOriginal in one shot.
    return [`SubSecDateTimeOriginal=${data}`];
  },

  geo(data) {
    // For some reason, exiftool does not support writing into Composite:GPSAltitude.
    // Hence, we need to write into GPSAltitude and GPSAltitudeRef separately. GPSAltitudeRef automatically
    // assigns correct value based on the passed value of altitude. For example: if > 0, it will
    // write 0 (above sea level), if < 0, it will write 1 (below sea level).
    return [
      `Composite:GPSLatitude=${data.latitude}`,
      `Composite:GPSLongitude=${data.longitude}`,
      `GPSAltitude=${data.altitude}`,
      `GPSAltitudeRef=${data.altitude}`,
    ];
  },
};
