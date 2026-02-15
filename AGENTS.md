# AGENTS.md

This file provides guidance to AI coding agents when working with code in this repository.

## Commands

```bash
# Run all tests (unit + integration)
npm test

# Run unit tests only
npm run test:unit

# Run integration tests only (requires exiftool)
npm run test:integration

# Run a single test file
node --test --experimental-test-module-mocks test/stages/link.test.js

# Run the CLI
npm start -- -s <source> -d <destination>

# Format code
npx prettier --write .
```

## Integration Test Fixtures

Pre-generated JPEG files live in `test/integration/fixtures/media/`. To add a new fixture:

```bash
# Copy the blank JPEG as a starting point
cp test/integration/fixtures/media/no-metadata.jpg test/integration/fixtures/media/new-profile.jpg

# Stamp it with metadata using exiftool
exiftool -SubSecDateTimeOriginal="2024:01:01 00:00:00+00:00" test/integration/fixtures/media/new-profile.jpg

# For GPS data
exiftool -Composite:GPSLatitude=48.8584 -Composite:GPSLongitude=2.2945 -GPSAltitude=35 -GPSAltitudeRef=0 test/integration/fixtures/media/new-profile.jpg
```

## Architecture

PixelKasten processes Google Photos Takeout exports through a multi-stage pipeline defined in `src/pipeline.js`:

1. **Scan** (`src/stages/scan.js`) - Recursively reads the source directory and categorizes files into media, metadata (`.json` sidecars), album metadata, and unsupported files.

2. **Link** (`src/stages/link.js`) - Matches media files to their JSON sidecar metadata files. Handles Google's complex filename truncation patterns (documented in `docs/takeout.md`), including truncated `-edited` suffixes and `.supplemental-metadata` variants.

3. **Dedupe** (`src/stages/dedupe.js`) - Calculates SHA-256 hashes for content-based duplicate detection, then resolves which duplicates to keep based on source type preference (album vs loose files).

4. **Reconcile** (`src/stages/reconcile.js`) - Reads existing EXIF/QuickTime metadata from disk and compares with sidecar data to determine what needs to be written.

5. **Apply** (WIP) - Takes the in-memory manifest produced by prior stages and applies the actions to files on disk.

The **manifest** is the central data structure passed between stages, with each stage enriching entries with additional properties (`json`, `dedupe`, `metadata`).

### Handlers

Format-specific metadata logic lives in `src/handlers/formats/`:

- `exif.js` - JPEG, HEIC, PNG (EXIF tags)
- `quicktime.js` - MP4, MOV (QuickTime atoms)

Each handler defines `readTags` (what to extract), `parse` (normalize to common shape), and write functions (`timestamp`, `geo`).

### External Dependencies

- **exiftool** - Metadata read/write via `src/core/exiftool.js` (spawned as subprocess)
- **execa** - Process execution for exiftool

## Core Objective

Write metadata (timestamps, geo-data) from `.json` sidecar files into corresponding media files using exiftool via Node.js child_process.

## Guiding Principles

### 1. Do Not Overwrite Existing Data

If a media file already contains the relevant native metadata, it MUST NOT be updated.

- Check for existing native timestamp/geo-data tags before writing
- Read and parse existing metadata before deciding to write

### 2. Validate Input Data

Invalid data from the `.json` sidecar must be ignored.

- If `geoData.latitude` or `geoData.longitude` are `0`, `0.0`, `null`, or `undefined`, skip geo-data entirely

### 3. Use Native Tags & Correct Formatting

Metadata MUST be written to the correct native tags for each file format, and the value MUST be formatted to that tag's standard.

- Write to correct native tags per file format (EXIF for JPEG, QuickTime for MOV, etc.)
- JSON source: `photoTakenTime.timestamp` (UTC Unix epoch), `geoData` (signed decimal lat/lon/alt)
- Handle format-specific timestamp and geo-data requirements

### 4. Be Strict on Unknown Formats

- Only process formats with explicit rules
- Skip unknown formats (e.g., `.mkv`, `.avi`)
- Report skipped files in final summary

## Development Principles

### 5. Prioritize Simplicity

- Minimize third-party dependencies
- Justify any added dependency

### 6. Ensure Testability

- Use native Node.js testing framework
- Maintain good automated test coverage

### 7. Maintain Transparency

- Log outcomes of different phases
- Report file statuses: matched, skipped (with reason), unmatched pairs

## Test Code Style

### Behavior-Focused Tests

Test names should describe observable behavior, not implementation details. Treat functions as black boxes and verify what you can observe externally.

- Good: `"should not perform disk operations when manifest is empty"`
- Bad: `"should filter out entries marked for deletion"`

### Clear Assertions

Every assertion should have a descriptive comment explaining what it verifies. Format: comment -> assertion -> blank line.

```javascript
test("should queue timestamp write when missing from disk metadata", () => {
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

### Named Imports

```javascript
import { test, describe, beforeEach, mock } from "node:test";
import { strictEqual, deepStrictEqual, ok, rejects } from "node:assert";
```

### Explicit Mock Returns

Mock implementations should use explicit return statements with block bodies:

```javascript
// Good
readMetadataMock.mock.mockImplementation(async () => {
  return new Map([["test.jpg", {}]]);
});

// Bad - implicit return
readMetadataMock.mock.mockImplementation(async () => new Map([["test.jpg", {}]]));
```

### Mock Only What's Called

Only mock functions that are actually invoked in the test path.

```javascript
// Bad - mocks parse() even though it's never called (sidecar is null)
readSidecarMock.mock.mockImplementation(async () => {
  return null;
});
handlerMock.parse.mock.mockImplementation(() => {
  return { timestamp: null };
});

// Good - only mock what's needed
readSidecarMock.mock.mockImplementation(async () => {
  return null;
});
```

## Code Style

### Always Use Braces for Control Statements

```javascript
// Good
if (!parsed) {
  continue;
}

// Bad - inline without braces
if (!parsed) continue;
```

### Use Multi-Line Object Definitions

```javascript
// Good
entry.rename = {
  status: "error",
};

// Bad - inline object
entry.rename = { status: "error" };
```
