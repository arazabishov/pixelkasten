"""
Rich UI components for pipeline progress reporting.

Contains the progress factory (creates Rich progress bar context managers)
and summary table renderers (one per pipeline stage). This is the only module
that couples Rich to the pipeline — stages and pipeline.py remain UI-agnostic.
"""

import os
from collections.abc import Callable
from contextlib import contextmanager

from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
)
from rich.table import Column, Table

from pixelkasten.manifest import ApplyResult, DedupeResult, ManifestEntry, Status

# Shared width for tables and progress bars so they align visually.
UI_WIDTH = 58

# Progress bar labels are padded to this width so bars align vertically.
_PROGRESS_LABEL_WIDTH = 20

# Bar fills the remaining space: UI_WIDTH - spinner(2) - label(20) - pct(5) - gaps(3).
_BAR_WIDTH = UI_WIDTH - 30


def build_progress_factory(console: Console) -> Callable:
    """
    Build a progress context-manager factory for the pipeline.

    Returns a callable: (label: str, total: int) -> ContextManager
    The context manager yields an on_progress(completed: int) callback.
    """

    @contextmanager
    def factory(label: str, total: int):
        with Progress(
            SpinnerColumn(),
            TextColumn(
                "[progress.description]{task.description}",
                table_column=Column(min_width=_PROGRESS_LABEL_WIDTH),
            ),
            BarColumn(bar_width=_BAR_WIDTH),
            TaskProgressColumn(),
            console=console,
            expand=False,
        ) as progress:
            task_id = progress.add_task(label, total=total)

            def update(completed: int) -> None:
                progress.update(task_id, completed=completed)

            yield update

    return factory


def _make_table(title: str, header_left: str = "Category") -> Table:
    """Create a consistently-styled summary table with a stage title."""
    table = Table(
        show_header=True,
        show_edge=False,
        pad_edge=False,
        min_width=UI_WIDTH,
        title=f"[bold]{title}[/bold]",
        title_style="",
        title_justify="left",
    )
    table.add_column(header_left, style="cyan")
    table.add_column("Count", justify="right")
    return table


def render_scan_table(console: Console, raw_collections: dict, source_path: str) -> None:
    """Render the scan stage summary table."""
    albums = raw_collections.get("files_metadata_albums", [])
    media = raw_collections.get("files_media", [])
    metadata = raw_collections.get("files_metadata", [])
    other = raw_collections.get("files_other_ignored", [])
    total = raw_collections.get("files_total", 0)

    table = _make_table("Scan")
    table.add_row("Albums", str(len(albums)))
    table.add_row("Media files", str(len(media)))
    table.add_row("Metadata files", str(len(metadata)))
    if other:
        table.add_row("Other files", str(len(other)))
    table.add_row("All files", str(total), style="bold")

    console.print(table)
    console.print()


def render_link_table(console: Console, result: dict) -> None:
    """Render the link stage summary table."""
    manifest = result["manifest"]
    stats = result["stats"]

    confidence_counts = {3: 0, 2: 0, 1: 0}
    for entry in manifest:
        if entry.sidecar and entry.sidecar.confidence:
            c = entry.sidecar.confidence
            if c in confidence_counts:
                confidence_counts[c] += 1

    unmatched_metadata = stats.get("unmatched_metadata_files", set())
    unmatched_media = stats.get("unmatched_media_files", set())

    table = _make_table("Link")
    table.add_row("Matched (high confidence)", str(confidence_counts[3]))
    if confidence_counts[2]:
        table.add_row("Matched (medium confidence)", str(confidence_counts[2]))
    if confidence_counts[1]:
        table.add_row("Matched (satisfactory)", str(confidence_counts[1]))
    if unmatched_metadata:
        table.add_row("Unmatched metadata files", str(len(unmatched_metadata)))
    if unmatched_media:
        table.add_row("Unmatched media files", str(len(unmatched_media)))

    console.print(table)
    console.print()


def render_reconcile_table(console: Console, manifest: list[ManifestEntry]) -> None:
    """Render the reconcile stage summary table."""
    keepers = [e for e in manifest if e.can_keep()]

    n_processed = sum(
        1
        for e in keepers
        if e.metadata and e.metadata.status == Status.PROCESSED and e.metadata.write_tags
    )
    n_skipped = sum(1 for e in keepers if e.metadata and e.metadata.status == Status.SKIPPED)
    n_error = sum(1 for e in keepers if e.metadata and e.metadata.status == Status.ERROR)
    n_noop = sum(
        1
        for e in keepers
        if e.metadata and e.metadata.status == Status.PROCESSED and not e.metadata.write_tags
    )

    table = _make_table("Reconcile", "Action")
    table.add_row("To update", str(n_processed))
    table.add_row("Noop", str(n_noop))
    if n_skipped:
        table.add_row("Unsupported", str(n_skipped))
    if n_error:
        table.add_row("[red]Errors[/red]", f"[red]{n_error}[/red]")

    console.print(table)
    console.print()


def render_dedupe_table(console: Console, manifest: list[ManifestEntry]) -> None:
    """Render the dedupe stage summary table."""
    n_delete = sum(1 for e in manifest if e.dedupe and e.dedupe.result == DedupeResult.DELETE)
    n_keep = sum(1 for e in manifest if e.dedupe and e.dedupe.result == DedupeResult.KEEP)
    n_error = sum(1 for e in manifest if e.dedupe and e.dedupe.status == Status.ERROR)

    table = _make_table("Dedupe")
    table.add_row("To keep", str(n_keep))
    if n_delete:
        table.add_row("To delete", str(n_delete))
    if n_error:
        table.add_row("[red]Errors[/red]", f"[red]{n_error}[/red]")

    console.print(table)
    console.print()


def render_rename_table(console: Console, manifest: list[ManifestEntry]) -> None:
    """Render the rename stage summary table."""
    keepers = [e for e in manifest if e.can_keep()]

    n_processed = sum(1 for e in keepers if e.rename and e.rename.status == Status.PROCESSED)
    n_skipped = sum(1 for e in keepers if e.rename is None)
    n_error = sum(1 for e in keepers if e.rename and e.rename.status == Status.ERROR)

    table = _make_table("Rename", "Action")
    table.add_row("To rename", str(n_processed))
    if n_skipped:
        table.add_row("Skipped", str(n_skipped))
    if n_error:
        table.add_row("[red]Errors[/red]", f"[red]{n_error}[/red]")

    console.print(table)
    console.print()


def render_apply_table(console: Console, manifest: list[ManifestEntry]) -> None:
    """Render the apply stage summary table."""
    n_skipped = sum(1 for e in manifest if e.dedupe and e.dedupe.result == DedupeResult.DELETE)
    n_copied = sum(1 for e in manifest if e.apply and e.apply.result == ApplyResult.COPIED)
    n_embedded = sum(1 for e in manifest if e.apply and e.apply.result == ApplyResult.EMBEDDED)
    n_error = sum(1 for e in manifest if e.apply and e.apply.status == Status.ERROR)

    table = _make_table("Apply", "Action")
    table.add_row("Embedded", str(n_embedded))
    table.add_row("Copied", str(n_copied))
    if n_skipped:
        table.add_row("Skipped (duplicates)", str(n_skipped))
    if n_error:
        table.add_row("[red]Errors[/red]", f"[red]{n_error}[/red]")

    console.print(table)
    console.print()


def render_error_table(console: Console, manifest: list[ManifestEntry]) -> None:
    """Render a table of all files that encountered errors across all stages."""
    errors: list[tuple[str, str, str]] = []

    for entry in manifest:
        filename = os.path.basename(entry.media_path)

        if entry.dedupe and entry.dedupe.status == Status.ERROR:
            errors.append((filename, "Hash", entry.dedupe.error or "unknown"))

        if entry.metadata and entry.metadata.status == Status.ERROR:
            errors.append((filename, "Reconcile", entry.metadata.error or "unknown"))

        if entry.rename and entry.rename.status == Status.ERROR:
            errors.append((filename, "Rename", entry.rename.error or "unknown"))

        if entry.apply and entry.apply.status == Status.ERROR:
            reason = entry.apply.error or "unknown"
            # Strip long file paths from exiftool error messages.
            if " - /" in reason:
                reason = reason[: reason.index(" - /")]
            errors.append((filename, "Apply", reason))

    if not errors:
        return

    table = Table(
        show_header=True,
        show_edge=False,
        pad_edge=False,
        min_width=UI_WIDTH,
        title="[bold]Errors[/bold]",
        title_style="",
        title_justify="left",
    )
    table.add_column("File", style="cyan", no_wrap=True)
    table.add_column("Stage")
    table.add_column("Reason", style="red")

    for filename, stage, reason in errors:
        table.add_row(filename, stage, reason)

    console.print(table)
    console.print()
