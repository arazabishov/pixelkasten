import { compositeGeoTags, parseCompositeGeo } from "../composite.js";

export const quicktimeHandler = {
  readTags: [...compositeGeoTags, "QuickTime:CreationDate"],

  parse(raw) {
    return {
      timestamp: raw["QuickTime:CreationDate"],
      geo: parseCompositeGeo(raw),
    };
  },
};
