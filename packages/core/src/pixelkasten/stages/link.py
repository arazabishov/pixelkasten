"""
Sidecar matching — link media files to their Google Takeout JSON metadata.

Ported from packages/core/src/stages/link.js. Handles Google's complex
filename truncation patterns documented in docs/takeout.md.

IMPORTANT: Uses os.path for filename decomposition, NOT pathlib. pathlib
silently normalizes double extensions (.MP.jpg) and duplicate markers (1).
"""

import os
import re
from typing import NamedTuple

from pixelkasten.core.types import ManifestEntry, Sidecar, Source
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


class MediaParsed(NamedTuple):
    name: str
    duplicate: int | None
    extension: str  # lowercase, with dot (e.g., ".jpg") or ""


class SidecarParsed(NamedTuple):
    name: str
    duplicate: int | None
    extension: str  # lowercase, with dot (e.g., ".jpg") or ""


def link(raw_collections: dict, options: Options) -> dict:
    """
    Match media files to their JSON sidecar metadata files.

    For each media file, attempts an exact match first (name + extension +
    duplicate marker), then falls back to fuzzy matching for truncated
    filenames if no exact match is found.

    Args:
        raw_collections: Dict with files_media, files_metadata, files_metadata_albums.
        options: Dict with fuzzy_threshold (int), fuzzy (bool, default True).

    Returns:
        {"manifest": [...], "stats": {"unmatched_metadata_files": set, "unmatched_media_files": set}}
    """
    files_media = raw_collections["files_media"]
    files_metadata = raw_collections["files_metadata"]
    files_metadata_albums = raw_collections.get("files_metadata_albums", [])

    # Stage 1: index metadata by directory for O(1) lookups.
    metadata_by_dir: dict[str, list[dict]] = {}
    for file_path in files_metadata:
        dir_path = os.path.dirname(file_path)
        parsed = parse_sidecar(file_path)
        entry = {"path": file_path, **parsed._asdict()}
        metadata_by_dir.setdefault(dir_path, []).append(entry)

    # Stage 2: index albums by directory.
    albums: dict[str, str] = {}
    for path in files_metadata_albums:
        dir_path = os.path.dirname(path)
        albums[dir_path] = os.path.basename(dir_path)

    # Stage 3: pre-parse media files for performance.
    parsed_media = []
    for file_path in files_media:
        parsed = parse_media(file_path)
        parsed_media.append({"path": file_path, **parsed._asdict()})

    # Stage 4: match media files to their metadata sidecars.
    manifest: list[ManifestEntry] = []
    for media_entry in parsed_media:
        dir_path = os.path.dirname(media_entry["path"])
        candidates = metadata_by_dir.get(dir_path, [])

        source = (
            Source(type="album", name=albums[dir_path])
            if dir_path in albums
            else Source(type="loose")
        )

        sidecar_match = _match(media_entry, candidates, options)
        sidecar = (
            Sidecar(path=sidecar_match["path"], confidence=sidecar_match["confidence"])
            if sidecar_match
            else None
        )

        manifest.append(
            ManifestEntry(
                media_path=media_entry["path"],
                source=source,
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


def parse_media(file_path: str) -> MediaParsed:
    """
    Parse a media file path into components for matching.

    Strips the duplicate marker (N) and -edited variants before returning
    the base name used for comparison.
    """
    base = os.path.basename(file_path)
    extension = os.path.splitext(base)[1]
    name = base[: len(base) - len(extension)] if extension else base

    # Strip duplicate marker (N) from the end.
    dup_match = _DUPLICATE_PATTERN.search(name)
    duplicate = int(dup_match.group(1)) if dup_match else None
    if dup_match:
        name = name[: dup_match.start()]

    # Strip -edited variants from the end.
    edited_match = _EDITED_SUFFIX_PATTERN.search(name)
    if edited_match:
        name = name[: edited_match.start()]

    return MediaParsed(
        name=name,
        duplicate=duplicate,
        extension=extension.lower() if extension else "",
    )


def parse_sidecar(file_path: str) -> SidecarParsed:
    """
    Parse a sidecar JSON file path into components for matching.

    Strips .json, duplicate marker, metadata suffix, then extracts the
    media extension from what remains.
    """
    base = os.path.basename(file_path)

    # Strip .json extension.
    name = base[: len(base) - len(os.path.splitext(base)[1])]

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
    extension = os.path.splitext(name)[1]
    if extension:
        name = name[: len(name) - len(extension)]

    return SidecarParsed(
        name=name,
        duplicate=duplicate,
        extension=extension.lower() if extension else "",
    )


def _match(media_parsed: dict, candidates: list[dict], options: Options) -> dict | None:
    """Find the best metadata match for a media file within the same directory."""
    best_match = None
    best_score = 0

    for metadata in candidates:
        # Strict duplicate check: (1) must always match (1).
        if media_parsed["duplicate"] != metadata["duplicate"]:
            continue

        score = _match_score(media_parsed, metadata, options)
        if score > best_score:
            best_score = score
            best_match = metadata

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


def _match_score(media_parsed: dict, metadata_parsed: dict, options: Options) -> int:
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

    media_name = media_parsed["name"]
    media_ext = media_parsed["extension"]
    metadata_name = metadata_parsed["name"]
    metadata_ext = metadata_parsed["extension"]

    # Case 1: direct name match.
    if media_name == metadata_name:
        if metadata_ext and metadata_ext == media_ext:
            return 150
        return 100

    # Case 2: embedded extension match. Handles cases like:
    #   media: "123.mp" (name="123", ext=".mp")
    #   metadata name: "123.mp"
    composite_name = f"{media_name}{media_ext}".lower()
    if composite_name == metadata_name.lower():
        return 100

    # Fuzzy matching disabled.
    if not fuzzy:
        return 0

    # Case 3: fuzzy requires sufficient filename length.
    longer_name = max(len(media_name), len(metadata_name))
    if longer_name < threshold:
        return 0

    # Case 4: bidirectional prefix match.
    metadata_starts = metadata_name.startswith(media_name)
    media_starts = media_name.startswith(metadata_name)

    if media_starts or metadata_starts:
        return 50 + min(len(media_name), len(metadata_name))

    return 0
