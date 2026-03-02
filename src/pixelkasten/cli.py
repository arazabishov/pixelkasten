"""
CLI entry point — unified pipeline for photo library organization.

Usage:
    uv run pixelkasten -s <source> -d <destination>                    # takeout (default)
    uv run pixelkasten -s <source> -d <destination> --dry-run          # preview
    uv run pixelkasten -s <source> -d <destination> --no-takeout --catalog  # archive + AI
    uv run pixelkasten -s <source> -d <destination> -w ./workspace     # with caching
    uv run pixelkasten status -w ./workspace                           # inspect workspace
"""

import typer
from pathlib import Path
from rich.console import Console

app = typer.Typer(
    name="pixelkasten",
    help="Photo library organizer — Google Takeout processing and AI-powered categorization.",
    add_completion=False,
    invoke_without_command=True,
)
console = Console()


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    source: Path = typer.Option(
        None,
        "--source",
        "-s",
        help="Source directory containing photos.",
        exists=True,
        file_okay=False,
        resolve_path=True,
    ),
    destination: Path = typer.Option(
        None,
        "--destination",
        "-d",
        help="Destination directory for organized output.",
        resolve_path=True,
    ),
    takeout: bool = typer.Option(
        True,
        "--takeout/--no-takeout",
        help="Takeout mode (default) or archive mode.",
    ),
    catalog: bool = typer.Option(
        False,
        "--catalog",
        help="Enable AI-powered album discovery.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Preview plan without copying files.",
    ),
    skip_dedupe: bool = typer.Option(
        False,
        "--skip-dedupe",
        help="Skip SHA-256 deduplication.",
    ),
    skip_embed: bool = typer.Option(
        False,
        "--skip-embed",
        help="Skip writing sidecar metadata into files.",
    ),
    skip_caption: bool = typer.Option(
        False,
        "--skip-caption",
        help="Skip VLM captioning (catalog only).",
    ),
    skip_refine: bool = typer.Option(
        False,
        "--skip-refine",
        help="Skip temporal cluster refinement (catalog only).",
    ),
    workspace: Path = typer.Option(
        None,
        "--workspace",
        "-w",
        help="Workspace directory for caching init data and embeddings.",
        resolve_path=True,
    ),
    rescan: bool = typer.Option(
        False,
        "--rescan",
        help="Invalidate workspace cache, re-scan source.",
    ),
    prefer: str = typer.Option(
        "album",
        "--prefer",
        help="When deduplicating, prefer 'album' or 'loose' copies.",
    ),
):
    """
    Organize a photo library.

    By default, processes a Google Takeout export (--takeout). Use --no-takeout
    for plain photo archives. Add --catalog for AI-powered album discovery.
    """
    # If a subcommand was invoked, let it handle things
    if ctx.invoked_subcommand is not None:
        return

    # If no source provided, show help
    if source is None:
        console.print(ctx.get_help())
        return

    if destination is None and not dry_run:
        console.print("[red]--destination is required (unless --dry-run is set)[/red]")
        raise typer.Exit(code=1)

    from pixelkasten.pipeline import run_pipeline

    # Check exiftool if embedding is needed
    if not skip_embed and takeout:
        from pixelkasten.core.exiftool import check_exiftool

        try:
            check_exiftool()
        except RuntimeError as e:
            console.print(f"[red]{e}[/red]")
            raise typer.Exit(code=1)

    options = {
        "source": str(source),
        "destination": str(destination) if destination else "",
        "mode": "takeout" if takeout else "archive",
        "catalog": catalog,
        "dry_run": dry_run,
        "skip_dedupe": skip_dedupe,
        "skip_embed": skip_embed,
        "skip_caption": skip_caption,
        "skip_refine": skip_refine,
        "prefer": prefer,
        "fuzzy": True,
        "fuzzy_threshold": 40,
        "rescan": rescan,
    }

    if workspace:
        options["workspace"] = str(workspace)

    mode_label = "takeout" if takeout else "archive"
    console.print(f"\n[bold]Processing ({mode_label} mode) from {source}...[/bold]")
    if catalog:
        console.print("  [cyan]AI album discovery enabled[/cyan]")
    console.print()

    progress, hooks = _build_pipeline_ui(console)
    options["progress"] = progress
    manifest = run_pipeline(options, hooks)

    # Final summary
    if dry_run:
        console.print(
            f"[yellow]Dry run — {len(manifest)} files processed, no files copied.[/yellow]"
        )
    else:
        console.print("[green bold]Done![/green bold]")


def _build_pipeline_ui(console):
    """Build progress factory and hooks for pipeline UI reporting."""
    from pixelkasten.reports import (
        build_progress_factory,
        render_apply_table,
        render_dedupe_table,
        render_error_table,
        render_link_table,
        render_reconcile_table,
        render_rename_table,
        render_scan_table,
    )

    progress = build_progress_factory(console)

    hooks = {
        "on_scan": lambda raw, src: render_scan_table(console, raw, src),
        "on_link": lambda result: render_link_table(console, result),
        "on_reconcile": lambda manifest: render_reconcile_table(console, manifest),
        "on_dedupe": lambda manifest: render_dedupe_table(console, manifest),
        "on_rename": lambda manifest: render_rename_table(console, manifest),
        "on_apply": lambda manifest: render_apply_table(console, manifest),
        "on_errors": lambda manifest: render_error_table(console, manifest),
    }

    return progress, hooks


@app.command()
def status(
    workspace: Path = typer.Option(
        ...,
        "--workspace",
        "-w",
        help="Path to a workspace directory.",
        exists=True,
        file_okay=False,
        resolve_path=True,
    ),
):
    """Inspect a workspace manifest."""
    import json as json_mod

    manifest_path = workspace / "manifest.json"
    if not manifest_path.exists():
        console.print(f"[red]No manifest found in {workspace}[/red]")
        raise typer.Exit(code=1)

    with open(manifest_path) as f:
        manifest = json_mod.load(f)

    n_total = len(manifest)
    n_with_json = sum(1 for e in manifest if e.get("json"))
    n_with_dates = sum(1 for e in manifest if e.get("metadata", {}).get("dates"))

    console.print(f"\n[bold]Workspace: {workspace}[/bold]")
    console.print(f"  Total entries: {n_total}")
    console.print(f"  With sidecar match: {n_with_json}")
    console.print(f"  With timestamps: {n_with_dates}")

    embeddings_path = workspace / "embeddings.npy"
    if embeddings_path.exists():
        console.print("  Embeddings cached: yes")
    else:
        console.print("  Embeddings cached: no")
