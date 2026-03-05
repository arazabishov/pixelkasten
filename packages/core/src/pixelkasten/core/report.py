"""
CSV report generation — summarize pipeline results per file.

Ported from packages/core/src/core/report.js. Uses Python stdlib csv module.
"""

import csv
import os

from pixelkasten.core.types import ApplyResult, DedupeResult, ManifestEntry, Status
from pixelkasten.configuration import Options


def report(manifest: list[ManifestEntry], options: Options) -> str:
    """
    Write a per-file CSV report to the destination directory.

    Columns: media, metadata, confidence, status, reason
    All paths are relative to the source directory.

    Returns the path to the written report file.
    """
    if options.destination is None:
        raise ValueError("destination is required for report")

    report_path = os.path.join(options.destination, "report.csv")

    with open(report_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["media", "metadata", "confidence", "status", "reason"])

        for entry in manifest:
            # Use forward slashes in CSV output (portable, matches Node.js behavior)
            media = os.path.relpath(entry.media_path, options.source).replace("\\", "/")

            metadata = ""
            if entry.sidecar and entry.sidecar.path:
                metadata = os.path.relpath(entry.sidecar.path, options.source).replace("\\", "/")

            confidence = ""
            if entry.sidecar and entry.sidecar.confidence is not None:
                confidence = str(entry.sidecar.confidence)

            status_info = resolve_status(entry)

            writer.writerow(
                [
                    media,
                    metadata,
                    confidence,
                    status_info["status"],
                    status_info["reason"],
                ]
            )

    return report_path


def resolve_status(entry: ManifestEntry) -> dict:
    """
    Walk the entry's stage properties to find its terminal status.

    Priority order:
    1. apply.result == EMBEDDED
    2. apply.result == COPIED
    3. apply.status == ERROR
    4. metadata.status == SKIPPED
    5. dedupe.result == DELETE
    6. dedupe.status == ERROR
    7. Fallback: error/unknown
    """
    if entry.apply is not None:
        if entry.apply.result == ApplyResult.EMBEDDED:
            return {"status": "embedded", "reason": ""}

        if entry.apply.result == ApplyResult.COPIED:
            return {"status": "copied", "reason": ""}

        if entry.apply.status == Status.ERROR:
            return {"status": "error", "reason": entry.apply.error or ""}

    if entry.metadata is not None and entry.metadata.status == Status.SKIPPED:
        return {"status": "skipped", "reason": entry.metadata.error or ""}

    if entry.dedupe is not None:
        if entry.dedupe.result == DedupeResult.DELETE:
            return {"status": "deleted", "reason": ""}

        if entry.dedupe.status == Status.ERROR:
            return {"status": "error", "reason": entry.dedupe.error or ""}

    return {"status": "error", "reason": "Unknown state"}
