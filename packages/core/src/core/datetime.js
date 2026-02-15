/**
 * Normalizes raw date strings from ExifTool to ISO format (YYYY-MM-DDTHH:MM:SS) for file renaming.
 * Preserves "wall clock" time by ignoring timezone offsets to match user expectations.
 *
 * Examples:
 * - "2023:05:20 14:30:00"       -> "2023-05-20T14:30:00"
 * - "2023:05:20 14:30:00-05:00" -> "2023-05-20T14:30:00" (offset ignored)
 * - "2023:05:20 14:30:00Z"      -> "2023-05-20T14:30:00" (Z ignored)
 *
 * Uses regex extraction to avoid timezone drift from Date.parse().
 *
 * @param {string} date - Raw date string from ExifTool
 * @returns {string|null} ISO formatted date string or null if invalid
 */
export function normalizeDiskDate(date) {
  if (!date || typeof date !== "string") {
    return null;
  }

  // Regex to capture: YYYY : MM : DD (space) HH : MM : SS
  // Matches delimiters : or - to be flexible with different tag standards.
  const match = date.trim().match(/^(\d{4})[:/-](\d{2})[:/-](\d{2})\s+(\d{2}):(\d{2}):(\d{2})/);

  if (match) {
    const [_, y, m, d, h, min, s] = match;

    // Return standard ISO format: YYYY-MM-DDTHH:MM:SS
    return `${y}-${m}-${d}T${h}:${min}:${s}`;
  }

  return null;
}

/**
 * Parses an ISO date string into its components.
 *
 * @param {string} isoDate - Date in format "2023-01-15T14:30:45"
 * @returns {Object|null} Parsed components or null if invalid
 *   - year: string (4 digits)
 *   - month: number (1-12)
 *   - day: number (1-31)
 *   - hour: number (0-23)
 *   - minute: number (0-59)
 *   - second: number (0-59)
 */
export function parseIsoDate(isoDate) {
  if (!isoDate || typeof isoDate !== "string") {
    return null;
  }

  const date = new Date(isoDate);

  if (isNaN(date.getTime())) {
    return null;
  }

  return {
    year: String(date.getFullYear()),
    month: date.getMonth() + 1,
    day: date.getDate(),
    hour: date.getHours(),
    minute: date.getMinutes(),
    second: date.getSeconds(),
  };
}

/**
 * Converts a Unix epoch timestamp to both ISO and EXIF datetime formats.
 *
 * @param {string|number} timestamp - Unix epoch timestamp in seconds
 * @returns {{ iso: string, exif: string }} Datetime in both formats:
 *   - iso: "2023-05-20T19:30:00" (for renaming, UTC)
 *   - exif: "2023:05:20 19:30:00+00:00" (for metadata writing, UTC explicit)
 */
export function parsePhotoTakenTime(timestamp) {
  // Parse the timestamp (it's in seconds, not milliseconds)
  const timestampSeconds = parseInt(timestamp);

  // Convert to milliseconds for JavaScript Date constructor
  const timestampMilliseconds = timestampSeconds * 1000;

  // Create Date object (always in UTC since Unix timestamps are UTC-based)
  const date = new Date(timestampMilliseconds);

  // Validate that we got a valid date
  if (isNaN(date.getTime())) {
    throw new Error(`Failed to parse photoTakenTime timestamp: ${timestamp}`);
  }

  // Helper function for padding
  const pad2 = (num) => String(num).padStart(2, "0");

  // Get the parts in UTC
  const YYYY = date.getUTCFullYear();

  // getUTCMonth() is 0-indexed
  const MM = pad2(date.getUTCMonth() + 1);
  const DD = pad2(date.getUTCDate());
  const HH = pad2(date.getUTCHours());
  const mm = pad2(date.getUTCMinutes());
  const ss = pad2(date.getUTCSeconds());

  return {
    iso: `${YYYY}-${MM}-${DD}T${HH}:${mm}:${ss}`,
    exif: `${YYYY}:${MM}:${DD} ${HH}:${mm}:${ss}+00:00`,
  };
}
