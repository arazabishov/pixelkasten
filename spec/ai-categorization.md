# AI Photo Categorization

## Problem

Pixelkasten currently handles Google Photos Takeout exports — matching sidecars, embedding metadata, and organizing files by date. But for older photos that were never in Google Photos (DSLR imports, phone backups, inherited archives), there's no sidecar metadata to work with. These photos sit in flat directories or arbitrary folder structures with no meaningful organization.

The goal is to use AI models to semantically understand and organize these photos — grouping by scene, event, subject — without requiring manual tagging.

## Constraints

- Image understanding via large cloud models (GPT-4V, Claude) is expensive at scale. A personal library of 50k+ photos would cost hundreds of dollars in API tokens.
- The solution should run locally or use very cheap cloud inference.
- Target hardware: MacBook Pro 16" with M1 Max and 64GB RAM — capable of running models up to ~13B parameters comfortably.

## Three-Phase Pipeline

### Phase 1: Embedding + Zero-Shot Tagging

**What:** Run every image through CLIP or SigLIP to produce a fixed-size vector (embedding) that captures the semantic content of the image.

**Why this works:** CLIP was trained on ~400M image-text pairs to map both images and text into the same vector space. Two photos of a beach produce similar vectors. A text string like "birthday party" produces a vector that's close to photos of birthday parties. This enables both clustering (group similar images) and zero-shot classification (score images against label sets) without any training.

**Model options:**

| Model          | Size         | Speed (M1 Max)         | Notes                                    |
| -------------- | ------------ | ---------------------- | ---------------------------------------- |
| CLIP ViT-L/14  | ~430M params | ~10-50ms/image         | The standard. Well-supported everywhere. |
| SigLIP ViT-SO  | ~400M params | ~10-50ms/image         | Google's improved CLIP. Better accuracy. |
| Apple mlx-clip | Same models  | Optimized for M-series | Native Apple Silicon via MLX framework.  |

**Output per image:**

- A 768-dimensional float vector (embedding)
- Zero-shot classification scores against predefined label sets

**Example label sets:**

```
Scenes:    ["beach", "mountain", "city street", "indoor", "garden", "forest"]
Events:    ["birthday", "wedding", "graduation", "holiday dinner", "concert"]
Subjects:  ["portrait", "group photo", "landscape", "food", "pet", "document"]
```

**Storage:** Embeddings and tag scores stored in a local SQLite database or JSON manifest, keyed by file path + content hash.

**Performance:** ~2-5 hours for 100k photos. This phase is embarrassingly parallel.

### Phase 2: Selective VLM Captioning

**What:** Run a local vision-language model on a small subset of images to generate rich natural-language descriptions.

**Why selective:** Running a VLM on every image is wasteful. Instead:

1. Cluster the embeddings from Phase 1 (HDBSCAN or k-means).
2. Select representative images from each cluster — the image closest to the centroid plus a few outliers.
3. Caption only those representatives (~5-10% of the library).
4. Cluster membership propagates the caption context to all other images in the group.

**Model options (all run locally via Ollama on M1 Max 64GB):**

| Model      | Size  | Speed       | Best for                                   |
| ---------- | ----- | ----------- | ------------------------------------------ |
| Moondream2 | ~1.8B | ~1-2s/image | Fast captioning, purpose-built             |
| Florence-2 | ~0.7B | <1s/image   | Structured output (captions, objects, OCR) |
| LLaVA 7B   | ~7B   | ~3-5s/image | Richer understanding, more context         |

**Output per representative image:**

- Natural language caption (e.g., "family gathering around a dinner table with birthday cake, indoor, evening lighting")
- Optionally: detected objects, text in image (OCR)

### Phase 3: Agent-Driven Organization

**What:** Feed the structured metadata from Phases 1-2 into an LLM agent (Claude Code, Copilot CLI, or a standalone script) that reasons about organization and proposes a directory structure.

**Input to the agent:**

- Cluster summaries: representative captions, tag distributions, member count
- Date ranges per cluster (from EXIF)
- GPS locations per cluster (reverse-geocoded to place names)
- User preferences: organize by event? by year+topic? by people?

**Why an agent:** The agent never sees raw image bytes — it works entirely with structured text. This makes it cheap (no vision tokens) and leverages what LLMs are best at: reasoning about categories, naming things, resolving ambiguity.

**Output:** A proposed mapping of `source_path → target_path` for user review before execution.

## Complementary Signals

### EXIF Metadata

EXIF data provides dimensions that pixel analysis cannot:

- **Timestamps** — strongest signal for event-based grouping. Photos within a 2-hour window at the same GPS location are almost certainly the same event.
- **GPS coordinates** — reverse geocode to meaningful place names. A cluster of beach photos becomes "Beach — Antalya, Turkey, July 2019."
- **Camera model** — distinguishes phone snapshots from DSLR shots.
- **Lens / focal length** — wide angle suggests landscapes, macro suggests close-ups, telephoto suggests wildlife or sports.

Pixelkasten already has EXIF reading infrastructure in the reconcile stage (`packages/core/src/stages/reconcile.js`) and format handlers (`packages/core/src/handlers/`). This is directly reusable.

### Signal Stack (Strongest → Weakest)

```
EXIF (timestamp + GPS)       → when and where
CLIP embeddings              → what it looks like
VLM captions (sampled)       → what's happening
Whisper transcription         → what's being said (videos only)
```

Each layer is independently useful. Combining them gives the agent much richer context — all without sending image bytes to a cloud API.

## Video Handling

The pipeline extends to video with minor adaptations:

1. **Frame sampling** — Extract keyframes via ffmpeg (one every 5-10 seconds, or scene-change detection). For a 30-second clip, 3-5 frames is enough. Don't process every frame.

2. **Embedding** — Run CLIP on each sampled frame, average the vectors. The composite vector lands in the same embedding space as photos, so videos and photos of the same scene cluster together naturally.

3. **Metadata** — QuickTime/MP4 containers carry timestamps, GPS, camera model — same as EXIF. Already handled by `packages/core/src/handlers/formats/quicktime.js`.

4. **Audio transcription (bonus)** — Whisper (via `mlx-whisper` on Apple Silicon) can transcribe the audio track locally. "Happy birthday to you..." immediately identifies the event type without looking at a single frame. This is optional but powerful for home videos.

**Caveat:** Averaging frame embeddings loses temporal information. A single vector can't distinguish "ceremony" from "reception" within a wedding video. For basic organization this is fine. Temporal analysis (splitting a long video into segments) is a more advanced problem to defer.

## Cost Analysis

| Phase                    | Compute         | Cost                   | Time (100k photos)         |
| ------------------------ | --------------- | ---------------------- | -------------------------- |
| Phase 1: CLIP embeddings | Local (M1 Max)  | Free                   | ~2-5 hours                 |
| Phase 2: VLM captioning  | Local (Ollama)  | Free                   | ~30-60 min (5-10k samples) |
| Phase 3: Agent reasoning | One LLM session | Negligible (text only) | Minutes                    |

The entire pipeline can process a large personal library without spending anything on API calls.

## Validation Strategy

This pipeline is experimental. Before investing in consolidation or UI work (see `architecture.md`), we need to validate that the AI produces useful results on real photo libraries.

**What to test:**

- Does CLIP clustering produce semantically meaningful groups? Or are clusters dominated by visual similarity (all blue photos together) rather than semantic similarity (all beach photos together)?
- Do zero-shot tag scores correlate with human judgment? Is "birthday party" actually scored higher for birthday photos than "landscape"?
- Does selective VLM captioning on cluster representatives produce useful descriptions, or are the captions too generic?
- Can an agent (or a rule-based script) turn the structured metadata into a directory structure that a human would actually want?

**How to test:**

- Run the pipeline on a personal photo library (1k-10k photos is sufficient for validation).
- Manually review a sample of clusters: are the groupings sensible?
- Compare the proposed organization against what you would have done manually.
- Iterate on label sets, clustering parameters, and captioning prompts.

The Node.js Takeout pipeline stays untouched until this validation passes. See `architecture.md` for the full sequencing.
