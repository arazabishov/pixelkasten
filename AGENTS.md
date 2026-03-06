# AGENTS.md

The core objective of this tool is to help organize a photo library. For Google Takeout exports, it matches media files to their JSON sidecars, deduplicates, and embeds metadata (timestamps, geo-data) into files using exiftool. For any photo library, Takeout or not, it can automatically discover and name albums using local AI (CLIP + Ollama). Both capabilities work independently or together.

## Guiding principles

### 1. Correctness and transparency

It is critical that the tool updates the correct media files with the correct metadata and never loses user data. Changes must only be applied to copies. Original source files are never modified in place. If the tool has low confidence in any change, or if errors occur during processing, this must be communicated to the user.

#### 1.1. Do not overwrite existing data

If a media file already contains the relevant native metadata, it MUST NOT be updated. Always read and parse existing metadata before deciding to write.

#### 1.2. Validate input data

Invalid data from the `.json` sidecar must be ignored. For example, if `geoData.latitude` or `geoData.longitude` are `0`, `0.0`, or `None`, skip geo-data entirely. Sidecar rejects either-zero (Google placeholder); disk EXIF rejects only both-zero.

#### 1.3. Use native tags & correct formatting

Metadata MUST be written to the correct native tags for each file format (EXIF for JPEG, QuickTime for MOV, etc.), and the value MUST be formatted to that tag's standard. The JSON sidecar provides `photoTakenTime.timestamp` (UTC Unix epoch) and `geoData` (signed decimal lat/lon/alt).

#### 1.4. Maintain transparency

Log outcomes of different phases and report file statuses: matched, skipped (with reason), unmatched pairs.

### 2. Prioritize simplicity

Minimize third-party dependencies. Any added dependency should be justified.

### 3. Ensure testability

All code changes must be covered by unit and/or integration tests. Tests must be reliable, reproducible, and fast. No dependencies on long-running tools like LLMs or VLMs. Mock external services where needed.

### 4. Privacy

User data must never leave the device. All processing, including AI-powered categorization, happens offline using local models. No cloud API calls, no telemetry, no network requests.

## Architecture

The project is a uv workspaces monorepo: `packages/core` contains pipeline logic, stages, and AI album discovery with no UI dependencies, while `packages/cli` is a thin typer + rich consumer that wires up progress, hooks, and reporting.

A simple `core/` and `cli/` directory split inside one package would not be enough. uv workspaces enforce the dependency boundary at install time, so core can never accidentally import typer or rich. This matters because the CLI should not be the only frontend. A web UI or desktop app should be able to import core directly without pulling in CLI dependencies.

### Data pipeline

Processing photos requires multiple steps (scanning, matching sidecars, deduplicating, writing metadata, etc.) that must happen in order, where each step builds on the results of the previous one. The pipeline tracks all work in a single in-memory manifest that each stage reads from and enriches. Stages are decoupled: each reads fields that upstream stages wrote, without needing to know about the stages themselves. No stage performs side effects. File copies and metadata writes are deferred to the final apply stage. This is what makes `--dry-run` possible (just skip apply), makes the pipeline safe to retry (a failed stage leaves disk untouched), and keeps tests simple (assert on manifest state, no filesystem mocking).

The pipeline is a linear sequence where flags control which stages run. Sidecar matching runs automatically when JSON metadata is present. `--discover` enables AI album discovery. Workspace caching (`-w`) persists `manifest.json` after init stages and `embeddings.npy` after CLIP embedding, the two most expensive operations. Caching them lets you iterate on downstream stages (clustering parameters, LLM prompts) without re-doing the slow work. For the exact execution sequence and stage wiring, see `pipeline.py`.

Two areas are complex enough to have their own documentation. The link stage (sidecar matching) deals with Google Takeout's unpredictable filename truncation, collision markers, and edited variants; see `docs/takeout.md` for the full breakdown. Album discovery is effectively a sub-pipeline with its own stages (embedding, clustering, classification, captioning, album naming) orchestrated by `stages/discovery/`.

### Handlers

Different media formats store metadata in incompatible ways: EXIF tags for images (JPEG, HEIC, PNG) and QuickTime tags for video (MP4, MOV). The tag names differ, the value formats differ, and the GPS encoding differs. Handlers encapsulate all of this behind a common interface (`read_tags`, `parse()`, `timestamp()`, `geo()`), so pipeline stages work with metadata without knowing the underlying format. Adding a new format means registering a new handler; nothing else in the pipeline changes. Formats without an explicit handler (e.g., `.mkv`, `.avi`) are skipped and reported in the final summary.

## Dependencies

Python 3.12+ and uv are required to run the project. exiftool must be installed separately for metadata read/write operations. Ollama with vision and text models is only needed when running with `--discover`. All Python dependencies, including ruff and pytest, are managed by uv. Run `uv sync` to install them.

## Useful commands

```bash
# CLI usage and all available options
uv run pixelkasten --help

# Run all tests
uv run pytest -v

# Lint
uv run ruff check packages/

# Format check
uv run ruff format --check packages/
```

## Code conventions

### Style

#### Clarity over conciseness

Avoid inline ternaries and dense one-liners when a local variable would be more readable:

```python
# Bad — hard to parse
return {
    "timestamp": photo_taken_time.get("timestamp") if photo_taken_time else None,
    "geo": geo,
}

# Good — explicit and readable
timestamp = photo_taken_time.get("timestamp") if photo_taken_time else None
return {"timestamp": timestamp, "geo": geo}
```

#### Type annotations and imports

All public functions should have full type annotations. Always use proper imports for type annotations — never use string annotations (e.g., `"PipelineOptions"`) as a workaround. If an import would cause a circular dependency, fix the dependency structure instead. Imports for heavy dependencies (torch, sklearn, ollama) are deferred inside functions. This is not just about startup speed. A user running without `--discover` should not need torch installed at all. Deferred imports make optional dependencies truly optional.

#### Comments and docstrings

Comments should explain *why*, not *what*. Don't restate what the code already says. Keep comments as single-line inline comments above the relevant line. Docstrings should focus on design intent, invariants, and non-obvious constraints — not mechanical parameter/return descriptions that duplicate the type annotations.

#### None handling

Never coerce `None` to a default value with `or` (e.g., `destination = options.destination or ""`). Handle `None` explicitly — either check and branch, or assert non-`None` when the pipeline guarantees the value is set.

#### os.path only — no pathlib

All path manipulation MUST use `os.path`. Do not use `pathlib.Path` anywhere in the codebase. The link stage requires `os.path` because pathlib normalizes double extensions (`.MP.jpg`) and duplicate markers `(1)`, which breaks Takeout filename parsing. All other stages use `os.path` for consistency. File paths are represented as plain strings throughout the pipeline — in `ManifestEntry`, in function signatures, and in return values.

#### Typing at boundaries

Stages are the type boundary, not individual functions within a stage. Internal helpers (exiftool, sidecar, handlers) can freely use raw dicts — they never leave the stage. But when a stage writes to `ManifestEntry`, it must use the typed structures from `manifest.py` (e.g., `Geo`, `Metadata`, `Dedupe`). This keeps typing focused where it matters (the manifest contract between stages) without fighting Python's dynamic nature inside stage internals.

### Testing

Tests use pytest. Test names should describe observable behavior, not implementation details. Treat functions as black boxes and verify what you can observe externally (e.g., `test_does_not_perform_disk_operations_when_manifest_is_empty`, not `test_filters_out_entries_marked_for_deletion`).

Every assertion should have a descriptive comment explaining what it verifies:

```python
def test_queues_timestamp_write_when_missing_from_disk(self):
    manifest = [_entry("/tmp/image.jpg", "/tmp/image.json")]
    reconcile(manifest, make_options())

    # Verify entry was marked for processing
    assert manifest[0].metadata.status == Status.PROCESSED

    # Verify at least one tag was queued for writing
    assert len(manifest[0].metadata.write_tags) >= 1

    # Verify timestamp was prepended to dates
    assert manifest[0].metadata.dates[0] == "2023-01-01T12:00:00"
```

Keep test setup minimal. If the code under test doesn't reach a function, don't mock it.
