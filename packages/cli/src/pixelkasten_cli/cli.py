"""
CLI entry point — pixelkasten subcommands.

Usage:
    uv run pixelkasten init --from-takeout -s <source> -d <destination>
    uv run pixelkasten init --from-archive -s <source> -d <destination>
"""

import os
import typer
from functools import partial
from pathlib import Path
from rich.console import Console

app = typer.Typer(
    name="pixelkasten",
    help="Photo library organizer.",
    add_completion=False,
    no_args_is_help=True,
)
console = Console()


@app.callback()
def _callback() -> None:
    """Photo library organizer."""


@app.command()
def init(
    from_takeout: bool = typer.Option(
        False,
        "--from-takeout",
        help="Treat the source as a Google Takeout export (matches JSON sidecars).",
    ),
    from_archive: bool = typer.Option(
        False,
        "--from-archive",
        help="Treat the source as a flat archive of media files with no sidecars.",
    ),
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
    skip_metadata_write: bool = typer.Option(
        False,
        "--skip-metadata-write",
        help="Skip writing sidecar metadata into files (Takeout mode).",
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
        help="When deduplicating, prefer 'album' or 'loose' copies (Takeout mode only).",
    ),
    write_manifest: bool = typer.Option(
        False,
        "--write-manifest",
        help="Save manifest as JSON in destination for debugging.",
    ),
):
    """Initialize a working library from a source directory."""
    mode = _resolve_mode(from_takeout, from_archive, source)

    if destination is None and not dry_run:
        console.print("[red]--destination is required (unless --dry-run is set)[/red]")
        raise typer.Exit(code=1)

    from pixelkasten.configuration import Options
    from pixelkasten.pipeline import run_pipeline

    if mode == "takeout" and not skip_metadata_write:
        from pixelkasten.tools.exiftool import check_exiftool

        try:
            check_exiftool()
        except RuntimeError as e:
            console.print(f"[red]{e}[/red]")
            raise typer.Exit(code=1)

    progress, hooks = _build_pipeline_ui(console)

    options = Options(
        source=str(source),
        destination=str(destination) if destination else None,
        mode=mode,
        dry_run=dry_run,
        skip_dedupe=skip_dedupe,
        skip_metadata_write=skip_metadata_write,
        prefer=prefer,
        fuzzy=fuzzy,
        fuzzy_threshold=fuzzy_threshold,
        write_manifest=write_manifest,
    )

    console.print(f"\n[bold]Processing photos from {source}...[/bold]\n")

    manifest = run_pipeline(options, hooks, progress)

    if dry_run:
        console.print(
            f"[yellow]Dry run — {len(manifest)} files processed, no files copied.[/yellow]"
        )
    else:
        console.print("[green bold]Done![/green bold]")


@app.command()
def enrich(
    library: Path = typer.Argument(
        ...,
        help="Path to the working library produced by `pixelkasten init`.",
        exists=True,
        file_okay=False,
        resolve_path=True,
    ),
    with_captions: bool = typer.Option(
        False,
        "--with-captions",
        help="Also run VLM captioning on every asset (opt-in; slow).",
    ),
    video_frames: int = typer.Option(
        5,
        "--video-frames",
        help="Number of frames to sample per video for embeddings and captions.",
    ),
):
    """Bulk geocode + CLIP embed for an existing working library."""
    from pixelkasten.configuration import EnrichOptions
    from pixelkasten.stages.enrich import enrich as run_enrich
    from pixelkasten_cli.reports import build_progress_factory

    options = EnrichOptions(
        library=str(library),
        with_captions=with_captions,
        video_frames=video_frames,
    )

    console.print(f"\n[bold]Enriching {library}...[/bold]\n")
    run_enrich(options, progress=build_progress_factory(console))
    console.print("[green bold]Enrichment done.[/green bold]")


@app.command()
def apply(
    library: Path = typer.Argument(
        ...,
        help="Path to the working library to export.",
        exists=True,
        file_okay=False,
        resolve_path=True,
    ),
    to: Path = typer.Option(
        ...,
        "--to",
        help="Destination directory for the organized photo library.",
        resolve_path=True,
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Overwrite destination if it exists and is non-empty.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Print planned operations without copying.",
    ),
):
    """Export a working library to an organized photo library at --to."""
    from pixelkasten.configuration import ApplyOptions
    from pixelkasten.stages.export import apply_export

    options = ApplyOptions(force=force, dry_run=dry_run)
    summary = apply_export(str(library), str(to), options)
    label = "Would export" if summary["dry_run"] else "Exported"
    typer.echo(
        f"{label} {summary['total']} file(s) to {summary['destination']} "
        f"({summary['unsorted']} unsorted)."
    )


@app.command()
def propose(
    path: Path = typer.Argument(
        ...,
        help="Media file inside a working library. Group siblings update together.",
        exists=True,
        dir_okay=False,
        resolve_path=True,
    ),
    album: str | None = typer.Argument(
        None,
        help="Album name to record on the sidecar. Omit when using --clear.",
    ),
    clear: bool = typer.Option(
        False,
        "--clear",
        help="Remove proposed_album from the file and its group siblings.",
    ),
):
    """Set proposed_album on the file's sidecar and all group siblings."""
    if clear and album is not None:
        console.print("[red]--clear and an album name are mutually exclusive[/red]")
        raise typer.Exit(code=1)
    if not clear and not album:
        console.print("[red]Pass an album name or --clear[/red]")
        raise typer.Exit(code=1)

    from pixelkasten.tools.propose import propose as run_propose

    updated = run_propose(str(path), None if clear else album)
    label = "cleared proposed_album on" if clear else f"set proposed_album={album!r} on"
    typer.echo(f"{label} {len(updated)} file(s)")


@app.command()
def caption(
    path: Path = typer.Argument(
        ...,
        help="Media file to caption; its sidecar must exist in .pixelkasten/.",
        exists=True,
        dir_okay=False,
        resolve_path=True,
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Re-caption even if a caption is already present in the sidecar.",
    ),
    model: str = typer.Option(
        "gemma4:e4b",
        "--model",
        help="Ollama VLM to use.",
    ),
    video_frames: int = typer.Option(
        5,
        "--video-frames",
        help="Frames sampled per video.",
    ),
):
    """Caption one asset; write the caption to its sidecar and echo to stdout."""
    from pixelkasten.tools.caption import caption as run_caption

    result = run_caption(str(path), force=force, model=model, video_frames=video_frames)
    if result is None:
        raise typer.Exit(code=1)
    typer.echo(result)


@app.command()
def cluster(
    paths: list[str] = typer.Argument(
        None,
        help="Paths to cluster. If omitted (or '-'), read newline-separated paths from stdin.",
    ),
    library: Path | None = typer.Option(
        None,
        "--library",
        help="Working library to read embeddings from; auto-detected from the first path.",
        resolve_path=True,
    ),
    min_cluster_size: int = typer.Option(
        5,
        "--min-cluster-size",
        help="HDBSCAN's minimum cluster size (>= 2).",
    ),
):
    """Cluster a set of paths via HDBSCAN; print {label: [path]} as JSON."""
    import sys as _sys
    import json as _json

    from pixelkasten.tools.cluster import cluster as run_cluster
    from pixelkasten.tools.similarity import resolve_library

    resolved = _resolve_cluster_paths(paths)
    if not resolved:
        typer.echo("{}")
        return

    lib = str(library) if library else resolve_library(resolved[0])
    grouped = run_cluster(resolved, lib, min_cluster_size)
    typer.echo(_json.dumps({str(k): v for k, v in grouped.items()}, indent=2))
    _ = _sys  # keep import warning quiet if unused


def _resolve_cluster_paths(args: list[str] | None) -> list[str]:
    """Read paths from args, else from stdin (one per line)."""
    import sys as _sys

    if args and args != ["-"]:
        return args
    if _sys.stdin.isatty():
        return []
    return [line.strip() for line in _sys.stdin if line.strip()]


@app.command()
def similar(
    query: Path = typer.Argument(
        ...,
        help="Image or video to query (in a working library or anywhere on disk).",
        exists=True,
        dir_okay=False,
        resolve_path=True,
    ),
    library: Path | None = typer.Option(
        None,
        "--library",
        help="Working library to search; auto-detected by walking up from QUERY if omitted.",
        resolve_path=True,
    ),
    k: int = typer.Option(20, "--k", help="Number of neighbors to return."),
):
    """Print the K nearest neighbors of QUERY as JSON."""
    import json as _json

    from pixelkasten.tools.similarity import resolve_library, similar as run_similar

    lib = str(library) if library else resolve_library(str(query))
    results = run_similar(str(query), lib, k)
    typer.echo(_json.dumps(results, indent=2))


def _resolve_mode(from_takeout: bool, from_archive: bool, source: Path) -> str:
    """Validate the mutually-exclusive mode flags and return the chosen mode."""
    if from_takeout and from_archive:
        console.print("[red]--from-takeout and --from-archive are mutually exclusive[/red]")
        raise typer.Exit(code=1)
    if from_takeout:
        return "takeout"
    if from_archive:
        return "archive"

    hint = (
        " JSON sidecars detected in source; did you mean --from-takeout?"
        if _detect_takeout_sidecars(source)
        else ""
    )
    console.print(f"[red]Pass exactly one of --from-takeout or --from-archive.{hint}[/red]")
    raise typer.Exit(code=1)


def _detect_takeout_sidecars(source: Path) -> bool:
    """Return True if any .json file exists under source (single-level scan)."""
    try:
        for root, _dirs, files in os.walk(str(source)):
            for name in files:
                if name.endswith(".json"):
                    return True
            # Stop after the first directory level with files for speed.
            if root != str(source):
                break
    except OSError:
        return False
    return False


def _build_pipeline_ui(console):
    """Build progress factory and hooks for pipeline UI reporting."""
    from pixelkasten_cli.reports import (
        build_progress_factory,
        render_apply_table,
        render_dedupe_table,
        render_error_table,
        render_link_table,
        render_reconcile_table,
        render_scan_table,
    )

    progress = build_progress_factory(console)

    from pixelkasten.configuration import Hooks

    hooks = Hooks(
        on_scan=partial(render_scan_table, console),
        on_link=partial(render_link_table, console),
        on_reconcile=partial(render_reconcile_table, console),
        on_dedupe=partial(render_dedupe_table, console),
        on_apply=partial(render_apply_table, console),
        on_errors=partial(render_error_table, console),
    )

    return progress, hooks
