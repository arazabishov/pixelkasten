"""Manifest serialization — write pipeline state to JSON for debugging."""

import json
import os
from dataclasses import asdict
from enum import Enum

from pixelkasten.configuration import Options
from pixelkasten.manifest import ManifestEntry


def write_manifest(manifest: list[ManifestEntry], options: Options) -> str:
    """
    Write the full manifest to a JSON file in the destination directory.

    Returns the path to the written file.
    """
    destination = options.destination if options.destination else options.source
    path = os.path.join(destination, "manifest.json")

    data = [asdict(entry) for entry in manifest]
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=_json_default)

    return path


def _json_default(obj):
    """Handle Enum serialization."""
    if isinstance(obj, Enum):
        return obj.value
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
