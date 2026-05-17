# pixelkasten — agent skill (sample)

This is a reference skill file you can copy or adapt when running Claude Code (or another agent) against a pixelkasten working library. **It is not auto-installed by `pixelkasten init`.** Put it wherever your agent expects skill instructions (e.g., paste into Claude's "project instructions" or load it as a custom skill).

## What pixelkasten is

pixelkasten is a photo-library toolbox. It produces a **working library**: a flat directory of GUID-named media files with per-asset **record** JSONs under `.pixelkasten/`. The working library is your workspace — your job is to propose album assignments by reading records, asking the user, and writing `proposed_album` via the `propose` tool. A separate `export --to <dst>` command later turns your proposals into an organized photo library.

> "Record" is pixelkasten's `.pk.json` file. The word "sidecar" is reserved for Google Takeout's input `.json` files; you'll only encounter those if you peek at the source export, never inside a working library.

## Record schema

Every keeper in the working library has a record at `<library>/.pixelkasten/<filename>.pk.json`:

```json
{
  "dates": ["2024-06-01T14:30:22"],                           // import (reconcile)
  "geo": {"latitude": 52.52, "longitude": 13.40, "altitude": 34.0},  // import (reconcile)
  "album": "Wedding 2019",                                    // import (Takeout source folder or archive subfolder; null for root-level archive files)
  "group_id": "3f2a1b8cdef01234567890abcdef0123",             // import (emit) — shared across siblings
  "location": {"name": "Berlin, Germany",
               "region": "Berlin", "country": "DE"},          // enrich (geocode)
  "caption": "Street scene with cyclists.",                   // caption (on demand)
  "proposed_album": "Berlin trip"                             // propose (your decision)
}
```

Fields can be absent. Use `jq` filters that tolerate missing keys.

Members of one logical asset (Live Photo image + video, edited variant) share a `group_id`. **Filenames are independently unique** — siblings do *not* share a filename stem — so use `group_id` (not the filename) to identify a group's members.

## Running pixelkasten from inside the library

The agent's working directory is the working library, not the pixelkasten source tree, so plain `pixelkasten` likely isn't on `$PATH`. The reliable invocation is:

```bash
uv run --project <path-to-pixelkasten-repo> pixelkasten <subcommand> <args>
```

Capture it once in a shell variable so the commands below stay legible:

```bash
PK="uv run --project <path-to-pixelkasten-repo> pixelkasten"
$PK caption /abs/path/to/file.heic
$PK similar /abs/path/to/file.heic --k 10
```

Substitute the real `<path-to-pixelkasten-repo>` (the user will tell you where it lives, or `find ~ -maxdepth 4 -type d -name pixelkasten 2>/dev/null` can locate it).

## The toolbox

| Command | What it does | Typical use |
|---|---|---|
| `pixelkasten caption <path>` | Run VLM on one asset, cache caption in the record. | `pixelkasten caption library/3f2a1b8c.heic` |
| `pixelkasten similar <path> [--k 20]` | k-NN over `embeddings.npy` (images and videos both eligible); prints `[{path, score}, …]`. Query must already be in the library (run `enrich` after importing). | `pixelkasten similar library/3f2a1b8c.heic --k 5` |
| `pixelkasten cluster [paths…] [--min-cluster-size N]` | HDBSCAN over a scoped slice (images and videos both eligible); prints `{"<label>": [path, …]}`. Label `-1` is HDBSCAN's noise bucket — paths it couldn't group. | `jq -r … \| pixelkasten cluster` |
| `pixelkasten propose <path> <album>` | Write `proposed_album` to the file and group siblings. | `pixelkasten propose library/3f2a1b8c.heic "Berlin trip"` |
| `pixelkasten propose <path> --clear` | Remove `proposed_album` from the file and group siblings. | |

For reads, the records are the source of truth — use `jq`, `find`, `ls`. **Do not call `exiftool` to inspect dates, geo, or album on these files.** `pixelkasten import` already extracted that data into the record; the file's on-disk EXIF and the record can diverge (e.g., when `--skip-metadata-write` was used), and the record is canonical for the agent's purposes.

## `jq` query patterns

Run these against `<library>/.pixelkasten/*.pk.json`. They tolerate missing keys.

```bash
# All files in a specific region
jq -r 'select(.location.region == "Berlin")' .pixelkasten/*.pk.json

# All files between two dates
jq -r 'select((.dates // [])[0] >= "2024-06-01" and (.dates // [])[0] < "2024-07-01") | input_filename' .pixelkasten/*.pk.json

# All files without a caption
jq -r 'select(.caption == null or .caption == "") | input_filename' .pixelkasten/*.pk.json

# All files with proposed_album set (review what you've proposed so far)
jq -r 'select(.proposed_album != null) | input_filename' .pixelkasten/*.pk.json

# Files where dates contains 2024-06 (any field starting with 2024-06)
jq -r 'select(any(.dates // []; startswith("2024-06"))) | input_filename' .pixelkasten/*.pk.json

# Group records by group_id (siblings of one logical asset share the same group_id):
jq -r '.group_id // empty' .pixelkasten/*.pk.json | sort -u

# List all files in the same group as a given record:
my_group=$(jq -r '.group_id' .pixelkasten/abc123.jpg.pk.json)
jq -r --arg g "$my_group" 'select(.group_id == $g) | input_filename' .pixelkasten/*.pk.json
```

To map record paths back to media files in the library, drop the `.pk.json` suffix and replace `.pixelkasten/` with the library root.

## Behavioral rules

- **Anchor with 1–2 questions at the start of every session.** Where does the user live? Do they want this organized by trip, by year, by event? Don't skip — your output is only as good as the user's mental model that anchors it.
- **Propose only when confident.** A photo without `proposed_album` is *not* a failure — `export` will route it to its Takeout album (`.album`) if present, otherwise to a `<YYYY>/<YYYYMMDD-HHMMSS>.<ext>` year-folder slot. Use that fallback for everyday/home-region photos that don't belong to a distinct event. Never invent an album like `"Uncategorized"` or `"Other"` just to have something to propose.
- **Album names should not include dates.** `export` prepends `<YYYY>/<YYYYMMDD>-` to the album folder using the group's earliest date, so `"Berlin trip"` becomes `2024/20240601-Berlin trip/`. Putting a year in the name produces ugly duplicates like `20240601-Berlin 2024 trip`.
- **Match existing albums.** Before proposing a new album, check what's already in `.album` and `.proposed_album`. Use the user's vocabulary and casing.
- **Prefer the larger grouping when unsure.** It's easier for the user to split a "Summer 2024" album later than to merge ten micro-events.
- **Surface conflicts rather than silently picking.** When date says one event but location says another, ask the user which signal to trust here.
- **After a correction, restate the rule and apply forward.** Don't re-ask the same question on the next slice.
- **Captioning is the one slow operation — use it deliberately.** `similar` and `cluster` are cheap enough that cost shouldn't gate the decision to query them when they'd sharpen your reasoning; only `caption` warrants restraint. Cached captions are free for re-reads.
- **Propose on any group member; the tool propagates to siblings.** Live Photo image + video share a stem and get the same proposal automatically.

## When to reach for vision tools

Two of these are cheap and one is slow — use them accordingly.

**`similar <path> --k N`** is essentially free (a numpy dot product over the embeddings matrix). Use it whenever you have one well-anchored photo (e.g., a GPS-tagged shot you know belongs to a trip) and want to find visually-similar strays. Useful for stitching no-GPS photos into known events, sanity-checking that an album boundary corresponds to a visual coherence break, or finding near-duplicates.

Both images and videos are eligible (each video is represented by the mean of its sampled frames). If you anchor on a JPG and don't see any videos in the top-K, that's a content-similarity signal — not a capability gap. Anchor on a video itself if you specifically want to find other videos.

```bash
$PK similar /abs/path/to/anchor.jpg --k 30
```

**`cluster [paths...]`** is also cheap (HDBSCAN on a small matrix, sub-second). Use it whenever metadata alone gives you an ambiguous slice — undated stretches, several weeks in the same region with no clear trip structure, or a heap of strays you want to bucket by content.

```bash
jq -r 'select(.location.region == null and (.dates[0] // "") >= "2017-06" and (.dates[0] // "") < "2017-07") | input_filename' \
  .pixelkasten/*.pk.json \
  | sed 's|^\./\?\.pixelkasten/||; s|\.pk\.json$||' \
  | $PK cluster --min-cluster-size 4
```

Then propose per HDBSCAN label.

**`caption <path>` is the one slow operation** — 5-20s per call, hits the local VLM via Ollama. Reserve it for slices where metadata + `similar` + `cluster` still don't tell you what's depicted. Typically 1–2 captions on representative members of an unclear cluster is enough to disambiguate "wedding" vs. "hike" vs. "office party". Captions cache in the record, so re-reads are free.

The honest decision rule: form your hypothesis from metadata first, then use `similar` and `cluster` whenever they'd sharpen or test that hypothesis — they're cheap enough that cost shouldn't gate the decision to query them. Use `caption` deliberately, on specific photos whose content is genuinely the missing piece.

## Heuristic knowledge

These come from earlier auto-organization passes — they're starting points, not absolute rules. When a heuristic and the user disagree, the user wins.

- **>48-hour temporal gap → likely a different event.** Multi-day trips don't fragment cleanly under tighter windows; single-day events fit within 48 hours.
- **A region with 5+ photos is likely "home," not a destination.** People accumulate photos where they live. Surface this back to the user when you see it (e.g., "Berlin looks like home — should I exclude it from trips?").
- **Photos within a week + visually similar → same event.** HDBSCAN's clustering over-splits when it doesn't see temporal context; you should use both.
- **Photos without GPS but with timestamps overlapping a known trip → belong to that trip.** Phones occasionally drop GPS; visual similarity alone is unreliable for this.

## The export's fallback chain

When you understand what happens to files you don't propose, you'll make better calls about when to propose at all. For each photo, `pixelkasten export` picks a target in this order:

1. `proposed_album` set → `<YYYY>/<YYYYMMDD>-<proposed_album>/<YYYYMMDD-HHMMSS>.<ext>` (you decided)
2. `proposed_album` unset, `album` set (from Takeout source folder, or the parent folder of an archive subfolder file — note that generic folder names like `DCIM` / `100APPLE` are propagated verbatim; treat them as hints, not gospel) → same shape, using `album`
3. Neither set, parseable `dates[0]` → `<YYYY>/<YYYYMMDD-HHMMSS>.<ext>` (loose in year folder)
4. No parseable date → `<filename>` at the destination root (the working-library uuid name)

You only need to act at step 1. Steps 2–4 are automatic.

## What the agent should never do

- **Don't read image or video bytes into your context.** No `cat` on media files, no `Read` tool on JPEGs/HEICs/MP4s/MOVs, no base64-loading binaries. Pixels are processed only by pixelkasten's local tools (`caption`, `similar`, `cluster`) — keep them out of your conversation.
- **Don't upload images, embeddings, or any pixel data to any external service.** No `WebFetch`, no HTTP POSTs to remote APIs, no pastebins, no cloud vision endpoints. The privacy boundary is hard: pixels stay on this machine.
- **Use only pixelkasten's APIs for media operations.** If you want to caption, run `pixelkasten caption`; if you want similarity, run `pixelkasten similar`; if you want clustering, run `pixelkasten cluster`. Don't reach around them (no direct CLIP calls, no direct Ollama HTTP requests, no bespoke ffmpeg invocations).
- **Don't call `exiftool` for dates, geo, or album.** Read those from the records under `.pixelkasten/`. The record is canonical; on-disk EXIF can lag (e.g., `--skip-metadata-write` runs) and re-reading it is slower and noisier than `jq`.
- **Don't write to records except via `propose`.** Direct edits skip validation and break group propagation across Live Photo siblings and edited variants.
- **Don't move or rename files in the working library.** It's flat for a reason; `export --to <dst>` does the organizing later.
- **Don't reorganize the working library's folder structure.** No subdirectories, no rename. The working library is canonical.
- **Don't trigger `export --to <dst>` on the user's behalf without confirmation.** That's a write-out step that produces user-visible artifacts; let them initiate it.
