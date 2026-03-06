# PixelKasten

[![CI](https://github.com/arazabishov/pixelkasten/actions/workflows/ci.yml/badge.svg)](https://github.com/arazabishov/pixelkasten/actions/workflows/ci.yml)

PixelKasten helps you organize your photo library. It can automatically discover and name albums in any photo collection using local AI (CLIP + Ollama), and it can process Google Takeout exports by matching media files to their JSON sidecars, writing metadata, and deduplicating. Both capabilities work independently or together.

If you've ever tried to make sense of a Google Photos Takeout export, you know the pain: photos scattered across directories, timestamps and GPS coordinates trapped in `.json` sidecar files, and filenames truncated in ways that make matching things up surprisingly difficult. PixelKasten handles all of that. And if you just have a folder of photos you want organized into albums, no Takeout involved, it can do that too.

> **A note on stability:** PixelKasten is under active development. It will never touch your source files. Everything is copied into a separate destination directory and changes are applied there. That said, keeping a backup of your Takeout export is always a good idea.

## Quick start

```bash
# Process a Google Takeout export
pixelkasten -s ~/takeout -d ~/photos

# Preview without copying anything
pixelkasten -s ~/takeout -d ~/photos --dry-run

# Organize a plain photo archive with AI album discovery
pixelkasten -s ~/photos -d ~/organized --discover
```

## What it does

PixelKasten is built around the idea that you should be able to pick exactly the steps you need and skip the rest. Each stage of the pipeline can be turned on or off independently.

### Match media to metadata

When processing a Takeout export, PixelKasten scans the directory and pairs each media file with the JSON sidecar that belongs to it.

Google makes this matching harder than you'd expect. Long filenames get truncated, collision markers like `(1)` are appended, and `-edited` variants or `.supplemental-metadata` suffixes follow their own naming rules. PixelKasten uses a combination of exact and fuzzy matching to handle these cases, and every match gets a confidence score so you can verify the results yourself.

If all you need is the pairing, skip everything else. You'll get a CSV report mapping each file to its sidecar, and you can take it from there with exiftool or any other tool you prefer.

```bash
pixelkasten -s ~/takeout -d ~/photos --skip-metadata-write --skip-rename
```

### Write metadata into your files

If you'd rather not wrangle exiftool yourself, PixelKasten can write timestamps and GPS coordinates from the JSON sidecars directly into your media files. It uses the correct native tags for each format: EXIF for images, QuickTime for video.

It will not overwrite metadata that already exists on disk, it ignores invalid sidecar data (like `0,0` GPS coordinates), and it does not attempt to write to formats it doesn't have explicit rules for. If it doesn't know exactly what to do with a file, it leaves it alone.

```bash
pixelkasten -s ~/takeout -d ~/photos --skip-rename
```

### Organize and rename files

PixelKasten can arrange your library into a date-based folder structure:

```
destination/
  2024/
    20240301-133245.jpg                        # loose file
    20240301-133245-1.jpg                      # collision (-1, -2, ...)
    20240715-Beach Vacation/                  # album
      20240715-143000.jpg
      20240716-091200.jpg
  Unsorted/                                    # no EXIF timestamp
    IMG-20161115-WA0000.jpg
```

Files are named by their timestamp. Album files get grouped into subdirectories named after the album. Collisions are resolved with `-1`, `-2` suffixes.

### AI album discovery

For unstructured photo archives, or even Takeout exports where you want smarter organization, the `--discover` flag enables AI-powered album discovery. It runs entirely locally using CLIP embeddings for visual grouping, HDBSCAN for clustering, and an LLM (via Ollama) for naming the albums it finds.

```bash
# Plain archive with AI albums
pixelkasten -s ~/photos -d ~/organized --discover

# Takeout processing + AI albums combined
pixelkasten -s ~/takeout -d ~/photos --discover
```

This requires [Ollama](https://ollama.com/) with vision and text models installed locally. No data leaves your device.

## Prerequisites

Python 3.12+ and [uv](https://docs.astral.sh/uv/) are required. [exiftool](https://exiftool.org/) must be installed separately for metadata writing. [Ollama](https://ollama.com/) with vision and text models is only needed when running with `--discover`.

## Installation

```bash
uv sync
```

## Usage

```bash
pixelkasten --help
```

## Report

Every run produces a `report.csv` in the destination directory with one row per media file:

| Column | Description |
| --- | --- |
| `media` | Path to the source media file (relative to source) |
| `metadata` | Path to the matched JSON sidecar (empty if unmatched) |
| `confidence` | Match confidence: **3** (high), **2** (medium), **1** (satisfactory), or empty |
| `status` | Outcome: `written`, `copied`, `skipped`, `deleted`, or `error` |
| `reason` | Explanation when status is `skipped` or `error` |

## Supported formats

| Format | Extensions | Metadata written |
| --- | --- | --- |
| EXIF | `.jpg`, `.jpeg`, `.heic`, `.png` | Timestamps, GPS |
| QuickTime | `.mp4`, `.mov` | Timestamps, GPS |

Files with unsupported extensions (`.avi`, `.mkv`, `.wmv`, etc.) are copied without metadata writing and reported as skipped.
