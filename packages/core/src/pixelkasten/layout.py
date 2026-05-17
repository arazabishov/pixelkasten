"""
On-disk layout of a pixelkasten working library.

These constants and helpers describe where things live in a working library
relative to its root. Every reader and writer goes through this module so
the on-disk schema lives in one place.

Terminology: a ``.pk.json`` file is a **record** (the canonical per-asset
state across the lifecycle, owned by pixelkasten). The word "sidecar" is
reserved for Google Takeout's ``.json`` files that ``import`` consumes — a
different format with a different purpose.
"""

import json
import os

# Working-library directory names and file names.
RECORDS_DIR = ".pixelkasten"
RECORD_SUFFIX = ".pk.json"
EMBEDDINGS_NPY = "embeddings.npy"
EMBEDDINGS_PATHS_JSON = "embeddings.paths.json"


def records_dir(library: str) -> str:
    """Absolute path to the records directory inside ``library``."""
    return os.path.join(library, RECORDS_DIR)


def record_path(library: str, asset_name: str) -> str:
    """Absolute path of the record file for ``asset_name`` inside ``library``.

    ``asset_name`` is the media filename only (e.g. ``3f2a1b8c.heic``), not
    a full path.
    """
    return os.path.join(library, RECORDS_DIR, asset_name + RECORD_SUFFIX)


def embeddings_npy_path(library: str) -> str:
    return os.path.join(library, RECORDS_DIR, EMBEDDINGS_NPY)


def embeddings_paths_json_path(library: str) -> str:
    return os.path.join(library, RECORDS_DIR, EMBEDDINGS_PATHS_JSON)


def read_record(path: str) -> dict:
    """Read a ``.pk.json`` record. Raises if missing — keepers always have one."""
    if not os.path.exists(path):
        raise RuntimeError(f"No record at {path}; was this asset emitted by import?")
    with open(path) as f:
        return json.load(f)


def write_record(path: str, data: dict) -> None:
    """Write a ``.pk.json`` record."""
    with open(path, "w") as f:
        json.dump(data, f)


def resolve_library(asset_path: str) -> str:
    """Walk up from ``asset_path`` until a directory containing the records
    directory is found.

    Raises ``RuntimeError`` if no working library is found.
    """
    current = os.path.abspath(asset_path)
    if os.path.isfile(current):
        current = os.path.dirname(current)
    while True:
        if os.path.isdir(os.path.join(current, RECORDS_DIR)):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            raise RuntimeError(
                f"No {RECORDS_DIR}/ found at or above {asset_path}; "
                "pass --library explicitly if the file is outside any working library."
            )
        current = parent
