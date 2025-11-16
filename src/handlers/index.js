const dummyHandler = {};

// The master map linking supported extensions to their metadata-handling logic.
const handlerMap = {
  ".heic": dummyHandler,
  ".jpeg": dummyHandler,
  ".jpg": dummyHandler,
  ".png": dummyHandler,
  ".mp4": dummyHandler,
  ".mov": dummyHandler,
};

// A list of common media file extensions that we recognize but do not currently support.
const unsupportedMediaExtensionsList = [".avi", ".mkv", ".wmv", ".flv"];

/**
 * A Set of all supported media file extensions (lowercase)
 * for fast lookups in the 'scan' stage.
 */
export const supportedExtensions = new Set(Object.keys(handlerMap));

/**
 * A Set of all *unsupported* media file extensions (lowercase)
 * for fast lookups in the 'scan' stage.
 */
export const unsupportedMediaExtensions = new Set(unsupportedMediaExtensionsList);

/**
 * A combined Set of *all* known media extensions. This is used by the scan stage to
 * differentiate media from "other" files *before* we know if they are supported.
 */
export const allKnownMediaExtensions = new Set([
  ...supportedExtensions,
  ...unsupportedMediaExtensions,
]);

/**
 * The map of extensions to their handler functions.
 */
export const handlers = handlerMap;
