# AGENTS.md

This file provides guidance to AI coding agents when working with code in this repository.

## Commands

```bash
# Run all tests (unit + integration)
uv run pytest -v

# Run unit tests only
uv run pytest test/unit/ -v

# Run integration tests only (requires exiftool)
uv run pytest test/integration/ -v

# Run the unified pipeline
uv run pixelkasten -s <source> -d <destination>                    # takeout (default)
uv run pixelkasten -s <source> -d <destination> --dry-run          # preview
uv run pixelkasten -s <source> -d <destination> --no-takeout --catalog  # archive + AI
uv run pixelkasten -s <source> -d <destination> -w ./workspace     # with caching

# Inspect a workspace
uv run pixelkasten status -w ./workspace

# Lint and format
uv run ruff check src/
uv run ruff format --check src/
```

## Project Structure

```
src/pixelkasten/
  cli.py                    # CLI entry point (typer)
  pipeline.py               # unified orchestrator (takeout + archive modes)
  reports.py                # Rich progress bars + summary tables
  core/                     # shared utilities
    datetime.py             # normalize_disk_date, parse_iso_date, parse_photo_taken_time
    exiftool.py             # subprocess wrapper (read + write)
    geocode.py              # offline reverse geocoding (GPS → city/region)
    sidecar.py              # Google sidecar JSON parsing
    handlers.py             # EXIF + QuickTime handler registry
    manifest.py             # can_keep(), manifest I/O
    report.py               # CSV report generation
  stages/                   # pipeline stages
    scan.py                 # file discovery (scan + scan_takeout)
    link.py                 # sidecar matching (uses os.path, NOT pathlib)
    dedupe.py               # SHA-256 deduplication
    reconcile.py            # EXIF vs sidecar comparison + metadata population
    rename.py               # target path computation (no month directories)
    apply.py                # file copy + metadata embedding
    catalog/                # AI album discovery (--catalog)
      pipeline.py           # run_catalog() orchestrator
      embed.py              # CLIP embeddings
      cluster.py            # HDBSCAN clustering
      classify.py           # zero-shot classification
      refine.py             # temporal cluster refinement
      caption.py            # VLM captioning via Ollama
      organize.py           # LLM album naming + propose_albums()
test/
  unit/
    core/                   # mirrors src/pixelkasten/core/
    stages/                 # mirrors src/pixelkasten/stages/
  integration/
  fixtures/media/           # 4 shared JPEG test fixtures
```

## Pipeline Architecture

Two modes sharing stages:

**Takeout mode** (default, `--takeout`):
```
scan → link → reconcile → geocode → dedupe → [catalog] → rename → apply
```

**Archive mode** (`--no-takeout`):
```
scan → reconcile → geocode → dedupe → [catalog] → rename → apply
```

The catalog stages only run when `--catalog` is specified:
```
embed → cluster → classify → [refine] → [caption] → propose
```

The rename and apply stages are source-agnostic — they work the same for both modes.

**Workspace caching** (`-w`): persists `manifest.json` after init stages and `embeddings.npy` after CLIP embedding. Re-run skips cached stages.

## Manifest Data Flow

Each stage enriches the shared manifest. Downstream stages consume what upstream stages produce:

| Stage | Writes | Key fields |
|-------|--------|------------|
| scan | raw file lists | `files_media`, `files_metadata`, etc. |
| link | matched entries | `mediaPath`, `source`, `json` |
| reconcile | metadata from EXIF + sidecar | `metadata.status`, `metadata.dates`, `metadata.writeTags`, `metadata.geo` |
| geocode | location names from GPS | `location.name`, `location.region` |
| dedupe | duplicate resolution | `dedupe.status`, `dedupe.hash` |
| catalog/classify | per-image tags | `tags` |
| catalog/refine | updated clusters | `cluster` |
| catalog/caption | image descriptions | `caption` |
| catalog/organize | album assignments | `source.type`, `source.name` |
| rename | target paths | `rename.status`, `rename.targetPath` |
| apply | copy results | `apply.status` |

## Key Architecture Decisions

- **Python-only**: single runtime for AI + file processing. Direct ML integration, no process boundary. `typer` + `rich` for CLI, `pathlib` for path construction, FastAPI-ready for future web UI.
- **No month directories**: `YYYY/yyyymmdd-hhmmss.ext` (loose), `YYYY/yyyymmdd - Album/yyyymmdd-hhmmss.ext` (album). Lexicographic sort = chronological sort at every level.
- **Timezone**: strip offsets early (wall-clock time in filenames)
- **Manifest-driven**: single in-memory dict enriched by each stage. Side effects (file copy, metadata write) deferred to the apply stage.
- **Core/CLI separation**: `pixelkasten.core` + `pixelkasten.stages` are importable libraries with no UI deps. CLI is a thin consumer. Critical for future web/desktop UI.
- **Hooks pattern**: stage-level callbacks so different consumers (CLI, web UI, desktop app) can provide their own reporting.
- **Handler protocol**: EXIF + QuickTime handlers with `read_tags`, `parse()`, `timestamp()`, `geo()`
- **GPS validation**: sidecar rejects either-zero (Google placeholder); disk EXIF rejects only both-zero
- **All-local AI**: `--catalog` runs CLIP + HDBSCAN + Ollama locally. No cloud API calls. Signal stack: EXIF (when/where) > CLIP embeddings (looks like) > VLM captions (what's happening).
- **Cluster refinement**: HDBSCAN groups by appearance; metadata fixes it via eject (no dates), split (48h gaps), merge (similar + temporally close), absorb (by location or visual similarity). Region-level matching, home location inference, outlier filtering (< 10%).

## Guiding Principles

1. **Do Not Overwrite Existing Data** — check for existing EXIF before writing sidecar data
2. **Validate Input Data** — reject `(0, 0)` GPS, invalid timestamps
3. **Use Native Tags** — correct format-specific tags (EXIF vs QuickTime)
4. **Be Strict on Unknown Formats** — skip `.avi`, `.mkv` etc., report in summary
5. **Prioritize Simplicity** — minimize dependencies, justify additions
6. **Ensure Testability** — pytest, good coverage
7. **Maintain Transparency** — log outcomes, report file statuses
8. **Stages consume upstream output** — never re-read raw data; each stage reads from fields that upstream stages wrote

## Code Conventions

- All public functions should have full type annotations
- Imports for heavy dependencies (torch, sklearn, ollama) are deferred inside functions
- Link stage uses `os.path` for filename decomposition (NOT pathlib — it normalizes double extensions)

## Python Test Code Style

Tests use `pytest`. Fixtures live in `test/fixtures/media/`.

```python
# Use descriptive class + method names
class TestSplitByTemporalGaps:
    def test_splits_cluster_at_48h_gap(self):

# Create minimal inline test data per test
# Use numpy random with fixed seed for deterministic embeddings
rng = np.random.RandomState(42)
```

## Prerequisites

- Python 3.12+, uv
- exiftool (`brew install exiftool`)
- Ollama with vision + text models (for `--catalog` mode)
