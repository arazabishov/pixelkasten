# Spec: Unified PixelKasten Pipeline (Python Rewrite)

## Context

PixelKasten currently exists as two separate tools:

1. **Node.js Takeout pipeline** (`packages/core/` + `packages/cli/`) — processes Google Photos Takeout exports: links sidecar metadata, deduplicates, embeds EXIF, renames, and copies files. Rigorously tested (213 tests). Production-quality.

2. **Python AI pipeline** (`ai/`) — auto-organizes unstructured photo libraries using CLIP embeddings, HDBSCAN clustering, VLM captioning, and LLM-driven album naming. Validated on real libraries (113 tests).

Both tools solve parts of the same problem: organizing a photo archive. The split across two languages makes the codebase harder to maintain and prevents sharing infrastructure (rename, apply, dedupe, EXIF handling). The plan is to consolidate into a single Python tool.

## Design Decisions

### Single command

One command does everything. No subcommands, no multi-step workflows for users to manage.

```bash
pixelkasten -s ~/photos -d ~/organized [--catalog] [--dry-run] [-w ./workspace]
```

The tool auto-detects whether the source is a Google Takeout export or a plain archive and runs the appropriate pipeline.

### In-memory by default, workspace for caching

The pipeline runs entirely in memory. No manifest files, no workspace directories. The common case is one shot: point at photos, get organized output.

The `-w ./workspace` flag is opt-in for power users who want to iterate on AI catalog settings without re-running expensive CLIP embedding (~15 min for 5K images). The workspace caches two things:
- `manifest.json` — init-layer data (scan results, EXIF, sidecar links)
- `embeddings.npy` — CLIP embeddings (~30MB for 10K images)

Everything else re-runs on re-invocation (clustering, captioning, renaming — all fast).

Implementation cost: two `if` statements and two file writes. No state tracking, no `completed_stages`.

### Unified manifest

One in-memory dict structure for both pipelines. Fields that only one pipeline uses are simply absent in the other. No separate schemas.

### Source-agnostic rename

The rename stage reads `source.type`, `source.name`, and `metadata.dates`. It does not know whether album info came from Google Takeout metadata or an LLM. One rename implementation for both pipelines.

### Auto-detection

Presence of `.json` sidecar files alongside media files triggers takeout mode. Otherwise, archive mode. Override with `--takeout` / `--no-takeout`.

### "Catalog" not "AI"

The AI album discovery substage is called `--catalog`. The word "AI" never appears in the CLI. The user sees:
- Default behavior (takeout: uses existing albums; archive: uses date-only organization)
- `--catalog` to enable AI-powered album discovery

### Timezone handling

Strip timezone offsets early (matching Node.js behavior). `2024:03:21 10:24:10-05:00` becomes `2024-03-21T10:24:10`. Filenames represent wall-clock time, not UTC.

### Drop month directories

Directory structure: `YYYY/yyyymmdd-hhmmss.ext` for loose files, `YYYY/yyyymmdd - Album Name/yyyymmdd-hhmmss.ext` for albums. No `MM - Mon/` layer.

## Porting Conventions

The Node.js code is the behavioral spec (via its tests), but not the implementation spec. Port the *what*, not the *how*. The following conventions prevent non-idiomatic Python.

### Use `datetime` objects, not dicts

The Node.js code passes dates as `{year, month, day, hour, minute, second}` dicts and manually compares/formats components throughout. In Python:

- `normalize_disk_date()` uses regex to strip timezone offsets (correct — deliberately not parsing the TZ), but returns a `datetime` object, not a string.
- `parse_photo_taken_time()` uses `datetime.utcfromtimestamp()`.
- Date comparison uses `<` on `datetime` objects (replaces `isEarlierDate` component-by-component comparison).
- Date formatting uses `strftime` (replaces manual `pad2` + string interpolation).

### Use dataclasses for structured data

The Node.js manifest is a mutable list of plain objects, enriched stage-by-stage: `entry.metadata = { ... }`, `entry.rename = { ... }`. Direct port produces untyped dicts with no discoverability.

Instead:

- `ManifestEntry` is a `@dataclass` with `Optional` fields for each stage's output.
- Each stage's output is its own small dataclass (`DedupeResult`, `MetadataResult`, `RenameResult`, etc.).
- Stages still mutate entries in place (`entry.metadata = MetadataResult(...)`), but the types are explicit.
- Filename parsing helpers (`media()`, `sidecar()` in link) return `NamedTuple` or frozen dataclasses, not dicts.

### Use Protocol for handlers

The Node.js handler objects are plain dicts with `readTags`, `parse`, `timestamp`, `geo` properties. In Python, define a `Protocol`:

```python
class Handler(Protocol):
    read_tags: list[str]
    def parse(self, raw: dict) -> ParsedMetadata: ...
    def timestamp(self, data: str) -> list[str]: ...
    def geo(self, data: GeoData) -> list[str]: ...
```

Concrete handlers (EXIF, QuickTime) implement the protocol. The registry remains a `dict[str, Handler]`.

### Use `Optional` defaults over `None` checks

The Node.js code uses optional chaining (`entry.metadata?.dates`) extensively. In Python, prefer dataclass defaults that eliminate `None` checks: `dates: list[str] = field(default_factory=list)`. Check for empty (`if not entry.dates`) rather than `if entry.dates is not None`.

### Don't port `Promise.all`

`reconcile.js` uses `Promise.all(batch.map(async ...))` for concurrent sidecar reads within batches. This pattern doesn't translate to Python — the concurrency was marginal anyway (disk I/O is sequential, parsing is trivial). Use a simple `for` loop. If sidecar reads become a bottleneck, use `concurrent.futures.ThreadPoolExecutor`.

### Use `pathlib` for path construction, not decomposition

- **Rename/apply** (building target paths): use `pathlib.Path` / `/` operator. This is where Python's path handling is genuinely better.
- **Link stage** (decomposing Google Takeout filenames): use `os.path` string operations. `pathlib` silently normalizes double extensions (`.MP.jpg`), duplicate markers `(1)`, and other patterns that the link stage must preserve exactly.

## CLI Interface

```bash
pixelkasten -s <source> -d <destination>
    [--catalog]            # AI album discovery (default: ON for archives, OFF for takeout)
    [--skip-catalog]       # explicitly disable catalog for archives
    [--skip-dedupe]        # skip SHA-256 deduplication
    [--skip-caption]       # catalog without VLM captions (uses tags + EXIF only)
    [--skip-refine]        # catalog without temporal cluster refinement
    [--skip-embed]         # takeout: don't write sidecar metadata into files
    [--dry-run]            # compute plan, print summary, don't copy files
    [--takeout]            # force takeout mode (override auto-detection)
    [--no-takeout]         # force archive mode
    [-w <workspace>]       # persist init data + embeddings for iteration
    [--rescan]             # invalidate cached workspace, re-scan source
```

### Workspace iteration

```bash
# First run — full pipeline
pixelkasten -s ~/photos -d ~/organized --catalog -w ./ws

# Re-run with different LLM — embeddings cached, only clustering+naming re-run
pixelkasten -w ./ws --model gemma3:12b

# Preview before applying
pixelkasten -w ./ws --dry-run

# Source changed
pixelkasten -w ./ws --rescan
```

When `-w` is provided, `-s` and `-d` are remembered from the first run.

### Status / report

```bash
pixelkasten status -w ./workspace [--format csv]
```

Read-only inspection of a workspace manifest. Replaces auto-generated CSV reports.

## Pipeline Architecture

Two internal pipelines sharing stages:

### Takeout pipeline (auto-detected or `--takeout`)

```
scan (takeout) → link → reconcile → dedupe → rename → apply
```

- **scan**: categorize files (media, json sidecars, album metadata, ignored). Read EXIF from all media.
- **link**: match media files to `.json` sidecar metadata. Handles Google's filename truncation.
- **reconcile**: compare disk EXIF with sidecar data, queue `write_tags` for missing metadata.
- **dedupe**: SHA-256 hash, mark duplicates (prefer album over loose).
- **rename**: compute target paths from timestamps + album info.
- **apply**: copy files, write metadata via exiftool.

### Organize pipeline (archive mode, or takeout + `--catalog`)

```
scan (archive) → exif-read → dedupe → embed → cluster → classify → refine → caption → propose → rename → apply
```

- **scan**: discover media files. Read EXIF from all media.
- **exif-read**: reverse geocode GPS coordinates.
- **dedupe**: SHA-256 hash, mark duplicates.
- **embed**: CLIP ViT-L/14 embeddings (768-dim), batched.
- **cluster**: HDBSCAN on cosine distance.
- **classify**: zero-shot labels (scene, event, subject).
- **refine**: temporal split/merge, location-based noise absorption.
- **caption**: VLM captioning of cluster representatives via Ollama.
- **propose**: LLM album naming via Ollama. Writes `source.type = "album"` and `source.name` onto manifest entries.
- **rename**: same rename stage as takeout (source-agnostic).
- **apply**: copy files (no metadata embedding for archive mode).

### How propose feeds rename

Before propose:
```python
{"path": "/photos/IMG_001.jpg", "source": {"type": "loose"}, "metadata": {"dates": ["2024-07-15T14:30:00"]}}
```

After propose (LLM assigns album):
```python
{"path": "/photos/IMG_001.jpg", "source": {"type": "album", "name": "Beach Vacation"}, "metadata": {"dates": ["2024-07-15T14:30:00"]}}
```

Rename sees `source.type == "album"`, uses `metadata.dates[0]` for the date prefix, produces:
```
2024/20240715 - Beach Vacation/20240715-143000.jpg
```

### Workspace caching points

```
scan → exif-read → link → reconcile     ← SAVE manifest.json to workspace (if -w)
  → dedupe → [embed ← SAVE embeddings.npy] → cluster → ... → rename → apply
```

On re-run with workspace: load manifest.json (skip init stages), load embeddings.npy (skip embedding). Everything else re-runs.

## Manifest Schema

Single in-memory dict. Fields marked (takeout) or (catalog) are absent in the other pipeline.

```python
{
    "version": 1,
    "mode": "takeout" | "archive",

    # Catalog top-level (absent in takeout-only)
    "embeddings_file": "embeddings.npy",
    "clusters": {
        "0": {"size": 5, "captions": [...], "top_tags": [...], "date_range": {...}, ...}
    },

    "entries": [
        {
            "path": "/source/photo.jpg",

            "source": {
                "type": "album" | "loose",
                "name": "Trip to Japan"       # Google album name OR LLM-proposed name
            },

            # (takeout) Sidecar match info
            "sidecar": {
                "path": "/source/photo.json",
                "confidence": 3
            },

            # Shared: deduplication
            "dedupe": {
                "hash": "sha256...",
                "status": "keep" | "delete" | "error"
            },

            # Shared: metadata
            "metadata": {
                "status": "processed" | "noop" | "skipped" | "error",
                "dates": ["2024-03-21T10:24:10", ...],
                "geo": {"latitude": 48.8, "longitude": 2.29, "altitude": 35},
                "write_tags": [...]           # (takeout) exiftool args to embed
            },

            # (catalog) AI-specific
            "cluster": 7,
            "tags": [{"name": "scene:beach", "score": 0.31}],
            "is_representative": true,
            "caption": "A beach scene...",

            # Shared: rename output
            "rename": {
                "status": "processed" | "error",
                "target_path": "2024/20240321 - Vacation/20240321-102410.jpg"
            },

            # Shared: apply output
            "apply": {
                "status": "copied" | "embedded" | "error",
                "target_path": "/dest/2024/20240321 - Vacation/20240321-102410.jpg"
            }
        }
    ]
}
```

## Directory Naming Scheme

No month directories. Albums sort chronologically via date prefix.

```
destination/
  2024/
    20240301-133245.jpg                        # loose file
    20240301-133245-1.jpg                      # collision
    20240715 - Beach Vacation/                 # album
      20240715-143000.jpg
      20240716-091200.jpg
    20241231 - New Year Party/
      20241231-230000.jpg
      20250101-001500.jpg
  Unsorted/                                    # (catalog) no EXIF timestamp
    IMG-20161115-WA0000.jpg
```

Album date prefix uses the earliest date among album members. Collision handling: `-1`, `-2`, `-3` suffix before extension.

## Project Structure (Target)

```
src/
  pixelkasten/                    # core library (no UI deps)
    __init__.py
    cli.py                        # AI pipeline CLI (legacy, replaced by unified CLI in Phase 6)
    pipeline.py                   # unified orchestrator (both modes)
    core/                         # shared utilities
      __init__.py
      datetime.py                 # normalize_disk_date, parse_iso_date, parse_photo_taken_time
      exiftool.py                 # subprocess wrapper (read + write)
      sidecar.py                  # Google sidecar JSON parsing
      handlers.py                 # EXIF + QuickTime handler registry
      manifest.py                 # can_keep(), report generation
      exif.py                     # AI pipeline EXIF reading + reverse geocoding
    stages/                       # pipeline stages
      __init__.py
      # Takeout stages
      scan.py                     # file discovery (scan + scan_takeout)
      link.py                     # sidecar matching (os.path, NOT pathlib)
      dedupe.py                   # SHA-256 dedup
      reconcile.py                # EXIF vs sidecar comparison
      # Catalog stages (moved from ai/)
      embed.py                    # CLIP embeddings
      cluster.py                  # HDBSCAN clustering
      classify.py                 # zero-shot classification
      refine.py                   # temporal cluster refinement
      caption.py                  # VLM captioning via Ollama
      organize.py                 # LLM album naming (becomes propose.py in Phase 6)
      # Shared stages
      rename.py                   # target path computation
      apply.py                    # file copy + metadata embed
  pixelkasten_cli/                # CLI entry point
    __init__.py
    main.py                       # re-exports app from cli.py
test/
  unit/
    core/                         # mirrors src/pixelkasten/core/
      test_datetime.py
      test_sidecar.py
      test_handlers.py
      test_exiftool.py
      test_manifest.py
      test_exif_parsing.py
    stages/                       # mirrors src/pixelkasten/stages/
      test_scan.py
      test_scan_takeout.py
      test_link.py                # the crown jewels (56 tests)
      test_dedupe.py
      test_reconcile.py
      test_rename.py
      test_apply.py
      test_cluster.py
      test_classify.py
      test_refine.py
      test_organize_builders.py
  integration/                    # cross-cutting, stays flat
    test_takeout_pipeline.py
    test_exif_integration.py
    test_pipeline_integration.py
  fixtures/
    media/                        # 4 shared JPEGs (identical to Node.js suite)
```

## Implementation Phases

### Phase 0: Project Scaffolding

Move existing AI code into the new package layout. No logic changes.

**What happens:**
- Create `src/pixelkasten/` and `src/pixelkasten_cli/`
- Move `ai/src/pixelkasten_ai/*.py` into `src/pixelkasten/`
- Move `ai/test/` into `test/`
- Create root `pyproject.toml` (replaces `ai/pyproject.toml`)
- Delete `ai/` entirely (no backward-compat shim — nobody depends on `pixelkasten-ai`)

**Key files:**
- `pyproject.toml` (new, root level)
- `src/pixelkasten/__init__.py` (new)
- `src/pixelkasten_cli/main.py` (new, re-exports existing AI CLI commands)

**Verify:** `uv run pytest -v` passes all existing AI tests in the new location.

**Size:** ~100 lines new code (config, init files). Rest is file moves.

---

### Phase 1: Shared Utilities

Port the foundational modules that all takeout stages depend on. Small, self-contained, extensively tested.

**What gets ported:**
- `datetime.js` → `src/pixelkasten/datetime.py`
  - `normalize_disk_date()` — strips timezone offsets (critical: match Node.js behavior, not Python AI behavior)
  - `parse_iso_date()` → `{year, month, day, hour, minute, second}` dict
  - `parse_photo_taken_time()` — Unix epoch → `{iso, exif}` pair
- `sidecar.js` → `src/pixelkasten/sidecar.py`
  - `read_sidecar()` — parse Google JSON, extract timestamp + geo
  - GPS (0,0) rejection
  - `geoDataExif` vs `geoData` fallback
- Handler files → `src/pixelkasten/handlers.py`
  - EXIF handler: `read_tags`, `parse`, `timestamp`, `geo`
  - QuickTime handler: `read_tags`, `parse`, `timestamp`, `geo`
  - Composite GPS tag parsing
  - Handler registry mapping extensions to handlers
  - `all_known_media_extensions` set

**Tests:** Port all Node.js datetime, sidecar, and handler tests. Add Python-specific tests where behavior could diverge (e.g., `pathlib` normalization of double extensions like `.MP.jpg`).

**Verify:** All ported tests pass. Existing AI tests still pass.

**Size:** ~260 lines source + ~850 lines tests ≈ **1,110 lines**

**Timezone unification:** Replace the AI pipeline's `_normalize_timestamp()` in `exif.py` with the new `normalize_disk_date()` from `datetime.py`. Both must strip timezone offsets early (wall-clock time). This is a behavior change for the AI pipeline — update any AI tests that asserted on preserved timezone offsets. Do not defer this to a later phase.

---

### Phase 2: Exiftool Unification

Merge read+write into one exiftool module. The Python AI pipeline already has a read-only exiftool wrapper (`exif.py`). The Node.js code also writes metadata. The unified module serves both.

**What gets built:**
- Refactor `src/pixelkasten/exiftool.py` — extract subprocess logic from current `exif.py`
  - `check_exiftool()` — already exists
  - `read_metadata(file_paths, tags)` — generalize current `read_exif()` to accept tag list parameter (Node.js pattern)
  - `write_metadata(file_path, tags)` — new (ported from Node.js `exiftool.js`)
- Update `src/pixelkasten/exif.py` to import from `exiftool.py`

**Tests:** ~5 new unit tests for `write_metadata`. Existing `test_exif_parsing.py` (20 tests) and `test_exif_integration.py` (9 tests) serve as regression guard.

**Verify:** All exif tests pass. AI pipeline still works.

**Size:** ~100 lines source changes + ~50 lines new tests ≈ **150 lines**

---

### Phase 3: Link Stage

The hardest single piece. Port Google Takeout sidecar matching with all its edge cases. Also enhance scan for takeout detection.

**What gets ported:**
- `scan.js` → extend `src/pixelkasten/scan.py`
  - Add `scan_takeout()` returning categorized collections: `{files_media, files_metadata, files_metadata_albums, files_other_ignored}`
  - Takeout detection: check for presence of `.json` sidecars
  - Existing `scan()` for AI pipeline remains unchanged
- `link.js` → `src/pixelkasten/link.py`
  - `link()` — main entry, returns manifest + unmatched stats
  - `media()` / `sidecar()` — filename decomposition (strip `(N)`, `-edited` variants, `.supplemental-metadata` variants)
  - `match()` / `match_score()` — scoring with confidence levels (3=exact, 2=name, 1=fuzzy)
  - Metadata suffix regex (21 truncated variants of `.supplemental-metadata`)
  - Edited suffix regex (6 truncated variants of `-edited`)
  - Bidirectional fuzzy matching with length threshold
- Add `can_keep()` to `src/pixelkasten/manifest.py`

**Tests:** Port all Node.js scan and link tests. The link tests are the crown jewels — they encode every Google Takeout filename edge case. **Port every test case before writing the implementation.** Then implement until all pass. Add Python-specific tests for `pathlib` edge cases: double extensions (`.MP.jpg`), duplicate markers `(1)`, and any other cases where `pathlib` silently normalizes filenames differently from Node.js `path`.

**Verify:** All ported tests pass. Existing AI tests still pass.

**Size:** ~320 lines source + ~700 lines tests ≈ **1,020 lines**

**Risk:** Highest risk phase. Path handling differences between `pathlib` and Node.js `path` (double extensions like `.MP.jpg`, duplicate markers `(N)`). Use string manipulation matching the Node.js approach, not `pathlib` for filename parsing. The link stage tests are the specification — if they pass, the implementation is correct.

---

### Phase 4: Dedupe + Reconcile

Port content-based deduplication and metadata reconciliation.

**What gets ported:**
- `dedupe.js` → `src/pixelkasten/dedupe.py`
  - `dedupe_hash()` — SHA-256 in chunks (handles >2GB files)
  - `dedupe_resolve()` — prefer album over loose, keep same-type duplicates
- `reconcile.js` → `src/pixelkasten/reconcile.py`
  - `reconcile()` — batch EXIF reading (512-item windows) + sidecar comparison
  - Per-file resolution: queue `write_tags` when disk metadata is missing but sidecar has it

**Tests:** Port all Node.js dedupe and reconcile tests.

**Verify:** All ported tests pass.

**Size:** ~230 lines source + ~650 lines tests ≈ **880 lines**

**Depends on:** Phase 1 (handlers, sidecar, datetime), Phase 2 (exiftool read).

---

### Phase 5: Rename + Apply

Build the shared stages that both pipelines converge on. Implements the new naming scheme (no months).

**What gets ported:**
- `rename.js` → `src/pixelkasten/rename.py`
  - `rename()` — filter to keepers, resolve album dates, compute target paths
  - `resolve_target_path()` — `YYYY/yyyymmdd-hhmmss.ext` (loose) or `YYYY/yyyymmdd - Album Name/yyyymmdd-hhmmss.ext` (album)
  - `resolve_collision()` — `-1`, `-2` suffix before extension
  - 3-char month abbreviation lookup (not `Intl.DateTimeFormat`) — though months are dropped from directories, the lookup may still be useful for future features
  - **Intentional divergence from Node.js:** no month directories (per naming scheme spec)
- `apply.js` → `src/pixelkasten/apply.py`
  - `apply()` — copy files to destination, write metadata via exiftool if `write_tags` exist
  - Fallback to original filename when rename was skipped
  - Sidecar copy when `--skip-embed`
- `report.js` → `src/pixelkasten/report.py`
  - CSV report generation from manifest

**Tests:** Port all Node.js rename, apply, and report tests. Rename test expectations must be adapted for no-months (implementing the spec, not the legacy code).

**Verify:** All ported tests pass. Apply collision handling works (fixes the silent-overwrite bug in the current AI pipeline).

**Size:** ~280 lines source + ~1,000 lines tests ≈ **1,280 lines**

---

### Phase 6: Unified Pipeline + CLI

Wire everything together into one command with auto-detection and workspace caching.

**What gets built:**
- `src/pixelkasten/pipeline.py` — unified orchestrator
  - `run_pipeline(options, hooks)` — detects mode, runs appropriate stage sequence
  - Takeout path: scan_takeout → link → reconcile → dedupe → rename → apply
  - Organize path: scan → exif_read → dedupe → embed → cluster → classify → refine → caption → propose → rename → apply
  - Stage gating via skip flags
  - Workspace save/load (two `if` statements)
- Adapt `ai/organize.py` → `src/pixelkasten/propose.py`
  - Instead of building full target paths, writes `source.type` and `source.name` onto entries
  - Rename stage handles the rest
- `src/pixelkasten_cli/main.py` — single-command CLI
  - Auto-detection (takeout vs archive)
  - All flags from the CLI Interface section
  - Workspace `-w` handling
  - `--dry-run` (run pipeline, print summary, skip apply)
  - Rich progress bars and stage reporting
- `pixelkasten status -w ./workspace` subcommand

**Tests:** ~15 new tests (pipeline orchestration, auto-detection, workspace save/load)

**Verify:**
- `pixelkasten -s <takeout-dir> -d <dest> --dry-run` shows correct plan for takeout
- `pixelkasten -s <archive-dir> -d <dest> --catalog --dry-run` shows correct plan for archive
- Workspace iteration works: first run caches, second run reuses
- All existing AI and ported tests still pass

**Size:** ~300 lines source + ~200 lines tests ≈ **500 lines**

**Depends on:** All previous phases.

---

### Phase 7: Integration Tests + Cleanup

End-to-end validation and removal of legacy code.

**What gets built:**
- Port all Node.js integration tests (`pipeline.test.js`) → `test/integration/test_takeout_pipeline.py`
  - Full pipeline with real exiftool, real JPEG fixtures
  - Verifies: metadata embedding, dedup behavior, sidecar copy, dry-run, unsupported format handling
- New unified integration tests
  - Takeout → organize (sequential workflow)
  - Archive with catalog → verify album structure
- Update `CLAUDE.md` / `AGENTS.md` with new commands and structure
- Update CI workflow

**Verify:**
- `uv run pytest -v` runs all tests (~330+: 213 ported + 113 existing + new integration)
- `pixelkasten --help` works
- `pixelkasten -s <real-takeout> -d <dest>` produces identical output to the Node.js tool (manual verification on a real export)
- CI passes

**Size:** ~500 lines tests + config changes

---

## Phase Summary

| Phase | Description | Source | Tests | Total |
|-------|-------------|--------|-------|-------|
| 0 | Project scaffolding | ~100 | 0 | ~100 |
| 1 | Shared utilities + TZ unification | ~260 | ~850 | ~1,110 |
| 2 | Exiftool unification | ~100 | ~50 | ~150 |
| 3 | Link stage | ~320 | ~700 | ~1,020 |
| 4 | Dedupe + reconcile | ~230 | ~650 | ~880 |
| 5 | Rename + apply | ~280 | ~1,000 | ~1,280 |
| 6 | Unified pipeline + CLI | ~300 | ~200 | ~500 |
| 7 | Integration + cleanup | ~50 | ~500 | ~550 |
| **Total** | | **~1,640** | **~3,950** | **~5,590** |

Test requirement: every Node.js test must be ported. Hardcoded counts are estimates for sizing — the source of truth is the Node.js test suite. Add Python-specific tests where behavior could diverge (e.g., `pathlib` edge cases, double extensions, Unicode filenames).

## Risk Assessment

**Highest risk:** Phase 3 (link stage). Encodes undocumented Google Takeout filename truncation behavior across many test cases. Mitigation: port tests first, implement until they pass.

**Medium risk:** Phase 5 (naming scheme divergence). Ported rename tests must be adapted for no-months. Easy to miss a test expectation. Mitigation: systematic find-and-replace on test expectations, then manual review.

**Low risk:** Everything else. Dedupe, reconcile, apply are straightforward logic with clear tests.

## What Gets Deleted

After Phase 0:
- `ai/` — code moved to `src/pixelkasten/`, directory deleted entirely (no shim)

After Phase 7:
- `packages/core/` — Node.js core (tag before deleting, keep for reference)
- `packages/cli/` — Node.js CLI
- Root `package.json`, `package-lock.json`, `.eslintrc.*`, etc.
