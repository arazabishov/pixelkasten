# **Guiding Principles: PixelKasten**

This document outlines the high-level requirements for a script that processes media files and sidecar .json files from a Google Photos Takeout.

## **1\. Core Objective**

The primary goal is to write metadata (timestamps, geo-data) from .json sidecar files into their corresponding media files (images, videos). This can be extended to other metadata tags in the future.

- **Implementation:** The solution will be a **Node.js script**.
- **Core Tool:** The script will orchestrate a metadata-writing tool (like exiftool) to apply changes, using Node.js's child_process to execute commands.

## **2\. Guiding Principles (Constraints)**

The script **MUST** adhere to the following rules:

### **Principle 1: Do Not Overwrite Existing Data**

If a media file already contains the relevant native metadata, it MUST NOT be updated.

- **Timestamp Check:** Before writing, the script must check for the existence of relevant _native_ timestamp tags for that file format.
- **Geo-Data Check:** Before writing, the script must check for the existence of relevant _native_ geo-data tags for that file format.
- **Implementation:** The script should first read and parse existing metadata from the media file before deciding whether to write new data.

### **Principle 2: Validate Input Data**

Invalid data from the .json sidecar must be ignored.

- **Geo-Data Check:** If geoData.latitude or geoData.longitude are 0, 0.0, null, or undefined, the script MUST NOT write _any_ geo-data for that file.

### **Principle 3: Use Native Tags & Correct Formatting**

Metadata MUST be written to the correct native tags for each file format, and the value MUST be formatted to that tag's standard.

- **JSON Source Data:**
  - photoTakenTime.timestamp: UTC-based Unix epoch string.
  - geoData: Signed decimal latitude, longitude, and altitude.
- **Format-Specific Logic:** The script must contain a ruleset to map file extensions (e..g., .jpg, .png, .mov, .mp4, .gif) to their correct native tags and required value formats (e.g., EXIF for JPEG, QuickTime tags for MOV). This logic must handle the correct formatting of timestamps (with or without timezones) and geo-data as required by the native standard.

### **Principle 4: Be Strict on Unknown Formats**

The script must _only_ process file formats for which it has explicit rules.

- **Handling:** If an unknown file format (e.g., .mkv, .avi) is encountered, the script MUST skip it.
- **Reporting:** At the end of its run, the script should produce a summary that includes a list of all skipped files with unknown extensions. This is preferable to writing non-standard "fallback" tags.

## **3\. Development & Operational Principles**

### **Principle 5: Prioritize Simplicity**

The project should favor simplicity over complexity. The number of third-party dependencies should be kept to a minimum. Any dependency that is added must be scrutinized and justified.

### **Principle 6: Ensure Testability**

The project must have good automated test coverage. Tests should be written using the native Node.js testing framework.

### **Principle 7: Maintain Transparency**

The project should keep a good level of transparency and report on its execution. This includes logging the outcomes of different phases and providing a final summary.

- **Reporting:** The script must report on file statuses, such as how many files were successfully matched with metadata, how many were skipped (and why, e.g., "existing data" or "unknown format"), and how many media files or .json files did not have a matching pair.

## **4. Test Code Style Guidelines**

### **Principle 1: Write Behavior-Focused Tests**

Test names should describe observable behavior, not implementation details. Treat functions as black boxes and verify what you can observe externally.

- **Good**: `"should not perform disk operations when manifest is empty"`
- **Bad**: `"should filter out entries marked for deletion"` (mentions filtering - implementation detail)

### **Principle 2: Use Clear Assertions**

Every assertion should have a descriptive comment explaining what it verifies. Format: **comment** → **assertion** → **blank line** (except last assertion).

```javascript
test("should queue timestamp write when missing from disk metadata", () => {
  // Setup
  const manifest = [{ mediaPath: "/path/image.jpg" }];

  await reconcile(manifest, {});

  // Verify entry was marked for processing
  strictEqual(manifest[0].metadata.status, "processed");

  // Verify one tag was queued for writing
  strictEqual(manifest[0].metadata.writeTags.length, 1);

  // Verify timestamp was added to dates
  strictEqual(manifest[0].metadata.dates[0], "2023-01-01T12:00:00.000Z");
});
```

### **Principle 3: Use Named Imports**

Import assertion functions directly from `node:assert`:

```javascript
import { test, describe, beforeEach, mock } from "node:test";
import { strictEqual, deepStrictEqual, ok, rejects } from "node:assert";
```

### **Principle 4: Use Explicit Return Statements in Mocks**

Mock implementations should use explicit return statements with block bodies:

```javascript
// ✅ Good
readMetadataMock.mock.mockImplementation(async () => {
  return new Map([["test.jpg", {}]]);
});

// ❌ Bad - implicit return
readMetadataMock.mock.mockImplementation(async () => new Map([["test.jpg", {}]]));
```

For unused parameters, use `_`:

```javascript
transformMock.mock.mockImplementation((_) => {
  return "result";
});
```

### **Principle 5: Mock Only What's Called**

Only mock what's actually used in the test. If a code path isn't reached, don't mock it.

```javascript
// ❌ Bad - mocks parse() even though it's never called (sidecar is null)
readSidecarMock.mock.mockImplementation(async () => {
  return null;
});
handlerMock.parse.mock.mockImplementation(() => {
  // Never called!
  return { timestamp: null };
});

// ✅ Good - only mock what's needed
readSidecarMock.mock.mockImplementation(async () => {
  return null;
});
```

## **5. Code Style Guidelines**

### **Principle 1: Always Use Braces for Control Statements**

All control flow statements (`if`, `for`, `while`, etc.) must use braces, even for single-line bodies.

```javascript
// ✅ Good
if (!parsed) {
  continue;
}

if (value === null) {
  return;
}

// ❌ Bad - inline without braces
if (!parsed) continue;
if (value === null) return;
```

### **Principle 2: Use Multi-Line Object Definitions**

Object literals should use multi-line format, even for single properties.

```javascript
// ✅ Good
entry.rename = {
  status: "error",
};

const options = {
  strict: true,
};

// ❌ Bad - inline object
entry.rename = { status: "error" };
const options = { strict: true };
```
