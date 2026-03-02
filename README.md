# PixelKasten

[![CI](https://github.com/arazabishov/pixelkasten/actions/workflows/ci.yml/badge.svg)](https://github.com/arazabishov/pixelkasten/actions/workflows/ci.yml)

If you've ever tried to make sense of a Google Photos Takeout export, you know the pain. Your photos and videos are scattered across directories, timestamps and GPS coordinates are trapped in `.json` sidecar files instead of the media itself, and filenames are truncated in ways that make matching things up surprisingly difficult.

PixelKasten is a CLI tool that fixes this. It pairs your media files with their metadata, writes that metadata back into the files, and organizes them into a clean folder structure. It can also use AI (CLIP + LLM) to automatically discover and name albums in unstructured photo archives.

> **A note on stability:** PixelKasten is under active development. It will never touch your source files — everything is copied into a separate destination directory and changes are applied there. That said, keeping a backup of your Takeout export is always a good idea.

## Quick start

```bash
# Process a Google Takeout export
pixelkasten -s ~/takeout -d ~/photos

# Preview without copying anything
pixelkasten -s ~/takeout -d ~/photos --dry-run

# Organize a plain photo archive with AI album discovery
pixelkasten -s ~/photos -d ~/organized --no-takeout --catalog
```

## Pipeline

PixelKasten runs in two modes, controlled by `--takeout` (default) and `--no-takeout`. Each stage can be skipped independently.

### Takeout mode (default)

```mermaid
graph LR
    A[Scan] --> B[Link]
    B --> C[Reconcile]
    C --> D[Dedupe]
    D --> E[Rename]
    E --> F[Apply]

    style A fill:#4a9eff,color:white
    style B fill:#4a9eff,color:white
    style C fill:#4a9eff,color:white
    style D fill:#7c7c7c,color:white
    style E fill:#7c7c7c,color:white
    style F fill:#7c7c7c,color:white
```

Processes a Google Photos Takeout export:

1. **Scan** — Categorize files into media, JSON sidecars, album metadata, and ignored.
2. **Link** — Pair each media file with its JSON sidecar using exact and fuzzy matching. Handles Google's filename truncation, `-edited` variants, `.supplemental-metadata` suffixes, and `(N)` collision markers.
3. **Reconcile** — Compare disk EXIF with sidecar data, queue metadata writes for missing timestamps and GPS.
4. **Dedupe** — SHA-256 hashing to detect duplicates across album and loose copies.
5. **Rename** — Build target paths from timestamps: `YYYY/yyyymmdd-hhmmss.ext` (loose), `YYYY/yyyymmdd - Album/yyyymmdd-hhmmss.ext` (album).
6. **Apply** — Copy files to destination, write metadata via exiftool.

### Takeout + catalog (`--takeout --catalog`)

```mermaid
graph LR
    A[Scan] --> B[Link]
    B --> C[Reconcile]
    C --> D[Dedupe]
    D --> E[Embed]
    E --> F[Cluster]
    F --> G[Classify]
    G --> H[Refine]
    H --> I[Caption]
    I --> J[Propose]
    J --> K[Rename]
    K --> L[Apply]

    style A fill:#4a9eff,color:white
    style B fill:#4a9eff,color:white
    style C fill:#4a9eff,color:white
    style D fill:#7c7c7c,color:white
    style E fill:#e8a838,color:white
    style F fill:#e8a838,color:white
    style G fill:#e8a838,color:white
    style H fill:#e8a838,color:white
    style I fill:#e8a838,color:white
    style J fill:#e8a838,color:white
    style K fill:#7c7c7c,color:white
    style L fill:#7c7c7c,color:white
```

Combines takeout processing with AI-powered album discovery. The catalog stages (orange) use CLIP embeddings, HDBSCAN clustering, and LLM reasoning to propose album names that feed into the standard rename stage.

### Archive mode (`--no-takeout --catalog`)

```mermaid
graph LR
    A[Scan] --> B[EXIF Read]
    B --> C[Dedupe]
    C --> D[Embed]
    D --> E[Cluster]
    E --> F[Classify]
    F --> G[Refine]
    G --> H[Caption]
    H --> I[Propose]
    I --> J[Rename]
    J --> K[Apply]

    style A fill:#4a9eff,color:white
    style B fill:#4a9eff,color:white
    style C fill:#7c7c7c,color:white
    style D fill:#e8a838,color:white
    style E fill:#e8a838,color:white
    style F fill:#e8a838,color:white
    style G fill:#e8a838,color:white
    style H fill:#e8a838,color:white
    style I fill:#e8a838,color:white
    style J fill:#7c7c7c,color:white
    style K fill:#7c7c7c,color:white
```

For plain photo archives (no Google sidecars). No link or reconcile stages — EXIF is read directly. AI stages discover and name albums.

```bash
# Full pipeline
pixelkasten -s ~/takeout -d ~/photos

# Just match and embed metadata, skip renaming
pixelkasten -s ~/takeout -d ~/photos --skip-rename

# Just match sidecars, skip everything else
pixelkasten -s ~/takeout -d ~/photos --skip-embed --skip-rename
```

### Archive mode with AI catalog

For unstructured photo archives (no Google sidecars), use `--no-takeout --catalog` to enable AI-powered album discovery:

```bash
pixelkasten -s ~/photos -d ~/organized --no-takeout --catalog
```

This runs CLIP embedding, HDBSCAN clustering, VLM captioning, and LLM-driven album naming. Requires [Ollama](https://ollama.com/) with vision and text models.

### Directory structure

```
destination/
  2024/
    20240301-133245.jpg                        # loose file
    20240301-133245-1.jpg                      # collision (-1, -2, ...)
    20240715 - Beach Vacation/                 # album
      20240715-143000.jpg
      20240716-091200.jpg
  Unsorted/                                    # no EXIF timestamp
    IMG-20161115-WA0000.jpg
```

**Why this format?** The compact `yyyymmdd-hhmmss` avoids separator ambiguity — the single dash unambiguously splits 8 date digits from 6 time digits. No month directories: the `YYYYMMDD` prefix on album names provides chronological sorting, and lexicographic sort equals chronological sort at every level. The scheme contains no subjective formatting choices, making it durable across OS and file manager changes.

### Workspace caching

For iterating on AI catalog settings without re-running expensive CLIP embedding:

```bash
# First run — full pipeline, cache embeddings
pixelkasten -s ~/photos -d ~/organized --no-takeout --catalog -w ./ws

# Re-run with different settings — embeddings cached
pixelkasten -s ~/photos -d ~/organized --no-takeout --catalog -w ./ws

# Force re-scan
pixelkasten -s ~/photos -d ~/organized --no-takeout --catalog -w ./ws --rescan

# Inspect workspace
pixelkasten status -w ./ws
```

## Prerequisites

- **Python 3.12+** and [uv](https://docs.astral.sh/uv/)
- **exiftool** — `brew install exiftool` (required unless `--skip-embed` is set)
- **Ollama** — only required for `--catalog` mode

## Installation

```bash
uv sync
```

## Usage

```bash
pixelkasten -s <source> -d <destination> [options]
```

| Flag | Description |
| --- | --- |
| `-s, --source <path>` | Source directory (required) |
| `-d, --destination <path>` | Destination directory (required unless `--dry-run`) |
| `--takeout / --no-takeout` | Takeout mode (default) or archive mode |
| `--catalog` | Enable AI-powered album discovery |
| `--dry-run` | Preview changes without writing anything |
| `--skip-dedupe` | Skip duplicate detection |
| `--skip-embed` | Skip metadata embedding |
| `--skip-caption` | Skip VLM captioning (catalog only) |
| `--skip-refine` | Skip temporal cluster refinement (catalog only) |
| `--prefer <album\|loose>` | When deduplicating, prefer album or loose copies (default: `album`) |
| `-w, --workspace <path>` | Workspace directory for caching |
| `--rescan` | Invalidate workspace cache, re-scan source |

## Report

Every run produces a `report.csv` in the destination directory with one row per media file:

| Column | Description |
| --- | --- |
| `media` | Path to the source media file (relative to source) |
| `metadata` | Path to the matched JSON sidecar (empty if unmatched) |
| `confidence` | Match confidence: **3** (high), **2** (medium), **1** (satisfactory), or empty |
| `status` | Outcome: `embedded`, `copied`, `skipped`, `deleted`, or `error` |
| `reason` | Explanation when status is `skipped` or `error` |

## Supported formats

| Format | Extensions | Metadata written |
| --- | --- | --- |
| EXIF | `.jpg`, `.jpeg`, `.heic`, `.png` | Timestamps, GPS |
| QuickTime | `.mp4`, `.mov` | Timestamps, GPS |

Files with unsupported extensions (`.avi`, `.mkv`, `.wmv`, etc.) are copied without metadata embedding and reported as skipped.
