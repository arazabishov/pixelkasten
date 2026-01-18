# PixelKasten

A Node.js script that processes media files and sidecar `.json` files from a Google Photos Takeout, writing metadata (timestamps, geo-data) from sidecars into their corresponding media files.

## Documentation

See `docs/` for detailed documentation:
- `docs/takeout.md` - Google Takeout file naming conventions and matching challenges

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
