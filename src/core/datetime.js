export function transformPhotoTakenTime(timestamp) {
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

  // Assemble the string: the timezone always will be in UTC,
  // because that's what we get from Google.
  return `${YYYY}:${MM}:${DD} ${HH}:${mm}:${ss}+00:00`;
}
