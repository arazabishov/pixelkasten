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
node --test --experimental-test-module-mocks packages/core/test/stages/link.test.js

# Run the CLI
npm start -- -s <source> -d <destination>

# Format code
npx prettier --write .

# --- Python Pipeline ---

# Run Python pipeline tests
uv run pytest -v

# Run Python pipeline unit tests only
uv run pytest test/unit/ -v

# Run the full pipeline
uv run pixelkasten embed -s <source> -o <output>
uv run pixelkasten enrich -m <output>/manifest.json
uv run pixelkasten refine -m <output>/manifest.json
uv run pixelkasten caption -m <output>/manifest.json
uv run pixelkasten organize -m <output>/manifest.json
uv run pixelkasten apply -p <output>/organization.json -d <destination>
```

## Monorepo Structure

This is an npm workspaces monorepo with two packages:

- **`packages/core`** (`@pixelkasten/core`) - Core pipeline logic. No CLI dependencies. Private package.
- **`packages/cli`** (`@pixelkasten/cli`) - CLI entry point. Depends on `@pixelkasten/core`.

Shared config (ESLint, Prettier) lives at the root. Dev dependencies are at root level.

### Core Package (`packages/core`)

Contains the pipeline stages, handlers, and core utilities. All stages accept optional `logger` and `progress` via the `options` parameter, making the core independently consumable without CLI dependencies.

### CLI Package (`packages/cli`)

Contains the CLI entry point (`cli.js`), logger, progress bar, and report formatters. Wires up concrete `logger`, `progress`, and `hooks` implementations and passes them to `runPipeline()`.

### Python Package (`src/pixelkasten/`)

Python project for AI-powered photo categorization. Not an npm package — communicates with the Node.js pipeline only through JSON manifest files. Uses `uv` for dependency management and `pytest` for testing.

**Pipeline stages (run in this order):**

1. **embed** — Scan images, generate CLIP embeddings (768-dim vectors), cluster with HDBSCAN, classify with zero-shot labels. Produces `manifest.json` + `embeddings.npy`.
2. **enrich** — Read EXIF (timestamps, GPS, camera) from all images via exiftool. Reverse geocode GPS to city/region/country. Write to manifest.
3. **refine** — Fix clustering using EXIF: eject metadata-less images, split clusters at temporal gaps, merge temporally close + visually similar clusters, absorb travel noise by region, absorb GPS-less noise by visual similarity. Uses home location inference to avoid over-absorbing.
4. **caption** — Send representative images to a local VLM (LLaVA/Qwen) via Ollama for human-readable captions.
5. **organize** — Feed cluster summaries (captions, tags, dates, locations) to a local text LLM via Ollama. LLM proposes album names. Code builds directory paths from timestamps. Writes `organization.json`.
6. **apply** — Copy files to the proposed directory structure. Originals untouched.

**Prerequisites:** Python 3.12+, uv, exiftool (`brew install exiftool`), Ollama with vision + text models.

**Key architecture decisions:**

- Manifest-driven: each stage reads, enriches, and writes back `manifest.json`
- EXIF read for all images (not just representatives) to enable temporal refinement
- Region-level geocoding (state/province) for hierarchical location matching
- Home location inferred from most frequent region — prevents over-absorbing local photos
- Location outlier filtering (< 10%) prevents transit GPS from polluting album names

**Code conventions:**

- All public functions should have full type annotations
- Imports for heavy dependencies (torch, sklearn) are deferred inside CLI commands
- Tests use pytest; fixtures in `test/fixtures/media/`

## Integration Test Fixtures

Pre-generated JPEG files live in `packages/core/test/integration/fixtures/media/`. To add a new fixture:

```bash
# Copy the blank JPEG as a starting point
cp packages/core/test/integration/fixtures/media/no-metadata.jpg packages/core/test/integration/fixtures/media/new-profile.jpg

# Stamp it with metadata using exiftool
exiftool -SubSecDateTimeOriginal="2024:01:01 00:00:00+00:00" packages/core/test/integration/fixtures/media/new-profile.jpg

# For GPS data
exiftool -Composite:GPSLatitude=48.8584 -Composite:GPSLongitude=2.2945 -GPSAltitude=35 -GPSAltitudeRef=0 packages/core/test/integration/fixtures/media/new-profile.jpg
```

## Architecture

PixelKasten processes Google Photos Takeout exports through a multi-stage pipeline defined in `packages/core/src/pipeline.js`:

1. **Scan** (`packages/core/src/stages/scan.js`) - Recursively reads the source directory and categorizes files into media, metadata (`.json` sidecars), album metadata, and unsupported files.

2. **Link** (`packages/core/src/stages/link.js`) - Matches media files to their JSON sidecar metadata files. Handles Google's complex filename truncation patterns (documented in `docs/takeout.md`), including truncated `-edited` suffixes and `.supplemental-metadata` variants.

3. **Dedupe** (`packages/core/src/stages/dedupe.js`) - Calculates SHA-256 hashes for content-based duplicate detection, then resolves which duplicates to keep based on source type preference (album vs loose files).

4. **Reconcile** (`packages/core/src/stages/reconcile.js`) - Reads existing EXIF/QuickTime metadata from disk and compares with sidecar data to determine what needs to be written.

5. **Rename** (`packages/core/src/stages/rename.js`) - Builds target file paths from timestamps using the naming scheme (`YYYY/MM - Mon/yyyymmdd-hhmmss.ext`). Handles album subdirectories and filename collisions.

6. **Apply** (`packages/core/src/stages/apply.js`) - Takes the in-memory manifest produced by prior stages and applies the actions to files on disk (copy files, write metadata via exiftool).

The **manifest** is the central data structure passed between stages, with each stage enriching entries with additional properties (`json`, `dedupe`, `metadata`, `rename`).

The pipeline accepts a `hooks` object for inter-stage reporting. The CLI provides hooks that print tables; other consumers (e.g., Electron) can provide hooks that send IPC messages.

### Handlers

Format-specific metadata logic lives in `packages/core/src/handlers/formats/`:

- `exif.js` - JPEG, HEIC, PNG (EXIF tags)
- `quicktime.js` - MP4, MOV (QuickTime atoms)

Each handler defines `readTags` (what to extract), `parse` (normalize to common shape), and write functions (`timestamp`, `geo`).

### External Dependencies

- **exiftool** - Metadata read/write via `packages/core/src/core/exiftool.js` (spawned as subprocess)
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

## Python Test Code Style

Tests use `pytest`. Fixtures live in `test/fixtures/media/` (copies of the Node.js fixtures).

```python
# Use descriptive class + method names
class TestSplitByTemporalGaps:
    def test_splits_cluster_at_48h_gap(self):

# Create minimal inline test data per test (don't over-rely on shared fixtures)
# Use numpy random with fixed seed for deterministic embeddings
rng = np.random.RandomState(42)
```

## Consolidation Notes

The long-term plan (see `spec/architecture.md`) is to consolidate the Node.js Takeout pipeline into the Python project, creating a single tool. Key considerations:

- **Port the test suite first**, then port the implementation
- The `link` stage (`packages/core/src/stages/link.js`) is the most complex — it encodes Google Takeout filename truncation edge cases documented in `docs/takeout.md`
- The `rename` stage uses `Intl.DateTimeFormat` with `month: "long"` — the AI pipeline dropped month directories entirely (files go directly under `YYYY/`)
- Both pipelines share the same exiftool subprocess pattern for metadata reading
- GPS validation rules are aligned: both reject `(0, 0)` as Google's placeholder
- Timestamp handling: Node.js strips timezone offsets; Python will be unified to strip-offsets-early in Phase 1
