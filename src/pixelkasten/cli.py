"""
CLI entry point — orchestrates the AI pipeline phases.

Usage:
    uv run pixelkasten embed -s ~/photos -o ./output
    uv run pixelkasten caption -m ./output/manifest.json --model llava
    uv run pixelkasten enrich -m ./output/manifest.json
    uv run pixelkasten organize -m ./output/manifest.json

Phase 1  (embed):    scan → embed → cluster → classify → write manifest
Phase 2a (enrich):   read manifest → EXIF from all images → enrich manifest
Phase 2b (refine):   split/merge clusters using EXIF + embeddings → update manifest
Phase 3  (caption):  caption cluster representatives via VLM → enrich manifest
Phase 4  (organize): build cluster summaries → LLM reasoning → organization proposal
Phase 5  (apply):    read organization.json → copy files to proposed structure
"""

import typer
from pathlib import Path
from rich.console import Console
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TaskProgressColumn,
)
from rich.table import Table
from rich.tree import Tree

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

    manifest = run_pipeline(options)

    # Summary
    n_total = len(manifest)
    if dry_run:
        console.print(
            f"\n[yellow]Dry run — {n_total} files processed, no files copied.[/yellow]"
        )
    else:
        n_embedded = sum(
            1 for e in manifest if e.get("apply", {}).get("status") == "embedded"
        )
        n_copied = sum(
            1 for e in manifest if e.get("apply", {}).get("status") == "copied"
        )
        n_errors = sum(
            1 for e in manifest if e.get("apply", {}).get("status") == "error"
        )
        n_deleted = sum(
            1 for e in manifest if e.get("dedupe", {}).get("status") == "delete"
        )

        console.print("\n[green bold]Done![/green bold]")
        console.print(f"  Total files: {n_total}")
        if not skip_dedupe:
            console.print(f"  Deduplicated: {n_deleted}")
        console.print(f"  Embedded metadata: {n_embedded}")
        console.print(f"  Copied (no changes): {n_copied}")
        if n_errors > 0:
            console.print(f"  [red]Errors: {n_errors}[/red]")


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


@app.command()
def embed(
    source: Path = typer.Option(
        ...,
        "--source",
        "-s",
        help="Directory containing photos to categorize.",
        exists=True,
        file_okay=False,
        resolve_path=True,
    ),
    output: Path = typer.Option(
        Path("./output"),
        "--output",
        "-o",
        help="Directory to write manifest.json and embeddings.npy.",
        resolve_path=True,
    ),
    model_name: str = typer.Option(
        "ViT-L-14",
        "--model",
        help="CLIP model architecture. ViT-L-14 is recommended. ViT-B-32 is faster but less accurate.",
    ),
    min_cluster_size: int = typer.Option(
        5,
        "--min-cluster-size",
        help="Minimum images to form a cluster. Larger values = fewer, bigger clusters.",
    ),
    batch_size: int = typer.Option(
        32,
        "--batch-size",
        help="Images per batch during embedding. Lower this if you run out of memory.",
    ),
    threshold: float = typer.Option(
        0.15,
        "--threshold",
        help="Minimum cosine similarity for a tag to be included. CLIP scores are typically low (0.15-0.35).",
    ),
):
    """
    Run the Phase 1 pipeline: scan, embed, cluster, classify, write manifest.
    """
    from pixelkasten.stages.scan import scan, is_image
    from pixelkasten.stages.embed import load_model, embed_images, embed_texts
    from pixelkasten.stages.cluster import (
        cluster_embeddings,
        find_representatives,
        cluster_summary,
    )
    from pixelkasten.stages.classify import (
        classify,
        build_label_list,
        DEFAULT_LABEL_SETS,
    )
    from pixelkasten.core.manifest import write_manifest

    # --- Step 1: Scan for images ---
    console.print("\n[bold]Step 1/5:[/bold] Scanning for images...")
    all_files = scan(source)
    image_files = [f for f in all_files if is_image(f)]

    if len(image_files) == 0:
        console.print("[red]No supported images found in source directory.[/red]")
        raise typer.Exit(code=1)

    console.print(
        f"  Found {len(image_files)} images ({len(all_files) - len(image_files)} videos skipped)"
    )

    # --- Step 2: Load CLIP model ---
    console.print("\n[bold]Step 2/5:[/bold] Loading CLIP model...")

    with console.status(f"Downloading/loading {model_name}..."):
        model, preprocess, tokenizer, device = load_model(model_name=model_name)

    console.print(f"  Model: {model_name} on {device}")

    # --- Step 3: Generate embeddings ---
    console.print(f"\n[bold]Step 3/5:[/bold] Embedding {len(image_files)} images...")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Embedding images", total=len(image_files))

        def on_progress(processed):
            progress.update(task, completed=processed)

        embeddings, failed_indices = embed_images(
            model,
            preprocess,
            image_files,
            device,
            batch_size=batch_size,
            on_progress=on_progress,
        )

    n_embedded = len(image_files) - len(failed_indices)
    console.print(f"  Embedded: {n_embedded} images")
    if failed_indices:
        console.print(
            f"  [yellow]Failed: {len(failed_indices)} images (corrupt or unreadable)[/yellow]"
        )

    if n_embedded == 0:
        console.print("[red]No images could be embedded. Check file formats.[/red]")
        raise typer.Exit(code=1)

    # --- Step 4: Cluster ---
    console.print("\n[bold]Step 4/5:[/bold] Clustering embeddings...")

    labels = cluster_embeddings(embeddings, min_cluster_size=min_cluster_size)
    summary = cluster_summary(labels)
    representatives = find_representatives(embeddings, labels)

    console.print(f"  Clusters: {summary['n_clusters']}")
    console.print(f"  Noise (unclustered): {summary['n_noise']} images")

    # Print cluster sizes as a compact table.
    if summary["cluster_sizes"]:
        table = Table(title="Cluster Sizes", show_header=True)
        table.add_column("Cluster", style="cyan", justify="right")
        table.add_column("Images", justify="right")
        table.add_column("Representatives", justify="right")

        for cluster_id in sorted(summary["cluster_sizes"]):
            n_reps = len(representatives.get(cluster_id, []))
            table.add_row(
                str(cluster_id),
                str(summary["cluster_sizes"][cluster_id]),
                str(n_reps),
            )

        console.print(table)

    # --- Step 5: Classify ---
    console.print("\n[bold]Step 5/5:[/bold] Classifying images against labels...")

    prefixed_names, raw_labels = build_label_list(DEFAULT_LABEL_SETS)

    with console.status("Embedding label texts..."):
        label_embeddings = embed_texts(model, tokenizer, raw_labels, device)

    classifications = classify(
        embeddings, label_embeddings, prefixed_names, threshold=threshold
    )

    # --- Write manifest ---
    manifest_path = write_manifest(
        output_dir=output,
        image_paths=image_files,
        embeddings=embeddings,
        labels=labels,
        classifications=classifications,
        representatives=representatives,
        failed_indices=failed_indices,
    )

    console.print(
        f"\n[green bold]Done![/green bold] Manifest written to {manifest_path}"
    )
    console.print(f"  Embeddings saved to {output / 'embeddings.npy'}")


@app.command()
def caption(
    manifest_path: Path = typer.Option(
        ...,
        "--manifest",
        "-m",
        help="Path to a Phase 1 manifest.json file.",
        exists=True,
        dir_okay=False,
        resolve_path=True,
    ),
    model: str = typer.Option(
        "llava",
        "--model",
        help="Ollama vision model to use. LLaVA is recommended for image understanding.",
    ),
    prompt: str = typer.Option(
        None,
        "--prompt",
        help="Custom captioning prompt. Defaults to a general-purpose description prompt.",
    ),
):
    """
    Caption cluster representatives via a local VLM.

    Requires Ollama running locally with a vision model pulled.
    Reads the manifest, captions representative images, and writes
    enriched results (captions + cluster summaries) back to the manifest.
    """
    from pixelkasten.core.manifest import read_manifest, enrich_manifest
    from pixelkasten.stages.caption import (
        check_ollama,
        caption_representatives,
        DEFAULT_PROMPT,
    )

    # --- Step 1: Validate prerequisites ---
    console.print("\n[bold]Step 1/3:[/bold] Checking Ollama...")

    try:
        check_ollama(model)
    except RuntimeError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=1)

    console.print(f"  Model: {model}")

    # --- Step 2: Caption representatives ---
    manifest = read_manifest(manifest_path)

    n_representatives = sum(
        1
        for e in manifest["entries"]
        if e.get("is_representative", False) and e.get("status") == "ok"
    )

    if n_representatives == 0:
        console.print("[red]No representative images found in manifest.[/red]")
        raise typer.Exit(code=1)

    console.print(
        f"\n[bold]Step 2/3:[/bold] Captioning {n_representatives} representatives..."
    )

    captioning_prompt = prompt if prompt is not None else DEFAULT_PROMPT

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Captioning images", total=n_representatives)

        def on_progress(processed):
            progress.update(task, completed=processed)

        captions = caption_representatives(
            manifest,
            model,
            captioning_prompt,
            on_progress=on_progress,
        )

    console.print(f"  Captioned: {len(captions)} / {n_representatives} images")

    if len(captions) == 0:
        console.print("[red]No images could be captioned. Check Ollama logs.[/red]")
        raise typer.Exit(code=1)

    # --- Step 3: Enrich manifest ---
    console.print("\n[bold]Step 3/3:[/bold] Writing enriched manifest...")

    enrich_manifest(manifest_path, captions)

    console.print(
        f"\n[green bold]Done![/green bold] Manifest enriched: {manifest_path}"
    )

    # Print a sample of captions.
    table = Table(title="Sample Captions", show_header=True)
    table.add_column("Image", style="cyan", max_width=50)
    table.add_column("Caption", max_width=80)

    for path, cap in list(captions.items())[:5]:
        table.add_row(Path(path).name, cap)

    console.print(table)


@app.command()
def enrich(
    manifest_path: Path = typer.Option(
        ...,
        "--manifest",
        "-m",
        help="Path to a manifest.json file.",
        exists=True,
        dir_okay=False,
        resolve_path=True,
    ),
):
    """
    Read EXIF metadata from all images via exiftool and enrich the manifest.

    Reads timestamps, GPS coordinates, and camera model from all images
    and enriches the manifest with per-entry EXIF data and per-cluster
    date ranges, locations, and cameras.

    Requires exiftool installed (brew install exiftool).
    """
    from pixelkasten.core.exif import check_exiftool, read_exif_for_all
    from pixelkasten.core.manifest import read_manifest, enrich_manifest_exif

    # --- Step 1: Check exiftool ---
    console.print("\n[bold]Step 1/4:[/bold] Checking exiftool...")

    try:
        check_exiftool()
    except RuntimeError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=1)

    console.print("  exiftool found")

    # --- Step 2: Read EXIF from all images ---
    manifest = read_manifest(manifest_path)

    n_images = sum(1 for e in manifest["entries"] if e.get("status") == "ok")

    if n_images == 0:
        console.print("[red]No images found in manifest.[/red]")
        raise typer.Exit(code=1)

    console.print(f"\n[bold]Step 2/4:[/bold] Reading EXIF from {n_images} images...")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Reading EXIF", total=n_images)

        def on_progress(processed):
            progress.update(task, completed=processed)

        exif_data = read_exif_for_all(manifest, on_progress=on_progress)

    n_with_timestamp = sum(1 for e in exif_data.values() if e.get("timestamp"))
    n_with_gps = sum(1 for e in exif_data.values() if e.get("gps"))
    console.print(f"  With timestamp: {n_with_timestamp} / {len(exif_data)}")
    console.print(f"  With GPS: {n_with_gps} / {len(exif_data)}")

    # --- Step 3: Reverse geocode GPS coordinates ---
    from pixelkasten.core.exif import reverse_geocode

    location_data = {}
    if n_with_gps > 0:
        console.print(
            f"\n[bold]Step 3/4:[/bold] Reverse geocoding {n_with_gps} GPS coordinates..."
        )

        with console.status("Resolving locations..."):
            location_data = reverse_geocode(exif_data)

        unique_locations = set(loc["display_name"] for loc in location_data.values())
        console.print(f"  Resolved to {len(unique_locations)} unique locations")
    else:
        console.print("\n[bold]Step 3/4:[/bold] No GPS data to geocode")

    # --- Step 4: Enrich manifest ---
    console.print("\n[bold]Step 4/4:[/bold] Writing enriched manifest...")

    enrich_manifest_exif(manifest_path, exif_data, location_data=location_data)

    console.print(
        f"\n[green bold]Done![/green bold] Manifest enriched: {manifest_path}"
    )

    # Print a sample of EXIF results.
    table = Table(title="Sample EXIF Data", show_header=True)
    table.add_column("Image", style="cyan", max_width=35)
    table.add_column("Timestamp", max_width=22)
    table.add_column("Location", max_width=30)
    table.add_column("Camera", max_width=18)

    for path, exif in list(exif_data.items())[:5]:
        loc_info = location_data.get(path)
        loc_str = loc_info["display_name"] if loc_info else ""
        if not loc_str and exif.get("gps"):
            loc_str = f"{exif['gps']['latitude']}, {exif['gps']['longitude']}"
        table.add_row(
            Path(path).name,
            exif.get("timestamp") or "-",
            loc_str or "-",
            str(exif.get("camera") or "-"),
        )

    console.print(table)


@app.command()
def refine(
    manifest_path: Path = typer.Option(
        ...,
        "--manifest",
        "-m",
        help="Path to a manifest.json file (must have EXIF data from enrich step).",
        exists=True,
        dir_okay=False,
        resolve_path=True,
    ),
    split_gap: float = typer.Option(
        48.0,
        "--split-gap",
        help="Hours gap between photos to trigger a cluster split.",
    ),
    merge_similarity: float = typer.Option(
        0.5,
        "--merge-similarity",
        help="Minimum centroid cosine similarity to merge clusters.",
    ),
    merge_time: float = typer.Option(
        168.0,
        "--merge-time",
        help="Maximum hours apart for clusters to be merge candidates. Default is 7 days.",
    ),
):
    """
    Refine clusters using EXIF timestamps and embedding similarity.

    Splits clusters that span different time periods (e.g., beach photos
    from 2017 and 2023 grouped together) and merges clusters that are
    from the same day and visually similar (e.g., indoor and outdoor shots
    from the same go-karting event).

    Requires the enrich step to have been run first (EXIF data in manifest).
    """
    from pixelkasten.core.manifest import (
        read_manifest,
        load_embeddings,
        update_manifest_clusters,
    )
    from pixelkasten.stages.cluster import find_representatives, cluster_summary
    from pixelkasten.stages.refine import refine_clusters

    # --- Step 1: Load data ---
    console.print("\n[bold]Step 1/3:[/bold] Loading manifest and embeddings...")

    manifest = read_manifest(manifest_path)
    embeddings = load_embeddings(manifest_path)

    # Check that EXIF data exists.
    has_exif = any(entry.get("exif") for entry in manifest["entries"])
    if not has_exif:
        console.print("[red]No EXIF data found in manifest. Run 'enrich' first.[/red]")
        raise typer.Exit(code=1)

    import numpy as np

    before = cluster_summary(
        np.array(
            [
                e.get("cluster", -1)
                for e in manifest["entries"]
                if e.get("status") == "ok"
            ]
        )
    )
    console.print(f"  Clusters before: {before['n_clusters']}")
    console.print(f"  Noise before: {before['n_noise']} images")

    # --- Step 2: Refine ---
    console.print("\n[bold]Step 2/3:[/bold] Refining clusters...")

    new_labels, stats = refine_clusters(
        manifest,
        embeddings,
        split_gap_hours=split_gap,
        merge_similarity=merge_similarity,
        merge_time_hours=merge_time,
    )

    console.print(f"  Ejected (no EXIF): {stats['ejected']}")
    console.print(f"  Splits performed: {stats['splits']}")
    console.print(f"  Merges performed: {stats['merges']}")
    console.print(f"  Absorbed (by location): {stats['absorbed_by_location']}")
    console.print(f"  Absorbed (by similarity): {stats['absorbed_by_similarity']}")
    if stats.get("home_location"):
        console.print(f"  Home location: {stats['home_location']}")

    # --- Step 3: Update manifest ---
    console.print("\n[bold]Step 3/3:[/bold] Updating manifest...")

    representatives = find_representatives(embeddings, new_labels)
    update_manifest_clusters(manifest_path, new_labels, representatives)

    after = cluster_summary(new_labels)
    console.print(f"\n[green bold]Done![/green bold] Manifest updated: {manifest_path}")
    console.print(f"  Clusters after: {after['n_clusters']}")
    console.print(f"  Noise after: {after['n_noise']} images")

    # Show before/after comparison.
    if before["n_clusters"] != after["n_clusters"]:
        delta = after["n_clusters"] - before["n_clusters"]
        sign = "+" if delta > 0 else ""
        console.print(
            f"  Change: {sign}{delta} clusters ({before['n_clusters']} → {after['n_clusters']})"
        )

    # Print cluster sizes.
    if after["cluster_sizes"]:
        table = Table(title="Refined Cluster Sizes", show_header=True)
        table.add_column("Cluster", style="cyan", justify="right")
        table.add_column("Images", justify="right")
        table.add_column("Representatives", justify="right")

        for cluster_id in sorted(after["cluster_sizes"]):
            n_reps = len(representatives.get(cluster_id, []))
            table.add_row(
                str(cluster_id),
                str(after["cluster_sizes"][cluster_id]),
                str(n_reps),
            )

        console.print(table)


@app.command()
def organize(
    manifest_path: Path = typer.Option(
        ...,
        "--manifest",
        "-m",
        help="Path to an enriched manifest.json file.",
        exists=True,
        dir_okay=False,
        resolve_path=True,
    ),
    output: Path = typer.Option(
        None,
        "--output",
        "-o",
        help="Path to write organization.json. Defaults to same directory as manifest.",
        resolve_path=True,
    ),
    model: str = typer.Option(
        "qwen3.5:35b",
        "--model",
        help="Ollama text model for organization reasoning.",
    ),
):
    """
    Propose a directory structure using a local LLM.

    Reads the enriched manifest (with captions + EXIF), feeds cluster
    summaries to the LLM, and writes an organization.json proposal.

    This is propose-only — no files are moved. Review organization.json
    before applying.

    Requires Ollama running locally with a text model pulled.
    """
    from pixelkasten.stages.caption import check_ollama
    from pixelkasten.core.manifest import read_manifest
    from pixelkasten.stages.organize import (
        propose_organization,
        build_organization_plan,
        write_organization_plan,
    )

    # --- Step 1: Check Ollama ---
    console.print("\n[bold]Step 1/5:[/bold] Checking Ollama...")

    try:
        check_ollama(model)
    except RuntimeError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=1)

    console.print(f"  Model: {model}")

    # --- Step 2: Build cluster summaries ---
    console.print("\n[bold]Step 2/5:[/bold] Reading manifest...")

    manifest = read_manifest(manifest_path)
    clusters = manifest.get("clusters", {})

    if not clusters:
        console.print("[red]No clusters found in manifest. Run embed first.[/red]")
        raise typer.Exit(code=1)

    # Warn if no EXIF data is present.
    has_exif = any(entry.get("exif") for entry in manifest["entries"])
    if not has_exif:
        console.print(
            "[yellow]  No EXIF data found in manifest. "
            "Run 'enrich' first for better date-based organization.[/yellow]"
        )

    console.print(f"  Clusters: {len(clusters)}")

    # Print cluster preview table.
    table = Table(title="Cluster Summary", show_header=True)
    table.add_column("Cluster", style="cyan", justify="right")
    table.add_column("Size", justify="right")
    table.add_column("Date Range", max_width=25)
    table.add_column("Captions", max_width=50)

    for cid in sorted(clusters.keys(), key=lambda x: int(x)):
        c = clusters[cid]
        date_range = ""
        if c.get("date_range"):
            date_range = f"{c['date_range']['earliest'][:10]} to {c['date_range']['latest'][:10]}"
        cap_preview = "; ".join(c.get("captions", []))[:50]
        table.add_row(cid, str(c.get("size", 0)), date_range or "-", cap_preview or "-")

    console.print(table)

    # --- Step 3: LLM reasoning ---
    console.print(
        "\n[bold]Step 3/5:[/bold] Sending to LLM for organization proposal..."
    )

    with console.status("LLM is reasoning about directory structure..."):
        try:
            cluster_directories = propose_organization(manifest, model)
        except ValueError as e:
            console.print(f"[red]{e}[/red]")
            raise typer.Exit(code=1)

    console.print(f"  Proposed directories for {len(cluster_directories)} clusters")

    # --- Step 4: Read EXIF for noise images ---
    # Noise images (cluster=-1) weren't enriched by the enrich step (which
    # only processes representatives). Read their EXIF now so we can place
    # them in date-based directories instead of Unsorted/.
    noise_entries = [
        e
        for e in manifest["entries"]
        if e.get("status") == "ok"
        and (
            e.get("cluster") is None
            or e.get("cluster") == -1
            or str(e.get("cluster")) not in cluster_directories
        )
        and not e.get("exif", {}).get("timestamp")
    ]

    noise_exif = {}
    if noise_entries:
        from pixelkasten.core.exif import read_exif

        noise_paths = [Path(e["path"]) for e in noise_entries]
        console.print(
            f"\n[bold]Step 4/5:[/bold] Reading EXIF for {len(noise_paths)} unclustered images..."
        )

        with console.status("Reading EXIF..."):
            noise_exif = read_exif(noise_paths)

        n_with_date = sum(1 for e in noise_exif.values() if e.get("timestamp"))
        console.print(
            f"  {n_with_date} of {len(noise_paths)} have timestamps (will be placed by date)"
        )
    else:
        console.print(
            "\n[bold]Step 4/5:[/bold] No unclustered images need EXIF reading"
        )

    # --- Step 5: Write plan ---
    console.print("\n[bold]Step 5/5:[/bold] Writing organization plan...")

    plan = build_organization_plan(manifest, cluster_directories, noise_exif=noise_exif)

    output_path = (
        output if output is not None else manifest_path.parent / "organization.json"
    )
    write_organization_plan(plan, cluster_directories, model, output_path)

    n_organized = sum(1 for p in plan if not p["target"].startswith("Unsorted/"))
    n_unsorted = sum(1 for p in plan if p["target"].startswith("Unsorted/"))

    console.print(
        f"\n[green bold]Done![/green bold] Organization plan written to {output_path}"
    )
    console.print(f"  Organized: {n_organized} images")
    console.print(f"  Unsorted: {n_unsorted} images")

    # Print proposed directory tree.
    tree = Tree("[bold]Proposed Organization[/bold]")
    dir_counts: dict[str, int] = {}
    for p in plan:
        target_dir = str(Path(p["target"]).parent)
        dir_counts[target_dir] = dir_counts.get(target_dir, 0) + 1

    for dir_path in sorted(dir_counts.keys()):
        count = dir_counts[dir_path]
        tree.add(f"{dir_path}/ ({count} images)")

    console.print(tree)


@app.command()
def apply(
    plan_path: Path = typer.Option(
        ...,
        "--plan",
        "-p",
        help="Path to an organization.json file.",
        exists=True,
        dir_okay=False,
        resolve_path=True,
    ),
    destination: Path = typer.Option(
        ...,
        "--destination",
        "-d",
        help="Root directory to copy files into.",
        resolve_path=True,
    ),
):
    """
    Apply an organization plan by copying files to the proposed structure.

    Reads organization.json and copies each file to destination/target.
    Originals are not modified — this is a copy, not a move.
    """
    import json as json_mod
    from pixelkasten.stages.organize import apply_organization_plan

    # Read plan to get total count.
    with open(plan_path) as f:
        organization = json_mod.load(f)

    total = len(organization["plan"])

    if total == 0:
        console.print("[red]Organization plan is empty.[/red]")
        raise typer.Exit(code=1)

    console.print(f"\n[bold]Copying {total} files to {destination}...[/bold]")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Copying files", total=total)

        def on_progress(processed):
            progress.update(task, completed=processed)

        stats = apply_organization_plan(plan_path, destination, on_progress=on_progress)

    console.print(f"\n[green bold]Done![/green bold] Files copied to {destination}")
    console.print(f"  Copied: {stats['copied']}")
    if stats["skipped"] > 0:
        console.print(
            f"  [yellow]Skipped (source missing): {stats['skipped']}[/yellow]"
        )
    if stats["failed"] > 0:
        console.print(f"  [red]Failed: {stats['failed']}[/red]")


@app.command()
def takeout(
    source: Path = typer.Option(
        ...,
        "--source",
        "-s",
        help="Directory containing a Google Photos Takeout export.",
        exists=True,
        file_okay=False,
        resolve_path=True,
    ),
    destination: Path = typer.Option(
        ...,
        "--destination",
        "-d",
        help="Directory to copy organized files into.",
        resolve_path=True,
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Preview without copying files.",
    ),
    prefer: str = typer.Option(
        "album",
        "--prefer",
        help="When deduplicating, prefer 'album' or 'loose' copies.",
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
    skip_rename: bool = typer.Option(
        False,
        "--skip-rename",
        help="Skip renaming files by timestamp.",
    ),
    no_fuzzy: bool = typer.Option(
        False,
        "--no-fuzzy",
        help="Disable fuzzy matching for sidecar linking.",
    ),
):
    """
    Process a Google Photos Takeout export.

    Scans the source directory, matches media to JSON sidecars, deduplicates,
    embeds metadata, renames by timestamp, and copies to destination.
    """
    from pixelkasten.core.exiftool import check_exiftool
    from pixelkasten.pipeline import run_takeout_pipeline

    # Check exiftool is available
    if not skip_embed:
        try:
            check_exiftool()
        except RuntimeError as e:
            console.print(f"[red]{e}[/red]")
            raise typer.Exit(code=1)

    options = {
        "source": str(source),
        "destination": str(destination),
        "dry_run": dry_run,
        "prefer": prefer,
        "skip_dedupe": skip_dedupe,
        "skip_embed": skip_embed,
        "skip_rename": skip_rename,
        "fuzzy": not no_fuzzy,
        "fuzzy_threshold": 40,
    }

    console.print(f"\n[bold]Processing Takeout export from {source}...[/bold]")

    manifest = run_takeout_pipeline(options)

    # Summary
    n_total = len(manifest)
    n_matched = sum(1 for e in manifest if e.get("json"))
    n_unmatched = n_total - n_matched

    if dry_run:
        console.print("\n[yellow]Dry run — no files were copied.[/yellow]")
    else:
        n_embedded = sum(
            1 for e in manifest if e.get("apply", {}).get("status") == "embedded"
        )
        n_copied = sum(
            1 for e in manifest if e.get("apply", {}).get("status") == "copied"
        )
        n_errors = sum(
            1 for e in manifest if e.get("apply", {}).get("status") == "error"
        )
        n_deleted = sum(
            1 for e in manifest if e.get("dedupe", {}).get("status") == "delete"
        )

        console.print("\n[green bold]Done![/green bold]")
        console.print(f"  Total files: {n_total}")
        console.print(f"  Matched to sidecar: {n_matched}")
        console.print(f"  Unmatched: {n_unmatched}")
        if not skip_dedupe:
            console.print(f"  Deduplicated: {n_deleted}")
        console.print(f"  Embedded metadata: {n_embedded}")
        console.print(f"  Copied (no changes): {n_copied}")
        if n_errors > 0:
            console.print(f"  [red]Errors: {n_errors}[/red]")
