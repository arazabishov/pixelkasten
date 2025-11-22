import { compositeGeoTags } from "../constants.js";

export const exifHandler = {
  readTags: [...compositeGeoTags, "-EXIF:DateTimeOriginal"],
};
