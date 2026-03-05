"""
CSV report generation — summarize pipeline results per file.

Ported from packages/core/src/core/report.js. Uses Python stdlib csv module.
"""

import csv
import os

from pixelkasten.core.options import PipelineOptions


def report(manifest: list[dict], options: PipelineOptions) -> str:
    """
    Write a per-file CSV report to the destination directory.

    Columns: media, metadata, confidence, status, reason
    All paths are relative to the source directory.

    Returns the path to the written report file.
    """
    source = options.source
    destination = options.destination or ""

    report_path = os.path.join(destination, "report.csv")

    with open(report_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["media", "metadata", "confidence", "status", "reason"])

        for entry in manifest:
            # Use forward slashes in CSV output (portable, matches Node.js behavior)
            media = os.path.relpath(entry["mediaPath"], source).replace("\\", "/")

            metadata = ""
            json_info = entry.get("json")
            if json_info and json_info.get("path"):
                metadata = os.path.relpath(json_info["path"], source).replace("\\", "/")

            confidence = ""
            if json_info and json_info.get("confidence") is not None:
                confidence = str(json_info["confidence"])

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


def resolve_status(entry: dict) -> dict:
    """
    Walk the entry's stage properties to find its terminal status.

    Priority order:
    1. apply.status == "embedded"
    2. apply.status == "copied"
    3. apply.status == "error"
    4. metadata.status == "skipped"
    5. dedupe.status == "delete"
    6. dedupe.status == "error"
    7. Fallback: error/unknown
    """
    apply_status = entry.get("apply", {}).get("status")

    if apply_status == "embedded":
        return {"status": "embedded", "reason": ""}

    if apply_status == "copied":
        return {"status": "copied", "reason": ""}

    if apply_status == "error":
        return {"status": "error", "reason": entry.get("apply", {}).get("reason", "")}

    if entry.get("metadata", {}).get("status") == "skipped":
        return {
            "status": "skipped",
            "reason": entry.get("metadata", {}).get("reason", ""),
        }

    dedupe_status = entry.get("dedupe", {}).get("status")

    if dedupe_status == "delete":
        return {"status": "deleted", "reason": ""}

    if dedupe_status == "error":
        return {
            "status": "error",
            "reason": entry.get("dedupe", {}).get("reason", ""),
        }

    return {"status": "error", "reason": "Unknown state"}
