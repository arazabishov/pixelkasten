import { compositeGeoTags, parseCompositeGeo } from "../composite.js";

export const exifHandler = {
  readTags: [...compositeGeoTags, "EXIF:DateTimeOriginal"],

  parse(raw) {
    return {
      timestamp: raw["EXIF:DateTimeOriginal"],
      geo: parseCompositeGeo(raw),
    };
  },
};
