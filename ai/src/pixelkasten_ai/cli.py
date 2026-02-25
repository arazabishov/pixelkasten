"""
CLI entry point — orchestrates the AI pipeline phases.

Usage:
    uv run pixelkasten-ai embed -s ~/photos -o ./output
    uv run pixelkasten-ai caption -m ./output/manifest.json --model llava

Phase 1 (embed): scan → embed → cluster → classify → write manifest
Phase 2 (caption): read manifest → caption representatives via VLM → enrich manifest
"""

import typer
from pathlib import Path
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table

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
