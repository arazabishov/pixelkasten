# Archive Naming Scheme

## Problem

The current rename stage (`packages/core/src/stages/rename.js`) uses full month names in directory paths (e.g., `03 - March`, `09 - September`). These have variable character widths which look misaligned in:
- macOS Finder (proportional font — even digits have uneven widths)
- Any GUI file manager using a proportional font

Since Finder uses proportional fonts for *everything* including digits, no naming scheme will ever look perfectly aligned in Finder. This is Finder's limitation, not ours. Given that, we optimize for the one place where alignment *does* work: the terminal (monospaced fonts).

## Directory Format

### Current
```
2024/03 - March/
2024/09 - September/
```

### Proposed
```
2024/03 - Mar/
2024/09 - Sep/
```

**Change:** 3-character month abbreviations instead of full names.

**Rationale:**
- All 3-char abbreviations are universally understood (Jan, Feb, Mar, Apr, May, Jun, Jul, Aug, Sep, Oct, Nov, Dec).
- In a monospaced terminal, every directory name renders at the same width: `NN - NNN` (8 characters).
- In Finder, they're no worse than full names (alignment is broken regardless) but are more compact.

**Implementation:** Change the `Intl.DateTimeFormat` formatter in `rename.js` from `{ month: "long" }` to `{ month: "short" }` and strip any trailing period (some locales add one).

## Filename Format

### Current
```
20240301-133245.jpg
```

### Proposed: Keep Current (No Change)

The compact `yyyymmdd-hhmmss` format should stay as-is.

**Why not `2024-03-01_133245`?**

The motivation for adding dashes to the date is readability: `2024-03-01` is easier to parse at a glance than `20240301`. But introducing dashes in the date creates a separator problem — you need a different character to separate date from time, and the underscore (`_`) is the natural candidate. The underscore works functionally but doesn't look great aesthetically.

The compact format avoids this entirely:
- The single dash is an unambiguous separator: 8 digits (date), dash, 6 digits (time).
- The directory structure `2024/03 - Mar/` already provides human-readable date context. The filename's primary job is to sort correctly and be unique — not to be read as a standalone date.
- It's proven and already in use. Changing it means re-renaming the entire existing archive.

### Collision Handling (Unchanged)

When two files produce the same timestamp:
```
20240301-133245.jpg
20240301-133245-1.jpg
20240301-133245-2.jpg
```

Suffix counter starts at 1 and increments until unique.

## Album Directories

### Current
```
2024/04 - April/20240415 - Trip to Japan/
```

### Proposed
```
2024/04 - Apr/20240415 - Trip to Japan/
```

Only the month directory changes (3-char abbreviation). The album subdirectory format `yyyymmdd - Album Name` stays the same — the compact date prefix ensures albums sort chronologically, and the name provides context.

## Complete Structure

```
destination/
  2024/
    03 - Mar/
      20240301-133245.jpg
      20240315-091200.heic
      20240315-091200-1.heic
    04 - Apr/
      20240415 - Trip to Japan/
        20240415-103000.jpg
        20240418-142530.mov
    12 - Dec/
      20241225-180000.jpg
      20241231 - New Year Party/
        20241231-230000.jpg
        20250101-001500.jpg
```

## Durability Argument

This scheme is durable because it contains no subjective formatting choices:

- **Digits and separators only** in filenames — nothing subject to taste.
- **3-char month abbreviations** are an ISO/international standard (ISO 8601 doesn't mandate them, but they're universally understood and won't change).
- **Lexicographic sort = chronological sort** at every level.
- **No dependencies** on font rendering, OS, or file manager behavior.

The only scenario that would force a rename is if we later add AI-derived semantic labels to the directory structure (e.g., `2024/03 - Mar/Beach Trip/`). This spec intentionally keeps the date-based scheme as the foundation, with semantic organization handled separately at a higher level if needed.
