"""
Write `proposed_album` to a file's sidecar and to all group siblings.

The agent calls `propose(path, "Album name")` after deciding where a photo
belongs. The tool finds every file in the working library sharing the same
GUID stem (Live Photo image+video, edited variants, etc.) and updates the
`proposed_album` field in each sidecar. Idempotent — re-running with the
same album is a no-op. Passing `album=None` removes the field (--clear).
"""

import json
import os

SIDECAR_DIR = ".pixelkasten"
SIDECAR_SUFFIX = ".pk.json"


def propose(path: str, album: str | None) -> list[str]:
    """
    Set `proposed_album` on the file's sidecar and on every group sibling.

    Returns the list of sidecar paths updated.
    """
    if album is not None:
        _validate_album_name(album)

    library = _resolve_library(path)
    stem = _stem(os.path.basename(path))
    siblings = _siblings(library, stem)
    if not siblings:
        raise RuntimeError(f"No working-library file with stem {stem!r} under {library}")

    updated: list[str] = []
    for sibling_name in siblings:
        sidecar_path = os.path.join(library, SIDECAR_DIR, sibling_name + SIDECAR_SUFFIX)
        if not os.path.exists(sidecar_path):
            # Defensive: emit would have written one for every keeper. Skip
            # silently rather than crashing on a partially-populated library.
            continue
        data = _read_json(sidecar_path)
        if album is None:
            data.pop("proposed_album", None)
        else:
            data["proposed_album"] = album
        _write_json(sidecar_path, data)
        updated.append(sidecar_path)
    return updated


def _validate_album_name(album: str) -> None:
    if not album.strip():
        raise ValueError("Album name must be non-empty.")
    if album.lower() == "null":
        raise ValueError("'null' is reserved; use --clear to remove proposed_album.")


def _resolve_library(path: str) -> str:
    current = os.path.dirname(os.path.abspath(path))
    while True:
        if os.path.isdir(os.path.join(current, SIDECAR_DIR)):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            raise RuntimeError(
                f"No {SIDECAR_DIR}/ found at or above {path}; is this inside a working library?"
            )
        current = parent


def _stem(filename: str) -> str:
    """Return everything before the last extension. `live.heic` -> `live`."""
    return os.path.splitext(filename)[0]


def _siblings(library: str, stem: str) -> list[str]:
    """Return basenames of files in `library` that share the given stem."""
    out: list[str] = []
    for name in os.listdir(library):
        if name.startswith("."):
            continue
        if not os.path.isfile(os.path.join(library, name)):
            continue
        if _stem(name) == stem:
            out.append(name)
    return sorted(out)


def _read_json(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def _write_json(path: str, data: dict) -> None:
    with open(path, "w") as f:
        json.dump(data, f)
