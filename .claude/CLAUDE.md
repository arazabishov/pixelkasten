# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run all tests
npm test

# Run a single test file
node --test --experimental-test-module-mocks test/stages/link.test.js

# Run the CLI
npm start -- -s <source> -d <destination>

# Format code
npx prettier --write .
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

Write metadata from `.json` sidecar files into corresponding media files using exiftool via Node.js child_process.

## Guiding Principles

### 1. Do Not Overwrite Existing Data
- Check for existing native timestamp/geo-data tags before writing
- Read and parse existing metadata before deciding to write

### 2. Validate Input Data
- Ignore invalid sidecar data
- If `geoData.latitude` or `geoData.longitude` are `0`, `0.0`, `null`, or `undefined`, skip geo-data entirely

### 3. Use Native Tags & Correct Formatting
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
- Describe observable behavior, not implementation details
- Good: `"should not perform disk operations when manifest is empty"`
- Bad: `"should filter out entries marked for deletion"`

### Clear Assertions
- Add descriptive comment before each assertion
- Format: comment -> assertion -> blank line

### Named Imports
```javascript
import { test, describe, beforeEach, mock } from "node:test";
import { strictEqual, deepStrictEqual, ok, rejects } from "node:assert";
```

### Explicit Mock Returns
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
