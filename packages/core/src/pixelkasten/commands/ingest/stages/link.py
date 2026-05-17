"""
Link media files to their Google Takeout JSON sidecars.

Ported from packages/core/src/stages/link.js. Handles Google's complex
filename truncation patterns documented in docs/takeout.md.

IMPORTANT: Uses os.path for filename decomposition, NOT pathlib. pathlib
silently normalizes double extensions (.MP.jpg) and duplicate markers (1).
"""

import os
import re

from pixelkasten.manifest import ManifestEntry, SidecarMatch, Source
from pixelkasten.configuration import Options

# Truncated variants of .supplemental-metadata (longest first for greedy matching).
_METADATA_SUFFIX_PATTERN = re.compile(
    "|".join(
        [
            r"\.supplemental-metadata",
            r"\.supplemental-metadat",
            r"\.supplemental-metada",
            r"\.supplemental-metad",
            r"\.supplemental-meta",
            r"\.supplemental-met",
            r"\.supplemental-me",
            r"\.supplemental-m",
            r"\.supplemental-",
            r"\.supplemental",
            r"\.supplementa",
            r"\.supplement",
            r"\.supplemen",
            r"\.suppleme",
            r"\.supplem",
            r"\.supple",
            r"\.suppl",
            r"\.supp",
            r"\.sup",
            r"\.su",
            r"\.s",
        ]
    )
    + "$"
)

# Truncated variants of -edited (longest first for greedy matching).
_EDITED_SUFFIX_PATTERN = re.compile(r"(?:-edited|-edite|-edit|-edi|-ed|-e)$")

# Duplicate marker: (N) at end of filename.
_DUPLICATE_PATTERN = re.compile(r"\((\d+)\)$")


def link(raw_collections: dict, options: Options) -> dict:
    """
    Match media files to their JSON sidecar metadata files.

    Dispatches by mode: archive input never has Takeout sidecars but its
    subfolder names are propagated as album hints; Takeout input runs the
    full per-directory matcher with exact, embedded-extension, and
    fuzzy-truncation passes.
    """
    if options.mode == "archive":
        return _link_archive(raw_collections["files_media"], options.source)
    return _link_takeout(raw_collections, options)


def _link_archive(files_media: list[str], source_root: str) -> dict:
    """Archive mode: no sidecar matching. Files in subfolders inherit the
    folder name as ``source.name`` (treated as an album hint downstream);
    files at the source root stay loose."""
    source_root = os.path.normpath(source_root)
    manifest = [
        ManifestEntry(
            media_path=fp,
            source=_archive_source(fp, source_root),
            name=_parse_name(fp),
            sidecar=None,
        )
        for fp in files_media
    ]
    return {
        "manifest": manifest,
        "stats": {
            "unmatched_metadata_files": set(),
            "unmatched_media_files": set(files_media),
        },
    }


def _archive_source(file_path: str, source_root: str) -> Source:
    """Return ``Source(album, <parent folder name>)`` for files nested under
    the source root, or ``Source(loose)`` for files directly at the root.

    Nested folders collapse to their immediate parent's basename, matching
    Takeout's single-level album convention. ``<root>/Wedding/Day1/x.jpg``
    therefore belongs to album ``Day1``, not ``Wedding`` or ``Wedding/Day1``.
    """
    parent = os.path.normpath(os.path.dirname(file_path))
    if parent == source_root:
        return Source(type="loose")
    return Source(type="album", name=os.path.basename(parent))


def _link_takeout(raw_collections: dict, options: Options) -> dict:
    """Takeout mode: per-directory match each media file to its JSON sidecar."""
    files_media = raw_collections["files_media"]
    files_metadata = raw_collections["files_metadata"]
    files_metadata_albums = raw_collections.get("files_metadata_albums", [])

    # Stage 1: index metadata by directory for O(1) lookups.
    metadata_by_dir: dict[str, list[dict]] = {}
    for file_path in files_metadata:
        parsed = _parse_sidecar(file_path)
        dir_path = os.path.dirname(file_path)
        metadata_by_dir.setdefault(dir_path, []).append(parsed)

    # Stage 2: index albums by directory.
    albums: dict[str, str] = {}
    for path in files_metadata_albums:
        dir_path = os.path.dirname(path)
        albums[dir_path] = os.path.basename(dir_path)

    # Stage 3: pre-parse media files for performance.
    parsed_media = [_parse_media(fp) for fp in files_media]

    # Stage 4: match media files to their metadata sidecars.
    manifest: list[ManifestEntry] = []
    for media in parsed_media:
        dir_path = os.path.dirname(media["path"])
        candidates = metadata_by_dir.get(dir_path, [])

        source = (
            Source(type="album", name=albums[dir_path])
            if dir_path in albums
            else Source(type="loose")
        )

        sidecar_match = _match(media, candidates, options)
        sidecar = (
            SidecarMatch(path=sidecar_match["path"], confidence=sidecar_match["confidence"])
            if sidecar_match
            else None
        )

        manifest.append(
            ManifestEntry(
                media_path=media["path"],
                source=source,
                name=media["name"],
                sidecar=sidecar,
            )
        )

    # Stage 5: compute statistics from the manifest.
    unmatched_metadata = set(files_metadata)
    unmatched_media = set(files_media)

    for entry in manifest:
        if entry.sidecar:
            unmatched_metadata.discard(entry.sidecar.path)
            unmatched_media.discard(entry.media_path)

    return {
        "manifest": manifest,
        "stats": {
            "unmatched_metadata_files": unmatched_metadata,
            "unmatched_media_files": unmatched_media,
        },
    }


def _parse_name(file_path: str) -> str:
    """Return the canonical stem of a media filename: extension, ``(N)``
    duplicate marker, and ``-edited`` suffix removed. Link writes the result
    to ``ManifestEntry.name`` so downstream stages can read it directly
    instead of re-parsing the path."""
    base = os.path.basename(file_path)
    name, _ = os.path.splitext(base)

    dup_match = _DUPLICATE_PATTERN.search(name)
    if dup_match:
        name = name[: dup_match.start()]

    edited_match = _EDITED_SUFFIX_PATTERN.search(name)
    if edited_match:
        name = name[: edited_match.start()]

    return name


def _parse_media(file_path: str) -> dict:
    """Parse a media file path into components for matching."""
    base = os.path.basename(file_path)
    _, extension = os.path.splitext(base)
    name, _ = os.path.splitext(base)

    dup_match = _DUPLICATE_PATTERN.search(name)
    duplicate = int(dup_match.group(1)) if dup_match else None

    return {
        "path": file_path,
        "name": _parse_name(file_path),
        "duplicate": duplicate,
        "extension": extension.lower(),
    }


def _parse_sidecar(file_path: str) -> dict:
    """
    Parse a sidecar JSON file path into components for matching.

    Strips .json, duplicate marker, metadata suffix, then extracts the
    media extension from what remains.
    """
    base = os.path.basename(file_path)

    # Strip .json extension.
    name = os.path.splitext(base)[0]

    # Strip duplicate marker (N) from the end.
    dup_match = _DUPLICATE_PATTERN.search(name)
    duplicate = int(dup_match.group(1)) if dup_match else None
    if dup_match:
        name = name[: dup_match.start()]

    # Strip metadata suffix from the end.
    meta_match = _METADATA_SUFFIX_PATTERN.search(name)
    if meta_match:
        name = name[: meta_match.start()]

    # Extract extension (e.g., .jpg from "photo.jpg").
    name, extension = os.path.splitext(name)

    return {
        "path": file_path,
        "name": name,
        "duplicate": duplicate,
        "extension": extension.lower(),
    }


def _match(media: dict, candidates: list[dict], options: Options) -> dict | None:
    """Find the best metadata match for a media file within the same directory."""
    best_match = None
    best_score = 0

    for sidecar in candidates:
        # Strict duplicate check: (1) must always match (1).
        if media["duplicate"] != sidecar["duplicate"]:
            continue

        score = _match_score(media, sidecar, options)
        if score > best_score:
            best_score = score
            best_match = sidecar

    if not best_match:
        return None

    # Confidence levels based on match score.
    if best_score >= 150:
        confidence = 3
    elif best_score >= 100:
        confidence = 2
    else:
        confidence = 1

    return {"path": best_match["path"], "confidence": confidence}


def _match_score(media: dict, sidecar: dict, options: Options) -> int:
    """
    Calculate match score between a media file and a metadata file.

    Score hierarchy:
        150: Exact name + exact extension match (safest)
        100: Exact name match OR embedded extension match
        50+: Fuzzy/truncated name match (bidirectional prefix)
          0: No match
    """
    threshold = options.fuzzy_threshold
    fuzzy = options.fuzzy

    media_name = media["name"]
    media_ext = media["extension"]

    sidecar_name = sidecar["name"]
    sidecar_ext = sidecar["extension"]

    # Case 1: direct name match.
    if media_name == sidecar_name:
        if sidecar_ext and sidecar_ext == media_ext:
            return 150
        return 100

    # Case 2: embedded extension match. Handles cases like:
    #   media: "123.mp" (name="123", ext=".mp")
    #   metadata name: "123.mp"
    composite_name = f"{media_name}{media_ext}".lower()
    if composite_name == sidecar_name.lower():
        return 100

    # Fuzzy matching disabled.
    if not fuzzy:
        return 0

    # Case 3: fuzzy requires sufficient filename length.
    longer_name = max(len(media_name), len(sidecar_name))
    if longer_name < threshold:
        return 0

    # Case 4: bidirectional prefix match.
    sidecar_starts = sidecar_name.startswith(media_name)
    media_starts = media_name.startswith(sidecar_name)

    if media_starts or sidecar_starts:
        return 50 + min(len(media_name), len(sidecar_name))

    return 0
