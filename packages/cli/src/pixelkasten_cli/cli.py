"""
CLI entry point — unified pipeline for photo library organization.

Usage:
    uv run pixelkasten -s <source> -d <destination>                    # default
    uv run pixelkasten -s <source> -d <destination> --takeout          # Google Takeout
    uv run pixelkasten -s <source> -d <destination> --dry-run          # preview
    uv run pixelkasten -s <source> -d <destination> --catalog          # AI albums
"""

import typer
from functools import partial
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
        ...,
        "--source",
        "-s",
        help="Source directory containing photos.",
        exists=True,
        file_okay=False,
        resolve_path=True,
    ),
    destination: Path | None = typer.Option(
        None,
        "--destination",
        "-d",
        help="Destination directory for organized output.",
        resolve_path=True,
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
    skip_rename: bool = typer.Option(
        False,
        "--skip-rename",
        help="Skip target path computation.",
    ),
    fuzzy: bool = typer.Option(
        True,
        "--fuzzy/--no-fuzzy",
        help="Enable fuzzy sidecar matching in link stage.",
    ),
    fuzzy_threshold: int = typer.Option(
        40,
        "--fuzzy-threshold",
        help="Minimum filename length for fuzzy sidecar matching.",
    ),
    prefer: str = typer.Option(
        "album",
        "--prefer",
        help="When deduplicating, prefer 'album' or 'loose' copies.",
    ),
    # Catalog-specific options
    clip_model: str = typer.Option(
        "ViT-L-14",
        "--clip-model",
        help="CLIP model name for image embeddings.",
    ),
    batch_size: int = typer.Option(
        32,
        "--batch-size",
        help="Batch size for CLIP embedding.",
    ),
    min_cluster_size: int = typer.Option(
        5,
        "--min-cluster-size",
        help="Minimum cluster size for HDBSCAN.",
    ),
    classify_threshold: float = typer.Option(
        0.15,
        "--classify-threshold",
        help="Zero-shot classification confidence threshold.",
    ),
    caption_model: str = typer.Option(
        "llava",
        "--caption-model",
        help="Ollama vision model for captioning.",
    ),
    organize_model: str = typer.Option(
        "qwen3.5:35b",
        "--organize-model",
        help="Ollama text model for album naming.",
    ),
):
    """
    Organize a photo library.

    Organize a photo library. Sidecar matching runs automatically when JSON
    metadata is present. Add --catalog for AI-powered album discovery.
    """
    # If a subcommand was invoked, let it handle things
    if ctx.invoked_subcommand is not None:
        return

    if destination is None and not dry_run:
        console.print("[red]--destination is required (unless --dry-run is set)[/red]")
        raise typer.Exit(code=1)

    from pixelkasten.configuration import Options, CatalogOptions
    from pixelkasten.pipeline import run_pipeline

    # Check exiftool if embedding or renaming is needed (mirrors pipeline gate)
    if not skip_embed or not skip_rename:
        from pixelkasten.core.exiftool import check_exiftool

        try:
            check_exiftool()
        except RuntimeError as e:
            console.print(f"[red]{e}[/red]")
            raise typer.Exit(code=1)

    progress, hooks = _build_pipeline_ui(console)

    catalog_opts = (
        CatalogOptions(
            clip_model=clip_model,
            batch_size=batch_size,
            min_cluster_size=min_cluster_size,
            classify_threshold=classify_threshold,
            caption_model=caption_model,
            organize_model=organize_model,
            skip_caption=skip_caption,
            skip_refine=skip_refine,
        )
        if catalog
        else None
    )

    options = Options(
        source=str(source),
        destination=str(destination) if destination else None,
        dry_run=dry_run,
        skip_dedupe=skip_dedupe,
        skip_embed=skip_embed,
        skip_rename=skip_rename,
        prefer=prefer,
        fuzzy=fuzzy,
        fuzzy_threshold=fuzzy_threshold,
        catalog=catalog_opts,
    )

    console.print(f"\n[bold]Processing photos from {source}...[/bold]")
    if catalog:
        console.print("  [cyan]AI album discovery enabled[/cyan]")
    console.print()

    manifest = run_pipeline(options, hooks, progress)

    # Final summary
    if dry_run:
        console.print(
            f"[yellow]Dry run — {len(manifest)} files processed, no files copied.[/yellow]"
        )
    else:
        console.print("[green bold]Done![/green bold]")


def _build_pipeline_ui(console):
    """Build progress factory and hooks for pipeline UI reporting."""
    from pixelkasten_cli.reports import (
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

    from pixelkasten.configuration import Hooks

    hooks = Hooks(
        on_scan=partial(render_scan_table, console),
        on_link=partial(render_link_table, console),
        on_reconcile=partial(render_reconcile_table, console),
        on_dedupe=partial(render_dedupe_table, console),
        on_rename=partial(render_rename_table, console),
        on_apply=partial(render_apply_table, console),
        on_errors=partial(render_error_table, console),
    )

    return progress, hooks
