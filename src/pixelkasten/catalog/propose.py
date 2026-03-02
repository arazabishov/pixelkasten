"""
Propose stage — bridge LLM album naming with the source-agnostic rename stage.

Adapts the existing organize.py LLM logic for the unified pipeline. Instead
of writing organization.json, mutates manifest entries with source.type and
source.name so the rename stage can build the correct directory structure.
"""

import re

from pixelkasten.catalog.organize import propose_organization


# Pattern to extract album name from "YYYY/YYYYMMDD - Name" or "YYYY/Name".
_ALBUM_NAME_RE = re.compile(r"^\d{4}/(?:\d{8}\s*-\s*)?(.+)$")


def propose_albums(manifest: dict, options: dict | None = None) -> None:
    """
    Call LLM to propose album names, then mutate manifest entries.

    For each cluster that the LLM assigns a directory, extracts the album
    name and sets entry["source"] = {"type": "album", "name": name}.

    Entries not in any cluster (noise, cluster=-1) or in clusters the LLM
    didn't assign are left as-is (typically source.type = "loose").

    Args:
        manifest: Manifest dict with "entries" list and "clusters" dict.
        options: Dict with optional "model" key for Ollama model name.
    """
    options = options or {}
    model = options.get("model", "qwen3.5:35b")

    cluster_dirs = propose_organization(manifest, model=model)

    for entry in manifest.get("entries", []):
        cluster_id = str(entry.get("cluster", -1))

        if cluster_id not in cluster_dirs or cluster_id == "-1":
            continue

        dir_path = cluster_dirs[cluster_id]
        album_name = extract_album_name(dir_path)

        if album_name:
            entry["source"] = {"type": "album", "name": album_name}


def extract_album_name(dir_path: str) -> str | None:
    """
    Extract album name from an LLM-proposed directory path.

    Handles formats:
        "2024/20240715 - Beach Vacation" → "Beach Vacation"
        "2024/Beach Vacation"            → "Beach Vacation"
        "Unknown/Misc Photos"            → "Misc Photos"

    Returns None if the path can't be parsed.
    """
    m = _ALBUM_NAME_RE.match(dir_path)
    if m:
        return m.group(1).strip()

    # Fallback: try the last path component
    parts = dir_path.strip("/").split("/")
    if len(parts) >= 2:
        name = parts[-1]
        # Strip date prefix if present
        date_stripped = re.sub(r"^\d{8}\s*-\s*", "", name)
        return date_stripped.strip() if date_stripped.strip() else None

    return None
