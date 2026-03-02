# Design Decisions

Key architectural and design decisions behind PixelKasten.

## Why Python

- **Single runtime** for AI + file processing. No ecosystem split for contributors or users.
- **Better CLI libraries.** `typer` + `rich` provide a superior terminal experience compared to Node.js alternatives.
- **Direct ML integration.** No process boundary between the AI pipeline and file operations.
- **`pathlib`** for path construction is genuinely nicer than Node's `path` module.
- **FastAPI** makes adding a web UI trivial when the time comes.

## Pipeline Architecture

Both takeout and archive modes share a manifest-driven pipeline. Stages enrich entries sequentially; side effects (file copy, metadata write) are deferred to the apply stage.

**Key patterns preserved from the original Node.js design:**
- **Handler pattern** — format-specific metadata logic (EXIF vs QuickTime) behind a common protocol.
- **Hooks pattern** — stage-level callbacks so different consumers (CLI, web UI, desktop app) can provide their own reporting.
- **Core/CLI separation** — core logic is an importable library (`pixelkasten.core` + `pixelkasten.stages`), CLI is a thin consumer. Critical for the future UI story.

## AI Catalog Pipeline

The `--catalog` flag enables AI-powered album discovery. The pipeline runs entirely locally — no cloud API calls.

### Constraints

- Cloud vision APIs (GPT-4V, Claude) cost hundreds of dollars at scale (50k+ photos). Local inference is free.
- Target hardware: MacBook Pro with Apple Silicon, 16-64GB RAM. Models up to ~13B parameters run comfortably.

### Signal Stack (strongest to weakest)

```
EXIF (timestamp + GPS)       → when and where
CLIP embeddings              → what it looks like
VLM captions (sampled)       → what's happening
```

Each layer is independently useful. Combining them gives the LLM much richer context for album naming — all without sending image bytes to a cloud API.

### Cost

| Phase | Compute | Cost | Time (100k photos) |
|---|---|---|---|
| CLIP embeddings | Local (Apple Silicon) | Free | ~2-5 hours |
| VLM captioning | Local (Ollama) | Free | ~30-60 min (5-10k samples) |
| LLM album naming | One text session | Negligible | Minutes |

### Cluster Refinement

Pure visual clustering (HDBSCAN on CLIP embeddings) groups by appearance — all blue photos together. EXIF metadata fixes this:

1. **Eject** images with no EXIF from clusters (most error-prone).
2. **Split** clusters at temporal gaps > 48 hours (breaks "beach 2017 + beach 2023").
3. **Merge** visually similar clusters that are temporally close (< 7 days). Same-region clusters get a lower similarity threshold.
4. **Absorb** noise images by location — travel photos HDBSCAN missed.
5. **Absorb** noise images by visual similarity — GPS-less images near a cluster's date range.

**Key decisions:**
- Region-level matching (state/province, not city) — groups nearby cities
- Home location inference from most frequent region — prevents over-absorbing local photos
- Location outlier filtering (< 10%) — catches transit GPS from flights
