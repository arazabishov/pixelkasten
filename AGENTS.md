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

# Legacy: run individual AI catalog stages
uv run pixelkasten embed -s <source> -o <output>
uv run pixelkasten enrich -m <output>/manifest.json
uv run pixelkasten refine -m <output>/manifest.json
uv run pixelkasten caption -m <output>/manifest.json
uv run pixelkasten organize -m <output>/manifest.json

# Lint and format
uv run ruff check src/
uv run ruff format --check src/
```

## Project Structure

```
src/pixelkasten/
  cli.py                    # CLI entry point (typer)
  pipeline.py               # unified orchestrator (takeout + archive modes)
  core/                     # shared utilities
    datetime.py             # normalize_disk_date, parse_iso_date, parse_photo_taken_time
    exiftool.py             # subprocess wrapper (read + write)
    exif.py                 # EXIF reading + reverse geocoding
    sidecar.py              # Google sidecar JSON parsing
    handlers.py             # EXIF + QuickTime handler registry
    manifest.py             # can_keep(), manifest I/O
    report.py               # CSV report generation
  stages/                   # pipeline stages
    scan.py                 # file discovery (scan + scan_takeout)
    link.py                 # sidecar matching (uses os.path, NOT pathlib)
    dedupe.py               # SHA-256 deduplication
    reconcile.py            # EXIF vs sidecar comparison
    rename.py               # target path computation (no month directories)
    apply.py                # file copy + metadata embedding
    propose.py              # LLM album naming adapter
    embed.py                # CLIP embeddings
    cluster.py              # HDBSCAN clustering
    classify.py             # zero-shot classification
    refine.py               # temporal cluster refinement
    caption.py              # VLM captioning via Ollama
    organize.py             # LLM organization (legacy)
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
scan_takeout → link → reconcile → dedupe → rename → apply
```

**Archive mode** (`--no-takeout`):
```
scan → exif_read → dedupe → [embed → cluster → classify → refine → caption → propose] → rename → apply
```

The catalog stages (in brackets) only run when `--catalog` is specified. The rename and apply stages are source-agnostic — they work the same for both modes.

**Workspace caching** (`-w`): persists `manifest.json` after init stages and `embeddings.npy` after CLIP embedding. Re-run skips cached stages.

## Key Architecture Decisions

- **No month directories**: `YYYY/yyyymmdd-hhmmss.ext` (loose), `YYYY/yyyymmdd - Album/yyyymmdd-hhmmss.ext` (album)
- **Timezone**: strip offsets early (wall-clock time in filenames)
- **Manifest-driven**: single in-memory dict structure enriched by each stage
- **Handler protocol**: EXIF + QuickTime handlers with `read_tags`, `parse()`, `timestamp()`, `geo()`
- **GPS validation**: sidecar rejects either-zero (Google placeholder); disk EXIF rejects only both-zero

## Guiding Principles

1. **Do Not Overwrite Existing Data** — check for existing EXIF before writing sidecar data
2. **Validate Input Data** — reject `(0, 0)` GPS, invalid timestamps
3. **Use Native Tags** — correct format-specific tags (EXIF vs QuickTime)
4. **Be Strict on Unknown Formats** — skip `.avi`, `.mkv` etc., report in summary
5. **Prioritize Simplicity** — minimize dependencies, justify additions
6. **Ensure Testability** — pytest, good coverage
7. **Maintain Transparency** — log outcomes, report file statuses

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
