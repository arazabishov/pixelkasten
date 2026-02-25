"""
CLI entry point — orchestrates the AI pipeline phases.

Usage:
    uv run pixelkasten-ai embed -s ~/photos -o ./output
    uv run pixelkasten-ai caption -m ./output/manifest.json --model llava
    uv run pixelkasten-ai enrich -m ./output/manifest.json
    uv run pixelkasten-ai organize -m ./output/manifest.json

Phase 1 (embed):    scan → embed → cluster → classify → write manifest
Phase 2 (caption):  read manifest → caption representatives via VLM → enrich manifest
Phase 3a (enrich):  read manifest → EXIF from representatives → enrich manifest
Phase 3b (organize): read manifest → LLM reasoning → organization proposal
"""

import typer
from pathlib import Path
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table
from rich.tree import Tree

app = typer.Typer(
    name="pixelkasten-ai",
    help="AI-powered photo categorization using CLIP embeddings and VLM captioning.",
    add_completion=False,
)
console = Console()


@app.command()
def embed(
    source: Path = typer.Option(
        ...,
        "--source", "-s",
        help="Directory containing photos to categorize.",
        exists=True,
        file_okay=False,
        resolve_path=True,
    ),
    output: Path = typer.Option(
        Path("./output"),
        "--output", "-o",
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
    from pixelkasten_ai.scan import scan, is_image
    from pixelkasten_ai.embed import load_model, embed_images, embed_texts
    from pixelkasten_ai.cluster import cluster_embeddings, find_representatives, cluster_summary
    from pixelkasten_ai.classify import classify, build_label_list, DEFAULT_LABEL_SETS
    from pixelkasten_ai.manifest import write_manifest

    # --- Step 1: Scan for images ---
    console.print("\n[bold]Step 1/5:[/bold] Scanning for images...")
    all_files = scan(source)
    image_files = [f for f in all_files if is_image(f)]

    if len(image_files) == 0:
        console.print("[red]No supported images found in source directory.[/red]")
        raise typer.Exit(code=1)

    console.print(f"  Found {len(image_files)} images ({len(all_files) - len(image_files)} videos skipped)")

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
            model, preprocess, image_files, device,
            batch_size=batch_size, on_progress=on_progress,
        )

    n_embedded = len(image_files) - len(failed_indices)
    console.print(f"  Embedded: {n_embedded} images")
    if failed_indices:
        console.print(f"  [yellow]Failed: {len(failed_indices)} images (corrupt or unreadable)[/yellow]")

    if n_embedded == 0:
        console.print("[red]No images could be embedded. Check file formats.[/red]")
        raise typer.Exit(code=1)

    # --- Step 4: Cluster ---
    console.print(f"\n[bold]Step 4/5:[/bold] Clustering embeddings...")

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
    console.print(f"\n[bold]Step 5/5:[/bold] Classifying images against labels...")

    prefixed_names, raw_labels = build_label_list(DEFAULT_LABEL_SETS)

    with console.status("Embedding label texts..."):
        label_embeddings = embed_texts(model, tokenizer, raw_labels, device)

    classifications = classify(embeddings, label_embeddings, prefixed_names, threshold=threshold)

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

    console.print(f"\n[green bold]Done![/green bold] Manifest written to {manifest_path}")
    console.print(f"  Embeddings saved to {output / 'embeddings.npy'}")


@app.command()
def caption(
    manifest_path: Path = typer.Option(
        ...,
        "--manifest", "-m",
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
    Run the Phase 2 pipeline: caption cluster representatives via a local VLM.

    Requires Ollama running locally with a vision model pulled.
    Reads a Phase 1 manifest, captions representative images, and writes
    enriched results (captions + cluster summaries) back to the manifest.
    """
    from pixelkasten_ai.manifest import read_manifest, enrich_manifest
    from pixelkasten_ai.caption import (
        check_ollama, caption_representatives, DEFAULT_PROMPT,
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
        1 for e in manifest["entries"]
        if e.get("is_representative", False) and e.get("status") == "ok"
    )

    if n_representatives == 0:
        console.print("[red]No representative images found in manifest.[/red]")
        raise typer.Exit(code=1)

    console.print(f"\n[bold]Step 2/3:[/bold] Captioning {n_representatives} representatives...")

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
            manifest, model, captioning_prompt, on_progress=on_progress,
        )

    console.print(f"  Captioned: {len(captions)} / {n_representatives} images")

    if len(captions) == 0:
        console.print("[red]No images could be captioned. Check Ollama logs.[/red]")
        raise typer.Exit(code=1)

    # --- Step 3: Enrich manifest ---
    console.print(f"\n[bold]Step 3/3:[/bold] Writing enriched manifest...")

    enrich_manifest(manifest_path, captions)

    console.print(f"\n[green bold]Done![/green bold] Manifest enriched: {manifest_path}")

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
        "--manifest", "-m",
        help="Path to a manifest.json file.",
        exists=True,
        dir_okay=False,
        resolve_path=True,
    ),
):
    """
    Run Phase 3a: read EXIF metadata from representative images via exiftool.

    Reads timestamps, GPS coordinates, and camera model from cluster
    representatives and enriches the manifest with date ranges and
    locations per cluster.

    Requires exiftool installed (brew install exiftool).
    """
    from pixelkasten_ai.exif import check_exiftool, read_exif_for_representatives
    from pixelkasten_ai.manifest import read_manifest, enrich_manifest_exif

    # --- Step 1: Check exiftool ---
    console.print("\n[bold]Step 1/3:[/bold] Checking exiftool...")

    try:
        check_exiftool()
    except RuntimeError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=1)

    console.print("  exiftool found")

    # --- Step 2: Read EXIF from representatives ---
    manifest = read_manifest(manifest_path)

    n_representatives = sum(
        1 for e in manifest["entries"]
        if e.get("is_representative", False) and e.get("status") == "ok"
    )

    if n_representatives == 0:
        console.print("[red]No representative images found in manifest.[/red]")
        raise typer.Exit(code=1)

    console.print(f"\n[bold]Step 2/3:[/bold] Reading EXIF from {n_representatives} representatives...")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Reading EXIF", total=n_representatives)

        def on_progress(processed):
            progress.update(task, completed=processed)

        exif_data = read_exif_for_representatives(manifest, on_progress=on_progress)

    n_with_timestamp = sum(1 for e in exif_data.values() if e.get("timestamp"))
    n_with_gps = sum(1 for e in exif_data.values() if e.get("gps"))
    console.print(f"  With timestamp: {n_with_timestamp} / {len(exif_data)}")
    console.print(f"  With GPS: {n_with_gps} / {len(exif_data)}")

    # --- Step 3: Enrich manifest ---
    console.print(f"\n[bold]Step 3/3:[/bold] Writing enriched manifest...")

    enrich_manifest_exif(manifest_path, exif_data)

    console.print(f"\n[green bold]Done![/green bold] Manifest enriched: {manifest_path}")

    # Print a sample of EXIF results.
    table = Table(title="Sample EXIF Data", show_header=True)
    table.add_column("Image", style="cyan", max_width=40)
    table.add_column("Timestamp", max_width=25)
    table.add_column("GPS", max_width=20)
    table.add_column("Camera", max_width=20)

    for path, exif in list(exif_data.items())[:5]:
        gps_str = ""
        if exif.get("gps"):
            gps_str = f"{exif['gps']['latitude']}, {exif['gps']['longitude']}"
        table.add_row(
            Path(path).name,
            exif.get("timestamp") or "-",
            gps_str or "-",
            exif.get("camera") or "-",
        )

    console.print(table)


@app.command()
def organize(
    manifest_path: Path = typer.Option(
        ...,
        "--manifest", "-m",
        help="Path to an enriched manifest.json file.",
        exists=True,
        dir_okay=False,
        resolve_path=True,
    ),
    output: Path = typer.Option(
        None,
        "--output", "-o",
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
    Run Phase 3b: propose a directory structure using a local LLM.

    Reads the enriched manifest (with captions + EXIF), feeds cluster
    summaries to the LLM, and writes an organization.json proposal.

    This is propose-only -- no files are moved. Review organization.json
    before any apply step.

    Requires Ollama running locally with a text model pulled.
    """
    from pixelkasten_ai.caption import check_ollama
    from pixelkasten_ai.manifest import read_manifest
    from pixelkasten_ai.organize import (
        build_cluster_summary_text,
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
    console.print(f"\n[bold]Step 2/5:[/bold] Reading manifest...")

    manifest = read_manifest(manifest_path)
    clusters = manifest.get("clusters", {})

    if not clusters:
        console.print("[red]No clusters found in manifest. Run embed first.[/red]")
        raise typer.Exit(code=1)

    # Warn if no EXIF data is present.
    has_exif = any(
        entry.get("exif") for entry in manifest["entries"]
    )
    if not has_exif:
        console.print(
            "[yellow]  No EXIF data found in manifest. "
            "Run 'enrich' first for better date-based organization.[/yellow]"
        )

    summary_text = build_cluster_summary_text(manifest)
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
    console.print(f"\n[bold]Step 3/5:[/bold] Sending to LLM for organization proposal...")

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
        e for e in manifest["entries"]
        if e.get("status") == "ok"
        and (e.get("cluster") is None or e.get("cluster") == -1 or str(e.get("cluster")) not in cluster_directories)
        and not e.get("exif", {}).get("timestamp")
    ]

    noise_exif = {}
    if noise_entries:
        from pixelkasten_ai.exif import read_exif

        noise_paths = [Path(e["path"]) for e in noise_entries]
        console.print(f"\n[bold]Step 4/5:[/bold] Reading EXIF for {len(noise_paths)} unclustered images...")

        with console.status("Reading EXIF..."):
            noise_exif = read_exif(noise_paths)

        n_with_date = sum(1 for e in noise_exif.values() if e.get("timestamp"))
        console.print(f"  {n_with_date} of {len(noise_paths)} have timestamps (will be placed by date)")
    else:
        console.print(f"\n[bold]Step 4/5:[/bold] No unclustered images need EXIF reading")

    # --- Step 5: Write plan ---
    console.print(f"\n[bold]Step 5/5:[/bold] Writing organization plan...")

    plan = build_organization_plan(manifest, cluster_directories, noise_exif=noise_exif)

    output_path = output if output is not None else manifest_path.parent / "organization.json"
    write_organization_plan(plan, cluster_directories, model, output_path)

    n_organized = sum(1 for p in plan if not p["target"].startswith("Unsorted/"))
    n_unsorted = sum(1 for p in plan if p["target"].startswith("Unsorted/"))

    console.print(f"\n[green bold]Done![/green bold] Organization plan written to {output_path}")
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
        "--plan", "-p",
        help="Path to an organization.json file.",
        exists=True,
        dir_okay=False,
        resolve_path=True,
    ),
    destination: Path = typer.Option(
        ...,
        "--destination", "-d",
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
    from pixelkasten_ai.organize import apply_organization_plan

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
        console.print(f"  [yellow]Skipped (source missing): {stats['skipped']}[/yellow]")
    if stats["failed"] > 0:
        console.print(f"  [red]Failed: {stats['failed']}[/red]")
