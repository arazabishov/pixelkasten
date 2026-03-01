# Architecture & Integration

## Problem

Pixelkasten is a Node.js monorepo with two packages (`core` and `cli`) that handles Google Photos Takeout exports. The AI categorization pipeline described in `ai-categorization.md` requires Python for ML inference (CLIP, VLMs, clustering). We need to decide:

1. How to structure the AI code and its relationship to the existing codebase.
2. When (and whether) to consolidate into a single language.
3. How to evolve the project toward a UI that non-technical users can use.

## Guiding Principle: Prove the AI First

The AI categorization pipeline is experimental. We don't know yet whether CLIP clustering produces useful groupings for personal photo libraries, whether the VLM captions add meaningful value over zero-shot tags, or whether agent-driven organization produces results worth shipping.

**Do not rewrite the Node.js codebase until the AI pipeline proves its value.** The existing Takeout pipeline is tested, working, and solving a real problem. Rewriting it before validating the AI approach risks spending effort on consolidation that may not be needed.

The sequencing is:

1. **Build the AI pipeline in Python.** Get it working end-to-end on a real photo library. Evaluate the quality of clustering, tagging, and organization proposals.
2. **If the AI works well enough to ship**, consolidate into Python. Port the Takeout pipeline (scan, link, dedupe, reconcile, rename, apply) into the same Python project. The rename/apply stages become shared infrastructure between both workflows.
3. **If the AI doesn't pan out**, the Node.js codebase is unaffected. No wasted effort.

## Phase 1: AI Pipeline in Python (Complete)

The AI pipeline has been validated on real photo libraries and produces usable organization results. It has a full test suite (112 tests), CI integration, and has been iteratively improved through real-world testing.

### Project Structure

```
pixelkasten/
  packages/
    core/             ← existing Node.js pipeline (untouched)
    cli/              ← existing Node.js CLI (untouched)
  ai/
    pyproject.toml    ← project config, dependencies, pytest config
    src/
      pixelkasten_ai/
        cli.py        ← Typer CLI with 6 subcommands
        scan.py       ← image discovery
        embed.py      ← CLIP embeddings + batched inference
        cluster.py    ← HDBSCAN clustering + representative selection
        classify.py   ← zero-shot classification (may be removed)
        exif.py       ← exiftool subprocess + reverse geocoding
        refine.py     ← temporal split/merge + location-based absorption
        caption.py    ← VLM captioning via Ollama
        organize.py   ← LLM-driven album naming + organization plan
        manifest.py   ← manifest I/O + enrichment functions
    test/
      unit/           ← 96 pure-logic tests
      integration/    ← 16 tests (exiftool + pipeline data contracts)
      fixtures/media/ ← real JPEGs with stamped metadata
    README.md
```

The `ai/` directory is a standalone Python project. Not an npm package, no npm workspace entry. It communicates with the rest of pixelkasten only through a JSON manifest file.

### Manifest as Integration Boundary

The AI pipeline writes a `manifest.json` with per-image metadata:

```json
[
  {
    "path": "/photos/IMG_2451.jpg",
    "cluster": 7,
    "tags": ["beach", "landscape", "outdoor"],
    "caption": "Sandy beach with turquoise water, rocky coastline in background",
    "confidence": 0.89,
    "exif": {
      "timestamp": "2019-07-15T14:30:00",
      "gps": { "lat": 36.8, "lon": 30.6 },
      "camera": "iPhone 11"
    }
  }
]
```

This manifest is inspectable — you can open it, audit it, edit it before any files are moved. This matters for a tool that reorganizes your photos.

### Why Not Integrate with Node.js Now?

During this phase, the two tools are independent. The AI pipeline has its own CLI for running embeddings, captioning, and proposing organization. The Node.js Takeout pipeline continues to work as-is. They share only the naming scheme spec (`spec/naming-scheme.md`).

This avoids:

- Runtime coupling between Python and Node.js (no subprocess orchestration, no IPC).
- Forcing users to install both runtimes for a single workflow.
- Premature architectural decisions before we know what the AI pipeline needs.

## Phase 2: Consolidation into Python (Conditional)

**Prerequisite:** The AI pipeline has been validated on real photo libraries and produces organization results worth shipping.

### What Gets Ported

The Takeout pipeline stages, in order of complexity:

| Stage     | Lines | Complexity | Notes                                                    |
| --------- | ----- | ---------- | -------------------------------------------------------- |
| scan      | ~100  | Low        | Directory traversal, file categorization                 |
| rename    | ~150  | Low        | Date formatting, path construction, collision handling   |
| apply     | ~100  | Low        | File copy, metadata write via exiftool subprocess        |
| dedupe    | ~100  | Low        | SHA-256 hashing, resolution logic                        |
| reconcile | ~150  | Medium     | EXIF reading, sidecar comparison, write queue            |
| link      | ~250  | High       | Google Takeout sidecar matching with truncation patterns |

Total: ~850 lines of core logic. The link stage is the only complex piece — it encodes empirically-discovered edge cases in Google's filename truncation. **Port the test suite first**, then port the implementation and verify tests pass.

### Why Python for the Consolidated Codebase

- **Single runtime** for AI + file processing. No ecosystem split for contributors or users.
- **Better CLI libraries.** `typer` + `rich` provide a superior terminal experience (tables, spinners, syntax highlighting) compared to commander + cli-progress + cli-table3.
- **Direct ML integration.** No process boundary between the AI pipeline and file operations.
- **`pathlib`** is genuinely nicer than Node's `path` for file operations.
- **FastAPI** makes adding a web UI trivial (see Phase 3).

### What to Preserve

- The **naming scheme** (`spec/naming-scheme.md`) — the directory structure is the shared contract.
- The **handler pattern** — format-specific metadata logic (EXIF vs QuickTime) behind a common interface.
- The **manifest-driven pipeline** — stages enrich entries sequentially, side effects deferred to the apply stage.
- The **hooks pattern** — stage-level callbacks so different consumers (CLI, web UI, desktop app) can provide their own reporting.
- The **core/cli separation** — core logic as an importable library, CLI as a thin consumer. This is critical for the UI story.

### Node.js Archive

Tag the Node.js codebase before starting the port. Keep it accessible for reference — the test cases encode edge-case knowledge that's easy to miss during a rewrite.

## Phase 3: UI Layer (Future)

### The Problem

The AI categorization pipeline has an inherently interactive review step: the agent proposes organization, the user approves or adjusts. Reviewing 200 clusters with captions in a terminal table is painful. And for non-technical end users, CLI is a non-starter.

### Progressive Delivery

```
Phase 3a:  CLI (Python + typer/rich)
           └── for developers and power users

Phase 3b:  Local web UI (FastAPI + simple frontend)
           └── still requires Python, but visual cluster review

Phase 3c:  Desktop app (Tauri + bundled Python backend)
           └── ships as Pixelkasten.app, no prerequisites except Ollama
```

### Phase 3a: CLI

The Python CLI is the first consumer of the core library. It handles both workflows:

```bash
# Google Takeout processing
pixelkasten takeout -s ~/takeout-export -d ~/photos

# AI-based organization
pixelkasten organize -s ~/old-photos -d ~/photos
```

Single entry point, subcommands for different workflows.

### Phase 3b: Local Web App

A FastAPI server serving a local-only web UI. This is where visual review becomes possible:

- **Thumbnail grids** of each cluster, rendered from disk via the local server.
- **Drag-and-drop corrections** — move misclassified photos between clusters.
- **Side-by-side comparison** — current vs proposed directory structure.
- **Progress dashboard** — embedding generation, captioning status.

The frontend can be lightweight: Svelte, Preact, or vanilla JS with server-rendered HTML. It's a local tool, not a web product.

### Phase 3c: Desktop App

For non-technical end users who expect to double-click an `.app`:

**Tauri** is the recommended shell. It's a Rust-based wrapper around the OS webview (~10-15MB vs Electron's ~150MB+). Ships as a native `.app` on macOS, `.exe` on Windows. The frontend is the same web UI from Phase 3b.

The Python backend gets bundled via **PyInstaller** or **Nuitka** into a standalone binary — no Python installation required for end users.

**Ollama dependency:** If the AI pipeline delegates inference to Ollama, the app doesn't need to bundle torch/transformers (which would add ~500MB-1GB). Instead, the app checks if Ollama is installed and prompts the user to download it if not. Ollama itself ships as a native app with a one-click installer.

### Key Architectural Requirement

The **core library must remain independent of any UI framework.** The CLI, the FastAPI server, and the Tauri backend all import the same library. This is the same separation that exists today in the Node.js codebase (`core` vs `cli`) and must carry over to Python.

```
pixelkasten/
  core/           ← importable library, no UI dependencies
  cli/            ← typer-based CLI, imports core
  web/            ← FastAPI server + frontend, imports core
  desktop/        ← Tauri shell, calls bundled Python backend
```

## Integration Flow (End State)

```
                         ┌─────────────┐
  Photos on disk ───────>│  core/      │
                         │  embed      │──> manifest (in-memory or JSON)
                         │  caption    │        │
                         └─────────────┘        │
                                                │
                         ┌─────────────┐        │
                         │  core/      │<───────┘
                         │  organize   │
                         │  (agent or  │──> proposed layout
                         │   rules)    │        │
                         └─────────────┘        │
                                                │
                         ┌─────────────┐        │
  Organized archive <────│  core/      │<───────┘
                         │  rename +   │
                         │  apply      │
                         └─────────────┘

  Consumed by: CLI | Web UI | Desktop App
```

The manifest can be an in-memory data structure (when running as a library) or a JSON file on disk (when running as separate steps or for inspection). The pipeline is resumable — if organization looks wrong, adjust and re-run from that point without re-processing embeddings.
