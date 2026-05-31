# PixelKasten

[![CI](https://github.com/arazabishov/pixelkasten/actions/workflows/ci.yml/badge.svg)](https://github.com/arazabishov/pixelkasten/actions/workflows/ci.yml)

PixelKasten helps you organize your photo library. It normalizes a messy source — a Google Takeout export or any flat archive of media files — into a deduplicated, metadata-enriched **working library**. From there, you can either export straight to an organized photo library, or hand the working library off to an LLM agent (Claude Code, etc.) that proposes album assignments through conversation with you.

If you've ever tried to make sense of a Google Photos Takeout export, you know the pain: photos scattered across directories, timestamps and GPS coordinates trapped in `.json` sidecar files, and filenames truncated in ways that make matching surprisingly difficult. PixelKasten handles that. And if you just have a folder of photos you want organized, no Takeout involved, it can do that too.

> **A note on stability:** PixelKasten is under active development. It never modifies your source files. Everything is copied into a separate destination directory.

## Quick start — pure pipeline (no agent)

Two commands take a Takeout export to an organized photo library:

```bash
# 1. Normalize the source into a working library
pixelkasten import --from-takeout -s ~/takeout -d ~/library

# 2. Export the working library to your final photo library
pixelkasten export ~/library --to ~/photos
```

The same flow works for archives without sidecars — just swap the mode:

```bash
pixelkasten import --from-archive -s ~/old-photos -d ~/library
pixelkasten export ~/library --to ~/photos
```

## Quick start — with an LLM agent

The agent (Claude Code, run inside the working library) reads records, asks you 1–2 anchoring questions, runs `caption` / `similar` / `cluster` on demand, and writes `proposed_album` decisions via `propose`. Then `export` produces the final library with your agent's choices baked in.

```bash
# 1. Normalize
pixelkasten import --from-takeout -s ~/takeout -d ~/library

# 2. Bulk geocode + CLIP embeddings (one-time per library)
pixelkasten enrich ~/library

# 3. Hand off to the agent
cd ~/library
claude  # (or your agent of choice, with docs/SKILL.md as its instructions)

# 4. Export with the agent's decisions
pixelkasten export ~/library --to ~/photos
```

A sample skill file for Claude Code lives at [`docs/SKILL.md`](docs/SKILL.md). Copy or adapt it to give the agent context about the toolbox.

## The toolbox

| Command | Purpose | Writes? |
|---|---|---|
| `pixelkasten import --from-takeout \| --from-archive` | Normalize a source into a working library | Files + records |
| `pixelkasten enrich <library>` | Bulk reverse-geocode + CLIP embed | Records + `embeddings.npy` |
| `pixelkasten caption <path>` | Run VLM on one asset; cache result in the record | One record |
| `pixelkasten similar <path> [--k N]` | k-NN over the library's embeddings | Stdout (JSON) |
| `pixelkasten cluster [paths…]` | HDBSCAN over a scoped slice | Stdout (JSON) |
| `pixelkasten propose <path> <album>` | Record `proposed_album` on the file and group siblings | Records |
| `pixelkasten export <library> --to <dst>` | Export the working library to an organized layout | Files at dst |

Read-only operations (listings, EXIF, record fields) use shell tools — `jq`, `find`, `exiftool`, `ls`.

## The two libraries

PixelKasten distinguishes a **working library** from an **export library**.

**Working library** (the agent's workspace; what `import` produces):

```
~/library/
  3f2a1b8cdef01234567890abcdef01230.heic   # uuid4 hex per file, flat
  9d7e4f02ab12c34d5e67f89012345678.mov     # group sibling — different filename,
                                           # same group_id in its record
  bbe90b6fd17f468c86da78ab484fd469.jpg
  .pixelkasten/
    3f2a1b8cdef01234567890abcdef01230.heic.pk.json   # per-asset record
    9d7e4f02ab12c34d5e67f89012345678.mov.pk.json
    bbe90b6fd17f468c86da78ab484fd469.jpg.pk.json
    embeddings.npy                 # CLIP vectors (after `enrich`)
    embeddings.paths.json          # row index → filename
```

**Export library** (the user-facing organized output of `export`):

```
~/photos/
  bbe90b6fd17f468c86da78ab484fd469.jpg   # undated -> kept at root with uuid name
  2024/
    20240615-Wedding/              # album: <YYYYMMDD>-<name>
      20240615-143022.heic         # group member
      20240615-143022.mov          # group sibling
    20240620-100530.jpg            # loose file in year folder
    20240620-100530-1.jpg          # -N suffix on collision
```

You can delete the working library after a satisfactory export. Users who want to keep iterating with the agent keep both.

## Prerequisites

| Tool | When needed |
|---|---|
| Python 3.12+ and [uv](https://docs.astral.sh/uv/) | Always |
| [exiftool](https://exiftool.org/) | Always (`brew install exiftool`) |
| [ffmpeg](https://ffmpeg.org/) | For video assets in `enrich` and `caption` (`brew install ffmpeg`) |
| [Ollama](https://ollama.com/) with a vision model | For `caption` only |
| Claude Code or another agent | For the agent-driven workflow only |

Install Python dependencies:

```bash
uv sync
```

## Architecture and design

See [AGENTS.md](AGENTS.md) for the pipeline shape, record schema, and design conventions. [docs/takeout.md](docs/takeout.md) covers Google Takeout's filename quirks, and [docs/SKILL.md](docs/SKILL.md) is a sample agent skill file for driving the toolbox.
