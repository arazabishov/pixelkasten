import { compositeGeoTags, parseCompositeGeo } from "../composite.js";

// TODO: consider bring back the prefix dash?
export const quicktimeHandler = {
  readTags: [
    ...compositeGeoTags,
    "QuickTime:CreationDate",
    "QuickTime:CreateDate",
    "QuickTime:ModifyDate",
    "File:FileCreateDate",
    "File:FileModifyDate",
  ],

  parse(raw) {
    return {
      timestamp: raw["QuickTime:CreationDate"],
      dates: [
        raw["QuickTime:CreationDate"],
        raw["QuickTime:CreateDate"],
        raw["Composite:GPSDateTime"],
        raw["QuickTime:ModifyDate"],
        raw["File:FileCreateDate"],
        raw["File:FileModifyDate"],
      ].filter(Boolean),
      geo: parseCompositeGeo(raw),
    };
  },

  timestamp(data) {
    // We use CreationDate since that's what most apps use in UX. Also, based on experience,
    // data taken out from Google Photos almost always has QuickTime:CreateDate set already.
    return [`CreationDate=${data}`];
  },

  geo(data) {
    // For QuickTime/MP4 files, coordinates need to be written into tags different compared to images.
    return [`Keys:GPSCoordinates=${data.latitude}, ${data.longitude}, ${data.altitude}`];
  },
};
