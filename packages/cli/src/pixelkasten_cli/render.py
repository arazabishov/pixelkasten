"""
All Rich/terminal rendering for the CLI lives in this file.

Convention: every command has exactly one public renderer named
``render_<command>(console, value, *extras) -> None``. ``value`` is what
the command returned; ``*extras`` are whatever else the renderer needs to
do its job — typically the command's ``options`` (so result types don't
duplicate option fields) or other primitives. The CLI's job is to capture
the return value and call the matching renderer — nothing else. When
you're looking for "how does X get displayed", grep this file for
``render_x``.

Machine-output commands (``similar``, ``cluster``) write JSON to stdout via
``typer.echo`` instead of Rich; their renderers take ``console`` for
signature uniformity and ignore it.

This is the only module that couples Rich to the command modules — every
file under ``packages/core`` stays UI-agnostic.
"""

import json
import os
from collections.abc import Callable
from contextlib import contextmanager

import typer
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
)
from rich.table import Column, Table

from pixelkasten.commands.enrich import EnrichState
from pixelkasten.commands.export import ExportResult
from pixelkasten.commands.ingest import IngestResult
from pixelkasten.configuration import ExportOptions, IngestOptions
from pixelkasten.handlers import is_image, is_video
from pixelkasten.commands.ingest.state import ApplyResult, DedupeResult, IngestEntry
from pixelkasten.pipeline import Status

# Progress bar labels are padded to this width so the bars start at the
# same column regardless of label length. Set to the longest label we use
# ("Emitting working library" = 24 chars) plus one space.
_PROGRESS_LABEL_WIDTH = 25

# Bar fills 28 columns — wide enough to read percentage progress at a glance.
_BAR_WIDTH = 28

# Summary tables pin their left column to this width so the column
# divider lands at the same screen position across every stage's table.
# Set to fit the longest label ("Matched (medium confidence)" = 27 chars)
# plus breathing room.
_TABLE_LABEL_WIDTH = 30

# Shared width for tables and the progress bar block so they align
# visually. Computed: spinner(2) + label + bar + pct(5) + gaps(3).
UI_WIDTH = _PROGRESS_LABEL_WIDTH + _BAR_WIDTH + 10


def build_progress_factory(console: Console) -> Callable:
    """
    Build a progress context-manager factory.

    Returns a callable: ``(label, total) -> ContextManager`` whose context
    manager yields an ``on_progress(completed)`` callback.
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


def render_import(console: Console, result: IngestResult, options: IngestOptions) -> None:
    """Render every stage's summary table from one IngestResult."""
    _render_scan_table(console, result.raw_collections)
    _render_link_table(console, result.manifest, result.link_stats)
    if any(e.dedupe is not None for e in result.manifest):
        _render_dedupe_table(console, result.manifest)
    _render_reconcile_table(console, result.manifest)
    if not options.dry_run:
        _render_apply_table(console, result.manifest)
    _render_error_table(console, result.manifest)


def render_enrich(console: Console, state: EnrichState) -> None:
    """Two tables — geocoding totals, then embedding totals — plus failure sample.

    Every count is derived from the entries here, the same way ``render_import``
    derives its tables from the manifest — the state carries no counters.
    """
    entries = state.entries
    n_geocoded = sum(1 for e in entries if e.location is not None)
    n_no_geo = sum(1 for e in entries if e.location is None)

    geocode_table = _make_table("Reverse geocoding", "Action")
    geocode_table.add_row("Records", str(len(entries)))
    geocode_table.add_row("Geocoded", str(n_geocoded))
    geocode_table.add_row("No geo", str(n_no_geo))
    console.print(geocode_table)
    console.print()

    embedded = [e for e in entries if e.embed and e.embed.status == Status.PROCESSED]
    failed = [e for e in entries if e.embed and e.embed.status == Status.ERROR]

    embed_table = _make_table("Embedding", "Action")
    embed_table.add_row("Images embedded", str(sum(1 for e in embedded if is_image(e.media))))
    embed_table.add_row("Videos embedded", str(sum(1 for e in embedded if is_video(e.media))))
    if state.unmatched_media:
        embed_table.add_row("Unmatched media", str(len(state.unmatched_media)))
    if state.unmatched_records:
        embed_table.add_row("Unmatched records", str(len(state.unmatched_records)))
    if state.unsupported_media:
        embed_table.add_row("Unsupported files", str(len(state.unsupported_media)))
    if failed:
        embed_table.add_row("[red]Failed[/red]", f"[red]{len(failed)}[/red]")
    console.print(embed_table)

    # Inline a small sample of failure paths so the user knows which files to investigate.
    if failed:
        console.print()
        console.print("[red]Failed paths (first 3):[/red]")
        for entry in failed[:3]:
            console.print(f"  {entry.media}")
    console.print()


def render_export(console: Console, summary: ExportResult, options: ExportOptions) -> None:
    """Dry-run lists the planned copies; both modes print a one-line count summary.

    total/undated are derived from the operations here — the result stores no counts.
    """
    operations = summary.operations
    if options.dry_run:
        for src, dst in operations:
            typer.echo(f"copy {src} -> {dst}")

    dest = os.path.normpath(summary.destination)
    undated = sum(1 for _, dst in operations if os.path.dirname(dst) == dest)
    label = "Would export" if options.dry_run else "Exported"
    console.print(
        f"{label} {len(operations)} file(s) to {summary.destination} ({undated} undated)."
    )


def render_propose(console: Console, paths: list[str], album: str | None) -> None:
    """One-line confirmation of how many records were updated and to what value."""
    action = "cleared proposed_album on" if album is None else f"set proposed_album={album!r} on"
    typer.echo(f"{action} {len(paths)} file(s)")


def render_caption(console: Console, text: str | None) -> None:
    """Caption text to stdout for piping; nothing on failure (CLI exits non-zero)."""
    if text is not None:
        typer.echo(text)


def render_similar(console: Console, results: list[dict]) -> None:
    """Machine output: JSON list of {path, score} to stdout."""
    typer.echo(json.dumps(results, indent=2))


def render_cluster(console: Console, groups: dict[int, list[str]]) -> None:
    """Machine output: JSON dict of {label: [paths]} to stdout."""
    typer.echo(json.dumps({str(k): v for k, v in groups.items()}, indent=2))


def _make_table(title: str, header_left: str = "Category") -> Table:
    """Consistently-styled summary table with a stage title.

    The left column is pinned to ``_TABLE_LABEL_WIDTH`` so the divider
    between label and count lines up across every table.
    """
    table = Table(
        show_header=True,
        show_edge=False,
        pad_edge=False,
        min_width=UI_WIDTH,
        title=f"[bold]{title}[/bold]",
        title_style="",
        title_justify="left",
    )
    table.add_column(header_left, style="cyan", min_width=_TABLE_LABEL_WIDTH)
    table.add_column("Count", justify="right")
    return table


def _render_scan_table(console: Console, raw_collections: dict) -> None:
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


def _render_link_table(console: Console, manifest: list[IngestEntry], stats: dict) -> None:
    confidence_counts = {3: 0, 2: 0, 1: 0}
    for entry in manifest:
        if entry.sidecar and entry.sidecar.confidence in confidence_counts:
            confidence_counts[entry.sidecar.confidence] += 1

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


def _render_reconcile_table(console: Console, manifest: list[IngestEntry]) -> None:
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


def _render_dedupe_table(console: Console, manifest: list[IngestEntry]) -> None:
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


def _render_apply_table(console: Console, manifest: list[IngestEntry]) -> None:
    n_skipped = sum(1 for e in manifest if e.dedupe and e.dedupe.result == DedupeResult.DELETE)
    n_copied = sum(1 for e in manifest if e.apply and e.apply.result == ApplyResult.COPIED)
    n_written = sum(1 for e in manifest if e.apply and e.apply.result == ApplyResult.WRITTEN)
    n_error = sum(1 for e in manifest if e.apply and e.apply.status == Status.ERROR)

    table = _make_table("Apply", "Action")
    table.add_row("Written", str(n_written))
    table.add_row("Copied", str(n_copied))
    if n_skipped:
        table.add_row("Skipped (duplicates)", str(n_skipped))
    if n_error:
        table.add_row("[red]Errors[/red]", f"[red]{n_error}[/red]")

    console.print(table)
    console.print()


def _render_error_table(console: Console, manifest: list[IngestEntry]) -> None:
    errors: list[tuple[str, str, str]] = []

    for entry in manifest:
        filename = os.path.basename(entry.media_path)

        if entry.dedupe and entry.dedupe.status == Status.ERROR:
            errors.append((filename, "Hash", entry.dedupe.error or "unknown"))

        if entry.metadata and entry.metadata.status == Status.ERROR:
            errors.append((filename, "Reconcile", entry.metadata.error or "unknown"))

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
