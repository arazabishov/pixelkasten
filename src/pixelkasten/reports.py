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

from pixelkasten.core.manifest import can_keep

# All summary tables use this minimum width for visual consistency.
TABLE_MIN_WIDTH = 44

# Progress bar labels are padded to this width so bars align vertically.
_PROGRESS_LABEL_WIDTH = 20


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
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            task_id = progress.add_task(label, total=total)

            def update(completed: int) -> None:
                progress.update(task_id, completed=completed)

            yield update

    return factory


# ---------------------------------------------------------------------------
# Summary table renderers — one per pipeline stage
# ---------------------------------------------------------------------------


def _make_table(title: str, header_left: str = "Category") -> Table:
    """Create a consistently-styled summary table with a stage title."""
    table = Table(
        show_header=True,
        show_edge=False,
        pad_edge=False,
        min_width=TABLE_MIN_WIDTH,
        title=f"[bold]{title}[/bold]",
        title_style="",
        title_justify="left",
    )
    table.add_column(header_left, style="cyan")
    table.add_column("Count", justify="right")
    return table


def render_scan_table(
    console: Console, raw_collections: dict, source_path: str
) -> None:
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
        json_info = entry.get("json")
        if json_info and json_info.get("confidence"):
            c = json_info["confidence"]
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


def render_reconcile_table(console: Console, manifest: list[dict]) -> None:
    """Render the reconcile stage summary table."""
    keepers = [e for e in manifest if can_keep(e)]

    n_processed = sum(
        1 for e in keepers if e.get("metadata", {}).get("status") == "processed"
    )
    n_skipped = sum(
        1 for e in keepers if e.get("metadata", {}).get("status") == "skipped"
    )
    n_error = sum(1 for e in keepers if e.get("metadata", {}).get("status") == "error")
    n_noop = sum(1 for e in keepers if e.get("metadata", {}).get("status") == "noop")

    table = _make_table("Reconcile", "Action")
    table.add_row("To update", str(n_processed))
    table.add_row("Noop", str(n_noop))
    if n_skipped:
        table.add_row("Unsupported", str(n_skipped))
    if n_error:
        table.add_row("[red]Errors[/red]", f"[red]{n_error}[/red]")

    console.print(table)
    console.print()


def render_dedupe_table(console: Console, manifest: list[dict]) -> None:
    """Render the dedupe stage summary table."""
    n_delete = sum(1 for e in manifest if e.get("dedupe", {}).get("status") == "delete")
    n_keep = sum(1 for e in manifest if e.get("dedupe", {}).get("status") == "keep")
    n_error = sum(1 for e in manifest if e.get("dedupe", {}).get("status") == "error")

    table = _make_table("Dedupe")
    table.add_row("To keep", str(n_keep))
    if n_delete:
        table.add_row("To delete", str(n_delete))
    if n_error:
        table.add_row("[red]Errors[/red]", f"[red]{n_error}[/red]")

    console.print(table)
    console.print()


def render_rename_table(console: Console, manifest: list[dict]) -> None:
    """Render the rename stage summary table."""
    keepers = [e for e in manifest if can_keep(e)]

    n_processed = sum(
        1 for e in keepers if e.get("rename", {}).get("status") == "processed"
    )
    n_skipped = sum(1 for e in keepers if "rename" not in e)
    n_error = sum(1 for e in keepers if e.get("rename", {}).get("status") == "error")

    table = _make_table("Rename", "Action")
    table.add_row("To rename", str(n_processed))
    if n_skipped:
        table.add_row("Skipped", str(n_skipped))
    if n_error:
        table.add_row("[red]Errors[/red]", f"[red]{n_error}[/red]")

    console.print(table)
    console.print()


def render_apply_table(console: Console, manifest: list[dict]) -> None:
    """Render the apply stage summary table."""
    n_skipped = sum(
        1 for e in manifest if e.get("dedupe", {}).get("status") == "delete"
    )
    n_copied = sum(1 for e in manifest if e.get("apply", {}).get("status") == "copied")
    n_embedded = sum(
        1 for e in manifest if e.get("apply", {}).get("status") == "embedded"
    )
    n_error = sum(1 for e in manifest if e.get("apply", {}).get("status") == "error")

    table = _make_table("Apply", "Action")
    table.add_row("Embedded", str(n_embedded))
    table.add_row("Copied", str(n_copied))
    if n_skipped:
        table.add_row("Skipped (duplicates)", str(n_skipped))
    if n_error:
        table.add_row("[red]Errors[/red]", f"[red]{n_error}[/red]")

    console.print(table)
    console.print()


def render_error_table(console: Console, manifest: list[dict]) -> None:
    """Render a table of all files that encountered errors across all stages."""
    errors: list[tuple[str, str, str]] = []

    for entry in manifest:
        path = entry.get("mediaPath", "unknown")
        filename = os.path.basename(path)

        dedupe = entry.get("dedupe", {})
        if dedupe.get("status") == "error":
            errors.append((filename, "Hash", dedupe.get("reason", "unknown")))

        metadata = entry.get("metadata", {})
        if metadata.get("status") == "error":
            errors.append((filename, "Reconcile", metadata.get("reason", "unknown")))

        rename_info = entry.get("rename", {})
        if rename_info.get("status") == "error":
            errors.append((filename, "Rename", rename_info.get("reason", "unknown")))

        apply_info = entry.get("apply", {})
        if apply_info.get("status") == "error":
            reason = apply_info.get("reason", "unknown")
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
        min_width=TABLE_MIN_WIDTH,
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
