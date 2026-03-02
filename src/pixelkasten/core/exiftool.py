"""
ExifTool subprocess wrapper — read and write metadata.

Extracted from exif.py and extended with write support (ported from
packages/core/src/core/exiftool.js). Provides the low-level subprocess
interface; higher-level parsing lives in exif.py and handlers.py.
"""

import json
import subprocess
from pathlib import Path


def check_exiftool() -> None:
    """
    Verify that exiftool is installed and available on PATH.

    Raises RuntimeError with a clear installation message if not found.
    """
    try:
        result = subprocess.run(
            ["exiftool", "-ver"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            raise RuntimeError(
                "exiftool is installed but returned an error. Check your installation."
            )
    except FileNotFoundError:
        raise RuntimeError(
            "exiftool is not installed. Install it with: brew install exiftool"
        )


def read_metadata(
    file_paths: list[Path],
    tags: list[str] | None = None,
) -> dict[str, dict]:
    """
    Read metadata from files using exiftool.

    Args:
        file_paths: Paths to the files to read.
        tags: Metadata tags to extract (e.g., ["EXIF:DateTimeOriginal"]).
              If None or empty, reads default tags.

    Returns:
        Dict mapping SourceFile path to raw exiftool metadata dict.
    """
    if not file_paths:
        return {}

    args = [
        "exiftool",
        "-api",
        "largefilesupport=1",
        "-json",
        "-n",
        "-G",
        "-fast",
    ]

    if tags:
        for tag in tags:
            args.append(f"-{tag}")

    args.extend(["-@", "-"])

    stdin_text = "\n".join(str(p) for p in file_paths)

    result = subprocess.run(
        args,
        input=stdin_text,
        capture_output=True,
        text=True,
        timeout=300,
    )

    # exiftool returns 1 for minor warnings (missing tags), not errors.
    if result.returncode not in (0, 1):
        raise RuntimeError(f"Failed to read metadata using exiftool: {result.stderr}")

    if not result.stdout.strip():
        return {}

    entries = json.loads(result.stdout)
    return {entry.get("SourceFile", ""): entry for entry in entries}


def write_metadata(file_path: str | Path, tags: list[str]) -> None:
    """
    Write metadata tags to a file using exiftool.

    Args:
        file_path: Path to the file to write metadata to.
        tags: Tags to write (e.g., ["SubSecDateTimeOriginal=2023:05:20 14:30:00+00:00"]).
              If empty, returns immediately without calling exiftool.
    """
    if not tags:
        return

    args = [
        "exiftool",
        "-api",
        "largefilesupport=1",
        "-overwrite_original",
    ]

    for tag in tags:
        args.append(f"-{tag}")

    args.append(str(file_path))

    result = subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=60,
    )

    if result.returncode != 0:
        raise RuntimeError(f"Failed to write metadata using exiftool: {result.stderr}")
