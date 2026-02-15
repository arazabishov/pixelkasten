# PixelKasten

[![CI](https://github.com/arazabishov/pixelkasten/actions/workflows/ci.yml/badge.svg)](https://github.com/arazabishov/pixelkasten/actions/workflows/ci.yml)

If you've ever tried to make sense of a Google Photos Takeout export, you know the pain. Your photos and videos are scattered across directories, timestamps and GPS coordinates are trapped in `.json` sidecar files instead of the media itself, and filenames are truncated in ways that make matching things up surprisingly difficult.

PixelKasten is a CLI tool that fixes this. It pairs your media files with their metadata, and — if you want — writes that metadata back into the files and organizes them into a clean folder structure.

> **A note on stability:** PixelKasten is under active development. It will never touch your source files — everything is copied into a separate destination directory and changes are applied there. That said, keeping a backup of your Takeout export is always a good idea.

## How you can use PixelKasten

PixelKasten is built around the idea that you should be able to pick exactly the steps you need and skip the rest. Each stage of the pipeline can be turned on or off independently.

### Match media to metadata

At its core, PixelKasten scans your Takeout export and pairs each media file with the JSON sidecar that belongs to it. This is the one step that always runs.

Google makes this matching harder than you'd expect. Long filenames get truncated, collision markers like `(1)` are appended, and `-edited` variants or `.supplemental-metadata` suffixes follow their own naming rules. PixelKasten uses a combination of exact and fuzzy matching to handle these cases, and every match gets a confidence score so you can verify the results yourself.

If all you need is the pairing, skip everything else. You'll get a CSV report mapping each file to its sidecar, and you can take it from there with `exiftool` or any other tool you prefer.

```bash
pixelkasten -s ~/takeout -d ~/photos --skip-embed --skip-rename
```

### Embed metadata into your files

If you'd rather not wrangle `exiftool` yourself, PixelKasten can write timestamps and GPS coordinates from the JSON sidecars directly into your media files. It uses the correct native tags for each format:

- **EXIF** (JPEG, HEIC, PNG) — `SubSecDateTimeOriginal`, `GPSLatitude`/`GPSLongitude`/`GPSAltitude`
- **QuickTime** (MP4, MOV) — `CreationDate`, `Keys:GPSCoordinates`

A few things it is strict about: it will not overwrite metadata that already exists on disk, it ignores invalid sidecar data (like `0,0` GPS coordinates), and it does not attempt to write to formats it doesn't have explicit rules for. If it doesn't know exactly what to do with a file, it leaves it alone.

This step requires [exiftool](https://exiftool.org/) to be installed. Currently only EXIF and QuickTime formats are supported — more will be added over time.

```bash
pixelkasten -s ~/takeout -d ~/photos --skip-rename
```

### Organize and rename files

PixelKasten can arrange your library into a date-based folder structure:

```
destination/
  2023/
    01 - January/
      20230115-143005.jpg
      20230115-150200.mp4
    05 - May/
      20230510-120000 - Summer Trip/
        20230510-120000.jpg
        20230511-091530.heic
```

Files are named by their timestamp. Album files get grouped into subdirectories named after the album. Collisions are resolved with `-1`, `-2` suffixes.

This is opinionated — if you prefer a different structure, skip the rename step entirely.

```bash
pixelkasten -s ~/takeout -d ~/photos --skip-rename
```

## Prerequisites

- **Node.js** (v20+)
- **exiftool** — required unless you pass both `--skip-embed` and `--skip-rename`

## Usage

```bash
npm start -- -s <source> -d <destination>
```

| Flag                       | Description                                                              |
| -------------------------- | ------------------------------------------------------------------------ |
| `-s, --source <path>`      | Source directory (your Takeout export)                                   |
| `-d, --destination <path>` | Destination directory for output                                         |
| `--dry-run`                | Preview changes without writing anything                                 |
| `--skip-dedupe`            | Skip duplicate detection                                                 |
| `--skip-embed`             | Skip metadata embedding                                                  |
| `--skip-rename`            | Skip file renaming/organizing                                            |
| `--no-fuzzy`               | Disable fuzzy matching (strict sidecar pairing only)                     |
| `--prefer <album\|loose>`  | When deduplicating, prefer album copies or loose ones (default: `album`) |

## Report

Every run produces a `report.csv` in the destination directory with one row per media file:

| Column       | Description                                                                    |
| ------------ | ------------------------------------------------------------------------------ |
| `media`      | Path to the source media file                                                  |
| `metadata`   | Path to the matched JSON sidecar (empty if unmatched)                          |
| `confidence` | Match confidence: **3** (high), **2** (medium), **1** (satisfactory), or empty |
| `status`     | Outcome: `embedded`, `copied`, `skipped`, `deleted`, or `error`                |
| `reason`     | Explanation when status is `skipped` or `error`                                |

Due to the information loss in Google's export process, exact matching isn't always possible. The confidence score reflects how the match was made:

- **3** — name, extension, and duplicate marker all matched exactly
- **2** — name matched but required extension inference
- **1** — fuzzy prefix match, typically for truncated filenames

It's worth reviewing low-confidence matches in the report to make sure they look right.

## Supported formats

| Format    | Extensions                       | Metadata written |
| --------- | -------------------------------- | ---------------- |
| EXIF      | `.jpg`, `.jpeg`, `.heic`, `.png` | Timestamps, GPS  |
| QuickTime | `.mp4`, `.mov`                   | Timestamps, GPS  |

Files with unsupported extensions (`.avi`, `.mkv`, `.wmv`, etc.) are reported as skipped rather than silently ignored. More formats will be added over time.
