# Roadmap

Future work not yet implemented.

## Video Support

Extend album discovery to handle videos:

1. **Frame sampling** — extract keyframes via ffmpeg (one every 5-10 seconds, or scene-change detection). 3-5 frames per 30s clip is enough.
2. **Embedding** — run CLIP on sampled frames, average vectors. Videos and photos of the same scene cluster together naturally.
3. **Audio transcription** — Whisper (via `mlx-whisper` on Apple Silicon) can transcribe audio tracks locally. "Happy birthday to you..." immediately identifies the event type without looking at a frame.

**Caveat:** Averaging frame embeddings loses temporal information. A single vector can't distinguish "ceremony" from "reception" within a wedding video. Temporal segment analysis is a harder problem to defer.

## UI Layer

### Phase 3a: CLI (done)

Python CLI via typer + rich. Handles both takeout and discovery workflows.

### Phase 3b: Local Web UI

FastAPI server serving a local-only web UI for visual review:

- Thumbnail grids of each cluster
- Drag-and-drop corrections (move photos between clusters)
- Side-by-side comparison (current vs proposed structure)
- Progress dashboard (embedding, captioning status)

Frontend: Svelte, Preact, or vanilla JS. It's a local tool, not a web product.

### Phase 3c: Desktop App

For non-technical users who expect to double-click an `.app`:

- **Tauri** shell — Rust-based wrapper around OS webview (~10-15MB vs Electron's ~150MB+)
- Python backend bundled via PyInstaller or Nuitka (no Python install required)
- Ollama dependency: app checks if installed, prompts to download if not

### Architectural Requirement

The core library must remain independent of any UI framework. The CLI, web server, and desktop backend all import the same `pixelkasten.core` + `pixelkasten.stages` packages.
