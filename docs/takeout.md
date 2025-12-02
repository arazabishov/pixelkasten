# Google Takeout File Naming

Google Photos Takeout exports media files alongside sidecar `.json` files containing metadata (capture time, geo tags, description, etc.). Matching media to sidecar files is challenging due to Google's unconventional naming scheme.

## Media Files

### Schema

```
<name>[-edited][(N)].<ext>
└──────┬──────┘
   shrinkable
```

Or without extension: `<name>[-edited][(N)]`

### Components

| Component | Required | Can Truncate | Example             | Description                                         |
| --------- | -------- | ------------ | ------------------- | --------------------------------------------------- |
| `name`    | Yes      | Yes          | `photo`, `photo.MP` | Base filename (may include `.MP`, etc.)             |
| `-edited` | No       | Yes          | `-edited`, `-edi`   | Edited suffix ¹                                     |
| `(N)`     | No       | N/A          | `(1)`, `(2)`        | Filename collision marker ² (added post-truncation) |
| `.<ext>`  | No       | No           | `.jpg`, `.HEIC`     | Primary extension (preserved when present)          |

> ¹ The `-edited` suffix truncates progressively: `-edited` → `-edite` → `-edit` → `-edi` → `-ed` → `-e` → removed

> ² The `(N)` marker resolves filename collisions at export time. It is assigned based on export order, not source file identity. For example, if you edit both `photo.jpg` and `photo(1).jpg`, the first edit exported becomes `photo-edited.jpg` and the second becomes `photo-edited(1).jpg`—regardless of which source file was edited.

**Key insight**: Google shrinks filenames from right to left, preserving only `.<ext>`. For example, `-edited` shrinks progressively before the `name` starts shrinking. The `name` may contain dot-separated segments like `.MP` (Motion Photos), but these are not treated specially—they shrink like any other part of the name. The `(N)` marker is added _after_ truncation if needed to resolve filename collisions.

### Examples

| File Name                | name        | edited    | (N) | ext   |
| ------------------------ | ----------- | --------- | --- | ----- |
| `photo.jpg`              | `photo`     | -         | -   | `jpg` |
| `photo-edited.jpg`       | `photo`     | `-edited` | -   | `jpg` |
| `photo(1).jpg`           | `photo`     | -         | `1` | `jpg` |
| `photo-edited(1).jpg`    | `photo`     | `-edited` | `1` | `jpg` |
| `photo.MP.jpg`           | `photo.MP`  | -         | -   | `jpg` |
| `photo.MP(1).jpg`        | `photo.MP`  | -         | `1` | `jpg` |
| `photo.MP-edited.jpg`    | `photo.MP`  | `-edited` | -   | `jpg` |
| `photo.MP-edited(1).jpg` | `photo.MP`  | `-edited` | `1` | `jpg` |
| `longname-edi(1).jpg`    | `longname`  | `-edi`    | `1` | `jpg` |
| `longname.(1).jpg`       | `longname.` | -         | `1` | `jpg` |
| `photo`                  | `photo`     | -         | -   | -     |

## Sidecar Files

### Schema

```
<name>[.<media_ext>][.<metadata_suffix>][(N)].json
└──────────────────┬───────────────────┘
                shrinkable
```

### Components

| Component            | Required | Can Truncate | Example                  | Description                                       |
| -------------------- | -------- | ------------ | ------------------------ | ------------------------------------------------- |
| `name`               | Yes      | Yes          | `photo`, `photo.MP`      | Base filename from media                          |
| `.<media_ext>`       | No       | Yes          | `.jpg`, `.HEIC`          | Media file extension                              |
| `.<metadata_suffix>` | No       | Yes          | `.supplemental-metadata` | Metadata suffix ¹ (can shrink to empty)           |
| `(N)`                | No       | N/A          | `(1)`, `(2)`             | Filename collision marker (added post-truncation) |
| `.json`              | Yes      | No           | `.json`                  | Always present                                    |

> ¹ The metadata suffix truncates progressively: `.supplemental-metadata` → `.supplemental-metada` → `.supplemental-met` → `.suppl` → empty

**Key insight**: Sidecar files only preserve `.json` during truncation—everything else, including media extension and metadata suffix, can be shrunk. The `(N)` marker is added after truncation if needed to resolve collisions.

### Examples

| Sidecar File Name                         | Media Name     | (N) |
| ----------------------------------------- | -------------- | --- |
| `photo.jpg.supplemental-metadata.json`    | `photo.jpg`    | -   |
| `photo.jpg.supplemental-metadata(1).json` | `photo.jpg` ²  | `1` |
| `photo.MP.jpg.supplemental-met.json`      | `photo.MP.jpg` | -   |
| `photo.jpg.suppl.json`                    | `photo.jpg`    | -   |
| `longname.jpg.supplemental-metada.json`   | `longname.jpg` | -   |
| `photo..json`                             | `photo.jpg`    | -   |
| `photo.json`                              | `photo`        | -   |

> ² The `(N)` in sidecar filenames is for sidecar collision resolution, not a reference to the media file's `(N)`. A sidecar with `(1)` could correspond to any media file.

## Export Flow

Google generates filenames during Takeout export in three steps:

### Step 1: Generate base filename

Each file gets its "ideal" filename based on type:

- Original: `photo.jpg`
- Edited: `photo-edited.jpg`

### Step 2: Truncate if needed

If the filename exceeds ~40 characters, shrink from right to left:

**For media files:**

1. Shrink `-edited` progressively (`-edited` → `-e`)
2. If still too long, remove `-edited` entirely
3. Continue shrinking `name` from the right

Only `.<ext>` is preserved.

**For sidecar files:**

1. Shrink `.<metadata_suffix>` progressively (`.supplemental-metadata` → empty)
2. Shrink `.<media_ext>`
3. Continue shrinking `name` from the right

Only `.json` is preserved.

### Step 3: Resolve collisions

When writing to the export folder, if a filename already exists, append `(1)`. If `(1)` exists, use `(2)`, and so on.

> **Key insight**: `(N)` is not a property of the source file—it's a collision resolution mechanism applied at export time. The same source file could get different `(N)` values in different Takeouts depending on export order.

## Matching Challenges

### 1. Truncation causes ambiguity

Both media and sidecar file names can be truncated. This information loss makes it theoretically impossible to **guarantee** correct matches in all cases. The tool relies on heuristics and observed truncation patterns.

Truncation appears to occur for file names longer than ~40 characters, though the exact threshold is not known.

### 2. One sidecar → multiple media files

A single sidecar file can correspond to multiple media files:

- **Edited files**: Takeout exports both original and edited versions, but only one sidecar (for the original)
- **Live Photos** (iOS): `.heic` image + `.mp4` video share one sidecar
- **Motion Photos** (Google): `.MP.jpg` files share sidecar with companion `.jpg`

### 3. Collision marker position differs

The collision marker `(N)` appears in different positions:

| Type    | Pattern                                   |
| ------- | ----------------------------------------- |
| Media   | `photo(1).jpg`                            |
| Sidecar | `photo.jpg.supplemental-metadata(1).json` |
