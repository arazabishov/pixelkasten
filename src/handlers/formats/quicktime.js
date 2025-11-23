import { compositeGeoTags, parseCompositeGeo } from "../composite.js";

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
};
