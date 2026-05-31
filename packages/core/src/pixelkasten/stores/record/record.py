"""
Record I/O, path helpers, and library detection.

A *record* is pixelkasten's canonical per-asset state, living under
``<library>/.pixelkasten/<asset>.pk.json``. (Distinct from a Google
Takeout *sidecar* — see ``stores/sidecar.py`` for those.) A working
library is identified by the presence of a records directory; that's
how ``records_dir_home`` walks up from any path to find its enclosing
library.

The ``Record`` model itself lives in ``types.py``; ``read_record`` parses
one off disk and ``write_record`` serializes it back.
"""

import json
import os

from pixelkasten.configuration import RECORD_SUFFIX, RECORDS_DIR
from pixelkasten.stores.record.types import Record


def records_dir(library: str) -> str:
    """Absolute path to the records directory inside ``library``."""
    return os.path.join(library, RECORDS_DIR)


def records_dir_home(asset_path: str) -> str:
    """Return the directory that hosts the records directory for ``asset_path``.

    Walks up from ``asset_path`` until a directory containing
    ``RECORDS_DIR`` is found and returns that directory — i.e. the
    working library root. Paired with ``records_dir(library)`` which
    goes the other way (library → records_dir path).

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


def record_path(library: str, asset_name: str) -> str:
    """Absolute path of the record file for ``asset_name`` inside ``library``.

    ``asset_name`` is the media filename only (e.g. ``3f2a1b8c.heic``), not
    a full path.
    """
    return os.path.join(library, RECORDS_DIR, asset_name + RECORD_SUFFIX)


def read_record(path: str) -> Record:
    """Read and parse a ``.pk.json`` record. Raises if missing — keepers always have one."""
    if not os.path.exists(path):
        raise RuntimeError(f"No record at {path}; was this asset emitted by import?")
    with open(path) as f:
        return Record.from_dict(path, json.load(f))


def write_record(record: Record) -> None:
    """Serialize ``record`` to its own ``path``."""
    with open(record.path, "w") as f:
        json.dump(record.to_dict(), f)
