"""
CLI entry point — orchestrates the Phase 1 pipeline.

Usage:
    uv run pixelkasten-ai -s ~/photos -o ./output

This runs the full Phase 1 pipeline:
    scan → embed → cluster → classify → write manifest

The output directory will contain:
    - manifest.json: Per-image metadata (cluster, tags, scores).
    - embeddings.npy: Raw embedding vectors for reuse.
"""

import typer
from pathlib import Path
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table

from pixelkasten_ai.scan import scan, is_image
from pixelkasten_ai.embed import load_model, embed_images, embed_texts
from pixelkasten_ai.cluster import cluster_embeddings, find_representatives, cluster_summary
from pixelkasten_ai.classify import classify, build_label_list, DEFAULT_LABEL_SETS
from pixelkasten_ai.manifest import write_manifest

app = typer.Typer(
    name="pixelkasten-ai",
    help="AI-powered photo categorization using CLIP embeddings.",
    add_completion=False,
)
console = Console()


@app.command()
def run(
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
    Run the Phase 1 AI categorization pipeline.

    Scans a directory for images, generates CLIP embeddings, clusters
    similar images together, and classifies them against predefined labels.
    Results are written to a manifest file for inspection and downstream use.
    """
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
