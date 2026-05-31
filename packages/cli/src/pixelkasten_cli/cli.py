"""
CLI entry point — pixelkasten subcommands.

Each command is a thin wrapper: build an options dataclass, call the core
function, hand the return value to ``render_<command>`` in ``render.py``.
No rendering logic lives here; ``render.py`` is the single source for that.

Usage:
    uv run pixelkasten import --from-takeout -s <source> -d <destination>
    uv run pixelkasten import --from-archive -s <source> -d <destination>
"""

import os
import typer
from pathlib import Path
from rich.console import Console

from pixelkasten_cli.render import (
    build_progress_factory,
    render_caption,
    render_check,
    render_cluster,
    render_enrich,
    render_export,
    render_import,
    render_propose,
    render_similar,
)

app = typer.Typer(
    name="pixelkasten",
    help="Photo library organizer.",
    add_completion=False,
    no_args_is_help=True,
)
console = Console()


# Forces typer into multi-command mode. Without a callback, typer collapses
# a single-command app to the top level; even an empty callback keeps the
# subcommand structure intact.
@app.callback()
def _callback() -> None:
    """Photo library organizer."""


# "import" is a Python keyword, so the function can't be named ``import``;
# we wire it under the CLI name explicitly.
@app.command(name="import")
def import_cmd(
    from_takeout: bool = typer.Option(
        False,
        "--from-takeout",
        help="Import a Google Takeout export (matches media files to their JSON sidecars).",
    ),
    from_archive: bool = typer.Option(
        False,
        "--from-archive",
        help="Import media files from a regular folder of photos (no Google Takeout sidecars).",
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
):
    """Import a source into a working library."""
    mode = _resolve_mode(from_takeout, from_archive, source)

    if destination is None and not dry_run:
        console.print("[red]--destination is required (unless --dry-run is set)[/red]")
        raise typer.Exit(code=1)

    from pixelkasten.configuration import IngestOptions
    from pixelkasten.commands.ingest import ingest

    if mode == "takeout" and not skip_metadata_write:
        from pixelkasten.tools.exiftool import check_exiftool

        try:
            check_exiftool()
        except RuntimeError as e:
            console.print(f"[red]{e}[/red]")
            raise typer.Exit(code=1)

    options = IngestOptions(
        source=str(source),
        destination=str(destination) if destination else None,
        mode=mode,
        dry_run=dry_run,
        skip_dedupe=skip_dedupe,
        skip_metadata_write=skip_metadata_write,
        prefer=prefer,
        fuzzy=fuzzy,
        fuzzy_threshold=fuzzy_threshold,
    )

    console.print(f"\n[bold]Processing photos from {source}...[/bold]\n")

    result = ingest(options, progress=build_progress_factory(console))
    render_import(console, result, options)

    if dry_run:
        console.print(
            f"[yellow]Dry run — {len(result.manifest)} files processed, no files copied.[/yellow]"
        )
    else:
        console.print("[green bold]Done![/green bold]")


@app.command()
def enrich(
    library: Path = typer.Argument(
        ...,
        help="Path to the working library produced by `pixelkasten import`.",
        exists=True,
        file_okay=False,
        resolve_path=True,
    ),
    video_frames: int = typer.Option(
        5,
        "--video-frames",
        help="Number of frames to sample per video for embeddings and captions.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Compute geocoding and embeddings but do not write to disk.",
    ),
):
    """Bulk geocode + CLIP embed for an existing working library."""
    from pixelkasten.configuration import EnrichOptions
    from pixelkasten.commands.enrich import enrich as run_enrich

    options = EnrichOptions(library=str(library), video_frames=video_frames, dry_run=dry_run)

    console.print(f"\n[bold]Enriching {library}...[/bold]\n")
    summary = run_enrich(options, progress=build_progress_factory(console))
    render_enrich(console, summary)
    console.print("[green bold]Enrichment done.[/green bold]")


@app.command()
def export(
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
    from pixelkasten.configuration import ExportOptions
    from pixelkasten.commands.export import export as run_export

    options = ExportOptions(force=force, dry_run=dry_run)
    result = run_export(str(library), str(to), options)
    render_export(console, result, options)


@app.command()
def check(
    library: Path = typer.Argument(
        ...,
        help="Working library to inspect for proposed_album conflicts before export.",
        exists=True,
        file_okay=False,
        resolve_path=True,
    ),
):
    """Report proposed_album conflicts + invalid album names as JSON; exit 1 if any."""
    from pixelkasten.commands.check import check as run_check

    report = run_check(str(library))
    render_check(console, report)

    if not report["ok"]:
        raise typer.Exit(code=1)


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
        help="Album name to record. Omit when using --clear.",
    ),
    clear: bool = typer.Option(
        False,
        "--clear",
        help="Remove proposed_album from the file and its group siblings.",
    ),
):
    """Set proposed_album on the file's record and all group siblings."""
    if clear and album is not None:
        console.print("[red]--clear and an album name are mutually exclusive[/red]")
        raise typer.Exit(code=1)
    if not clear and not album:
        console.print("[red]Pass an album name or --clear[/red]")
        raise typer.Exit(code=1)

    from pixelkasten.commands.propose import propose as run_propose

    chosen_album = None if clear else album
    updated = run_propose(str(path), chosen_album)
    render_propose(console, updated, chosen_album)


@app.command()
def caption(
    path: Path = typer.Argument(
        ...,
        help="Media file to caption; its record must exist in .pixelkasten/.",
        exists=True,
        dir_okay=False,
        resolve_path=True,
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Re-caption even if a caption is already present in the record.",
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
    """Caption one asset; write the caption to its record and echo to stdout."""
    from pixelkasten.commands.caption import caption as run_caption

    text = run_caption(str(path), force=force, model=model, video_frames=video_frames)
    render_caption(console, text)
    if text is None:
        raise typer.Exit(code=1)


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
    from pixelkasten.commands.cluster import cluster as run_cluster
    from pixelkasten.stores.record import records_dir_home

    resolved = _resolve_cluster_paths(paths)
    if not resolved:
        render_cluster(console, {})
        return

    lib = str(library) if library else records_dir_home(resolved[0])
    grouped = run_cluster(resolved, lib, min_cluster_size)
    render_cluster(console, grouped)


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
        help="Image or video to query — must be inside the working library.",
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
    from pixelkasten.commands.similar import similar as run_similar
    from pixelkasten.stores.record import records_dir_home

    lib = str(library) if library else records_dir_home(str(query))
    results = run_similar(str(query), lib, k)
    render_similar(console, results)


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
