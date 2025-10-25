import { extname } from "path";

const supportedExtensions = {
  images: [".jpg", ".jpeg", ".png", ".gif", ".heic", ".webp"],
  videos: [".mp4", ".mov", ".avi"],
  metadata: [".json"],
};

export function getFileType(filename) {
  const ext = extname(filename).toLowerCase();

  if (supportedExtensions.images.includes(ext)) {
    return "image";
  }

  if (supportedExtensions.videos.includes(ext)) {
    return "video";
  }

  if (supportedExtensions.metadata.includes(ext)) {
    return "metadata";
  }

  return "unsupported";
}
