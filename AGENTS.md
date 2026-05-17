# AGENTS.md

The core objective of this tool is to help organize a photo library. The `pixelkasten init` command normalizes a messy source — either a Google Takeout export (`--from-takeout`, matches JSON sidecars and writes timestamps + geo into copies via exiftool) or a flat archive of media files (`--from-archive`) — into a **working library**: a flat directory of GUID-named copies plus per-asset sidecars under `.pixelkasten/`. From there, the rest of the toolbox (`enrich`, `caption`, `similar`, `cluster`, `propose`, `apply --to`) lets a user (or an LLM agent driving the toolbox) enrich sidecars with location/embeddings/captions, query the library, decide album assignments, and export a final organized photo library. See `pixelkasten-plans/full-redesign.md` for the original design and `pixelkasten-plans/toolbox-extensions.md` / `toolbox-review.md` for ongoing work.

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

The project is a uv workspaces monorepo: `packages/core` contains pipeline logic, stages, and per-asset tools with no UI dependencies, while `packages/cli` is a thin typer + rich consumer that wires up progress, hooks, and reporting.

A simple `core/` and `cli/` directory split inside one package would not be enough. uv workspaces enforce the dependency boundary at install time, so core can never accidentally import typer or rich. This matters because the CLI should not be the only frontend. A web UI or desktop app should be able to import core directly without pulling in CLI dependencies.

### Data pipeline

Processing photos requires multiple steps (scanning, matching sidecars, deduplicating, reading EXIF, grouping, emitting) that must happen in order. The pipeline tracks all work in a single in-memory manifest that each stage reads from and enriches. Stages are decoupled: each reads fields that upstream stages wrote, without needing to know about the stages themselves. Only the final `emit` stage touches the filesystem (and reconcile reads it). This is what makes `--dry-run` possible (just skip emit), makes the pipeline safe to retry (a failed stage leaves disk untouched), and keeps tests simple (assert on manifest state).

```
scan → link → dedupe → reconcile → group → emit
```

- `scan` walks the source and partitions files into media, metadata (Takeout sidecars), and album marker files.
- `link` matches each media file to its Google Takeout sidecar (Takeout mode only). Archive mode short-circuits: every entry is loose with no sidecar.
- `dedupe` hashes files and resolves duplicates. Takeout mode uses `--prefer album/loose`; archive mode keeps the lex-smallest source path.
- `reconcile` reads disk EXIF, compares with sidecar data (when present), and queues `write_tags` for any metadata missing from disk. Always runs.
- `group` assigns a `group_id` (uuid4 hex) to each keeper. Members of one logical asset (Live Photo image + video, edited variant) share a `group_id`. Takeout mode buckets by shared sidecar; archive mode buckets by `(dirname, stripped_stem)`.
- `emit` writes the working library: `<dst>/<group_id>.<ext>` for the file (with `_2`, `_3`, … on same-extension collision within a group), `<dst>/.pixelkasten/<filename>.pk.json` for the sidecar. In Takeout mode, queued `write_tags` are applied via exiftool to the destination copy. Unsupported file formats are skipped (not emitted).

`--write-manifest` dumps `manifest.json` to the destination as a debugging artifact. Each run is a full run: there is no checkpoint or resume.

The link stage is complex enough to have its own documentation; see `docs/takeout.md` for Google Takeout's filename-truncation quirks.

### Working library layout

```
<destination>/
  3f2a1b8c.heic                          # group A member
  3f2a1b8c.mov                           # group A member (shared stem)
  9d7e4f02.jpg                           # singleton
  ...
  .pixelkasten/
    3f2a1b8c.heic.pk.json
    3f2a1b8c.mov.pk.json
    9d7e4f02.jpg.pk.json
  report.csv                             # per-file CSV report
```

### Sidecar schema

The sidecar grows across the lifecycle. Each command writes specific fields; downstream commands consume them.

At **init** time, every `.pk.json` carries exactly three fields:

```json
{
  "dates": ["2024-06-01T14:30:22"],
  "geo": {"latitude": 52.52, "longitude": 13.40, "altitude": 34.0},
  "album": "Wedding 2019"
}
```

- `dates`: list from `entry.metadata.dates`; `[]` when there's no metadata.
- `geo`: object or `null`.
- `album`: source-folder name for Takeout entries; `null` for loose entries and all archive-mode entries.

Subsequent commands add fields without modifying the originals:

| Field | Written by | Shape |
|---|---|---|
| `location` | `enrich` (reverse geocode) | `{"name": "Berlin, Germany", "region": "Berlin", "country": "DE"}` or `null` |
| `caption` | `caption` (VLM) | one short string, or absent |
| `proposed_album` | `propose` | string the agent chose, or absent |

Fields can be absent. Consumers should tolerate missing keys (use `jq`'s `// empty` or `// null`).

### The toolbox

Beyond `init`, the CLI exposes a small set of commands that the agent (or a human) can use to enrich, query, and export the working library:

| Command | Purpose | Writes to |
|---|---|---|
| `pixelkasten enrich <library>` | Bulk reverse-geocode + CLIP embed every asset. Idempotent — re-runs skip already-enriched files. | `.pixelkasten/*.pk.json`, `.pixelkasten/embeddings.npy` |
| `pixelkasten caption <path>` | On-demand VLM caption for one asset. Cached in the sidecar; `--force` to re-caption. | One `.pk.json` |
| `pixelkasten similar <path> [--k N]` | k-NN over `embeddings.npy` by cosine. | Stdout (JSON) |
| `pixelkasten cluster [paths…]` | HDBSCAN over a scoped slice of embeddings. Reads paths from args or stdin. | Stdout (JSON) |
| `pixelkasten propose <path> <album>` / `--clear` | Write `proposed_album` to the file's sidecar and to every group sibling. | Sidecars |
| `pixelkasten apply <library> --to <dst>` | Export the working library to an organized photo library. Reads sidecars, resolves albums by fallback chain (`proposed_album → album → date folder → Unsorted/`), copies into year/album folders. | Files at `<dst>` |

### Export library layout

`apply` writes the user-facing organized photo library:

```
<dst>/
  2024/
    20240615-Wedding/                # album: <YYYYMMDD>-<sanitized_name>
      20240615-143022.heic
      20240615-143022.mov            # group sibling, same timestamp, diff ext
    20240620-100530.jpg              # loose file in year folder
    20240620-100530-1.jpg            # -N suffix on collision (unrelated assets)
  Unsorted/
    9d7e4f02.jpg                     # no parseable date -> keep GUID name
```

The export is regenerable from the working library + sidecar decisions. The working library is never modified by `apply`.

### Agent integration

A sample agent skill file lives at `docs/SKILL.md`. It is not auto-installed — users who want to drive pixelkasten from Claude Code copy or adapt it into their own agent configuration. The agent reads sidecars (via `jq`), runs the toolbox commands on demand, and writes `proposed_album` via `propose`. See `pixelkasten-plans/full-redesign.md` for the full design.

### Handlers

Different media formats store metadata in incompatible ways: EXIF tags for images (JPEG, HEIC, PNG) and QuickTime tags for video (MP4, MOV). The tag names differ, the value formats differ, and the GPS encoding differs. Handlers encapsulate all of this behind a common interface (`read_tags`, `parse()`, `timestamp()`, `geo()`), so pipeline stages work with metadata without knowing the underlying format. Adding a new format means registering a new handler; nothing else in the pipeline changes. Formats without an explicit handler (e.g., `.mkv`, `.avi`) are skipped and reported in the final summary.

## Dependencies

Python 3.12+ and uv are required to run the project. The following must be installed separately at the OS level:

- **exiftool** — required for all runs. Used by `reconcile` (read EXIF) and `emit` (write EXIF in Takeout mode). Install: `brew install exiftool`.
- **ffmpeg + ffprobe** — required when `enrich` or `caption` touches videos (`.mp4`, `.mov`). Used to extract N evenly-sampled frames. Install: `brew install ffmpeg`.
- **Ollama** with a vision model (default: `gemma4:e4b`) — required only for `caption`. Run `ollama serve` and `ollama pull gemma4:e4b` once.

All Python dependencies (open-clip-torch, scikit-learn, numpy, ollama, reverse_geocoder, pillow-heif, ruff, pytest) are managed by uv. Run `uv sync` to install them. Note that CLIP weights (~890MB) and the reverse_geocoder data file are downloaded on first use and cached locally; thereafter the toolbox operates offline.

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

All public functions should have full type annotations. Always use proper imports for type annotations — never use string annotations (e.g., `"PipelineOptions"`) as a workaround. If an import would cause a circular dependency, fix the dependency structure instead. Imports for heavy dependencies (torch, sklearn, ollama) are deferred inside functions. This is not just about startup speed. A user running only `init` and `apply` should not pay the cost of loading CLIP or the Ollama client; those are reserved for `enrich`, `caption`, `similar`, and `cluster`. Deferred imports keep the lightweight paths lightweight.

#### Comments and docstrings

Comments should explain *why*, not *what*. Don't restate what the code already says. Keep comments as single-line inline comments above the relevant line. Docstrings should focus on design intent, invariants, and non-obvious constraints — not mechanical parameter/return descriptions that duplicate the type annotations.

#### None handling

Never coerce `None` to a default value with `or` (e.g., `destination = options.destination or ""`). Handle `None` explicitly — either check and branch, or assert non-`None` when the pipeline guarantees the value is set.

#### os.path only — no pathlib

All path manipulation MUST use `os.path`. Do not use `pathlib.Path` anywhere in the codebase. The link stage requires `os.path` because pathlib normalizes double extensions (`.MP.jpg`) and duplicate markers `(1)`, which breaks Takeout filename parsing. All other stages use `os.path` for consistency. File paths are represented as plain strings throughout the pipeline — in `ManifestEntry`, in function signatures, and in return values.

#### Typing at boundaries

Stages are the type boundary, not individual functions within a stage. Internal helpers (exiftool, sidecar, handlers) can freely use raw dicts — they never leave the stage. But when a stage writes to `ManifestEntry`, it must use the typed structures from `manifest.py` (e.g., `Geo`, `Metadata`, `Dedupe`). This keeps typing focused where it matters (the manifest contract between stages) without fighting Python's dynamic nature inside stage internals.

#### Stage structure

Each mutating stage follows the same shape: filter keepers, iterate entries, try/except per entry, set the stage's field on `ManifestEntry`. The try body should be extracted into a private helper that returns the result type — this keeps the main function flat and the per-entry logic testable. See `_resolve` in reconcile and `_emit_entry` in emit for examples.

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
