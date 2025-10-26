import { extname } from "path";

// TODO: .MP extension will need to get special treatment
// TODO: ignore known unsupported files, like .DS_Store, thumbs.db, etc, but include them in the stats for verification.
export const supportedExtensions = {
  images: [".jpg", ".jpeg", ".png", ".gif", ".heic", ".webp"],
  videos: [".mp4", ".mov", ".avi"],
  os: [".ds_store", "thumbs.db"],
};

export function getFileType(filename) {
  const ext = extname(filename).toLowerCase();

  if (supportedExtensions.images.includes(ext)) {
    return "image";
  }

  if (supportedExtensions.videos.includes(ext)) {
    return "video";
  }

  // if (supportedExtensions.metadata.includes(ext)) {
  //   return "metadata";
  // }

  return "unsupported";
}
