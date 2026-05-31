"""
CSV report generation — summarize pipeline results per file.

Ported from packages/core/src/core/report.js. Uses Python stdlib csv module.
"""

import csv
import os

from pixelkasten.configuration import IngestOptions
from pixelkasten.stores.record import records_dir
from pixelkasten.commands.ingest.types import ApplyResult, DedupeResult, IngestEntry
from pixelkasten.types import Status


def report(manifest: list[IngestEntry], options: IngestOptions) -> str:
    """
    Write a per-file CSV report inside the records directory.

    Columns: media, metadata, confidence, status, reason. Paths are
    relative to the source directory. Lives under ``.pixelkasten/`` next
    to the per-asset records — it's metadata about the run, not a media
    artifact, so it shouldn't sit next to media files.

    Returns the path to the written report file.
    """
    if options.destination is None:
        raise ValueError("destination is required for report")

    rdir = records_dir(options.destination)
    os.makedirs(rdir, exist_ok=True)
    report_path = os.path.join(rdir, "report.csv")

    with open(report_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["media", "metadata", "confidence", "status", "reason"])

        for entry in manifest:
            status, reason = _resolve_status(entry)

            writer.writerow(
                [
                    _relpath(entry.media_path, options.source),
                    _relpath(entry.sidecar.path, options.source) if entry.sidecar else "",
                    str(entry.sidecar.confidence) if entry.sidecar else "",
                    status,
                    reason,
                ]
            )

    return report_path


def _resolve_status(entry: IngestEntry) -> tuple[str, str]:
    """
    Determine what happened to an entry by checking stages in reverse
    pipeline order. Later stages take priority because they represent
    the final outcome — an apply error overrides a successful dedupe.
    """
    if entry.apply is not None:
        if entry.apply.result == ApplyResult.WRITTEN:
            return ("written", "")

        if entry.apply.result == ApplyResult.COPIED:
            return ("copied", "")

        if entry.apply.status == Status.ERROR:
            return ("error", entry.apply.error or "")

    if entry.metadata is not None and entry.metadata.status == Status.SKIPPED:
        return ("skipped", entry.metadata.error or "")

    if entry.dedupe is not None:
        if entry.dedupe.result == DedupeResult.DELETE:
            return ("deleted", "")

        if entry.dedupe.status == Status.ERROR:
            return ("error", entry.dedupe.error or "")

    return ("error", "Unknown state")


def _relpath(path: str, base: str) -> str:
    """Relative path with forward slashes for portable CSV output."""
    return os.path.relpath(path, base).replace("\\", "/")
