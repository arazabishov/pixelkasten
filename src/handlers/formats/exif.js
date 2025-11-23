import { compositeGeoTags, parseCompositeGeo } from "../composite.js";

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
    return {
      timestamp: raw["EXIF:DateTimeOriginal"],
      dates: [
        raw["EXIF:CreateDate"],
        raw["Composite:GPSDateTime"],
        raw["EXIF:ModifyDate"],
        raw["File:FileCreateDate"],
        raw["File:FileModifyDate"],
      ].filter(Boolean),
      geo: parseCompositeGeo(raw),
    };
  },
};
