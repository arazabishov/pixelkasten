# pixelkasten-ai

AI-powered photo categorization using CLIP embeddings and clustering. Runs entirely on your local machine — no cloud API calls, no costs.

## Glossary

If you're new to ML, here are the key terms used throughout this codebase:

- **CLIP** — Contrastive Language-Image Pretraining. A model (by OpenAI, 2021) that converts both images and text into numerical vectors in the same space. This lets you directly compare "how similar is this photo to the concept of 'beach'?" by comparing their vectors.

- **Embedding** — A fixed-size array of numbers (vector) that represents the semantic meaning of an image or text. Similar content produces similar vectors. CLIP ViT-L/14 produces 768-dimensional embeddings.

- **Zero-shot classification** — Classifying images into categories without any training data. Works by comparing image embeddings against text label embeddings using cosine similarity.

- **Cosine similarity** — A measure of how similar two vectors are, ranging from -1 (opposite) to 1 (identical). For normalized vectors (unit length), it equals the dot product.

- **HDBSCAN** — A clustering algorithm that automatically discovers groups in data without needing to specify the number of groups upfront. It also identifies "noise" — data points that don't fit any group.

- **VLM** — Vision Language Model. A model that can look at an image and produce a text description. Used in Phase 2 for richer captioning of cluster representatives.

- **MPS** — Metal Performance Shaders. PyTorch's GPU acceleration for Apple Silicon. Uses the GPU cores for faster inference.

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- ~2GB disk space for the CLIP model weights (downloaded on first run)

### Phase 2 (VLM captioning) additionally requires:

- [Ollama](https://ollama.com/) installed and running (`ollama serve`)
- A vision model pulled — recommended options:
  - `ollama pull llava` — LLaVA, purpose-built for image understanding (recommended)
  - `ollama pull moondream` — Moondream, lightweight and fast

### Phase 3a (EXIF enrichment) additionally requires:

- [exiftool](https://exiftool.org/) — `brew install exiftool`

### Phase 3b (organization) additionally requires:

- Ollama with a text reasoning model:
  - `ollama pull qwen3.5:35b` — Best quality for 64GB RAM machines, multimodal (recommended)
  - `ollama pull qwen2.5:14b` — Good balance for 16-32GB RAM
  - `ollama pull qwen2.5:7b` — Lightweight, works on most machines

## Setup

```bash
cd ai

# Install all dependencies (creates .venv automatically)
uv sync
```

## Usage

### Phase 1: Embed & Cluster

```bash
# Run the Phase 1 pipeline on a directory of photos
uv run pixelkasten-ai embed -s ~/photos -o ./output

# Use a smaller/faster model (less accurate but quicker)
uv run pixelkasten-ai embed -s ~/photos -o ./output --model ViT-B-32

# Adjust clustering sensitivity (larger = fewer, bigger clusters)
uv run pixelkasten-ai embed -s ~/photos -o ./output --min-cluster-size 20

# Lower batch size if running out of memory
uv run pixelkasten-ai embed -s ~/photos -o ./output --batch-size 16

# See all Phase 1 options
uv run pixelkasten-ai embed --help
```

### Phase 2: VLM Captioning

After Phase 1 produces a manifest, caption the cluster representatives using a local vision model:

```bash
# Caption representatives using LLaVA (default)
uv run pixelkasten-ai caption -m ./output/manifest.json

# Use a different vision model
uv run pixelkasten-ai caption -m ./output/manifest.json --model moondream

# Custom captioning prompt
uv run pixelkasten-ai caption -m ./output/manifest.json --prompt "What is happening in this photo?"

# See all Phase 2 options
uv run pixelkasten-ai caption --help
```

### Phase 3a: EXIF Enrichment

Enrich the manifest with timestamps, GPS coordinates, and camera info from representative images:

```bash
# Read EXIF from representatives and enrich the manifest
uv run pixelkasten-ai enrich -m ./output/manifest.json
```

### Phase 3b: Organization Proposal

Feed cluster summaries to a local LLM to propose a directory structure:

```bash
# Propose organization using Qwen 2.5 32B (default)
uv run pixelkasten-ai organize -m ./output/manifest.json

# Use a different text model
uv run pixelkasten-ai organize -m ./output/manifest.json --model qwen2.5:14b

# Custom output path
uv run pixelkasten-ai organize -m ./output/manifest.json -o ./my-plan.json

# See all Phase 3b options
uv run pixelkasten-ai organize --help
```

The organize command writes an `organization.json` file with proposed `source -> target` mappings. This is propose-only — no files are moved. Review the output before any future apply step.

## Output

The pipeline produces two files in the output directory:

### `manifest.json`

Human-readable JSON with per-image metadata:

```json
{
  "version": 1,
  "embeddings_file": "embeddings.npy",
  "total_images": 1500,
  "embedded": 1498,
  "failed": 2,
  "entries": [
    {
      "path": "/photos/IMG_2451.jpg",
      "status": "ok",
      "cluster": 7,
      "tags": [
        {"name": "scene:beach", "score": 0.3142},
        {"name": "event:travel or vacation", "score": 0.2801}
      ],
      "is_representative": true
    }
  ]
}
```

### `embeddings.npy`

Raw embedding vectors in numpy binary format. Load with:

```python
import numpy as np
embeddings = np.load("output/embeddings.npy")
# Shape: (N, 768) — one 768-dimensional vector per image
```

These can be reused for re-clustering with different parameters, similarity search, or other downstream analysis without re-running the slow embedding step.

## Pipeline Stages

1. **Scan** — Find all supported image files (`.jpg`, `.jpeg`, `.heic`, `.png`).
2. **Embed** — Generate CLIP embeddings for each image (batched, GPU-accelerated).
3. **Cluster** — Group similar images using HDBSCAN.
4. **Classify** — Score each image against predefined text labels.
5. **Write** — Save results to `manifest.json` and `embeddings.npy`.

## Architecture

This module is part of the broader pixelkasten project. See `spec/ai-categorization.md` for the full design and `spec/architecture.md` for how it integrates with the Node.js pipeline.

```
Phase 1 (embed):     images → embeddings → clusters → tags → manifest
Phase 2 (caption):   cluster representatives → VLM captions → enriched manifest
Phase 3a (enrich):   representative images → exiftool → EXIF metadata → enriched manifest
Phase 3b (organize): enriched manifest → LLM reasoning → organization.json proposal
```
