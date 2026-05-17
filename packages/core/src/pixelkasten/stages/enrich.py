"""
Enrich stage — geocode and CLIP-embed assets in a working library.

Walks `.pixelkasten/*.pk.json` for geocoding and the flat top-level media
files for embedding. Both steps are idempotent: re-running an enriched
library is a no-op. Failures (corrupt image, missing ffmpeg, etc.) are
logged to stderr and the file is skipped — the run continues.
"""

import io
import json
import os
import sys
from collections.abc import Callable
from contextlib import contextmanager

import numpy as np

from pixelkasten.configuration import EnrichOptions

SIDECAR_DIR = ".pixelkasten"
EMBEDDINGS_NPY = "embeddings.npy"
EMBEDDINGS_PATHS_JSON = "embeddings.paths.json"

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".heic", ".png", ".mp"}
VIDEO_EXTENSIONS = {".mp4", ".mov"}

# How many images go through one CLIP forward pass. The per-call Python/GPU
# overhead dominates when batch=1, so even modest batching (~32) is ~5-10x
# faster on MPS. Larger batches save little once the GPU is saturated.
EMBED_BATCH_SIZE = 32


@contextmanager
def _noop_progress(label: str, total: int):
    """Fallback progress factory used when none is supplied."""

    def _tick(_: int) -> None:
        pass

    yield _tick


def enrich(options: EnrichOptions, progress: Callable | None = None) -> None:
    """Geocode + embed all assets in the working library."""
    library = options.library
    sidecar_dir = os.path.join(library, SIDECAR_DIR)
    if not os.path.isdir(sidecar_dir):
        raise RuntimeError(
            f"Not a working library (missing {SIDECAR_DIR}/ at {library}). "
            "Run `pixelkasten init` first."
        )

    progress = progress or _noop_progress

    _geocode(sidecar_dir, progress)
    _embed(library, sidecar_dir, options.video_frames, progress)

    if options.with_captions:
        # Bulk captioning will be wired up in Phase 10 alongside the standalone
        # `caption` command. For now we surface a clear message rather than
        # silently doing nothing.
        print(
            "--with-captions is not yet wired; use `pixelkasten caption <path>` per asset "
            "(Phase 10).",
            file=sys.stderr,
        )


# ---------- geocode ----------


def _geocode(sidecar_dir: str, progress: Callable) -> None:
    """For each sidecar with geo set and no location, reverse-geocode and write location."""
    sidecars = sorted(_list_pk_sidecars(sidecar_dir))
    if not sidecars:
        return

    # Group sidecars by rounded coordinate to make one batched call into reverse_geocoder.
    pending: dict[tuple[float, float], list[str]] = {}
    for path in sidecars:
        data = _read_json(path)
        if data.get("location") is not None:
            continue
        geo = data.get("geo")
        if not geo:
            continue
        lat, lon = round(geo["latitude"], 2), round(geo["longitude"], 2)
        pending.setdefault((lat, lon), []).append(path)

    if not pending:
        return

    import reverse_geocoder as rg

    coords = list(pending.keys())
    total = sum(len(v) for v in pending.values())
    with progress("Reverse geocoding", total) as tick:
        results = rg.search(coords, verbose=False)
        done = 0
        for coord, result in zip(coords, results):
            city = result.get("name", "")
            region = result.get("admin1", "")
            country = result.get("cc", "")
            parts = [p for p in [city, region, country] if p]
            location = {
                "name": ", ".join(parts),
                "region": ", ".join([p for p in [region, country] if p]),
                "country": country,
            }
            for sidecar_path in pending[coord]:
                data = _read_json(sidecar_path)
                data["location"] = location
                _write_json(sidecar_path, data)
                done += 1
                tick(done)


# ---------- embed ----------


def _embed(library: str, sidecar_dir: str, video_frames: int, progress: Callable) -> None:
    """CLIP-embed every media file not already represented in embeddings.paths.json."""
    paths_file = os.path.join(sidecar_dir, EMBEDDINGS_PATHS_JSON)
    npy_file = os.path.join(sidecar_dir, EMBEDDINGS_NPY)

    already_embedded: list[str]
    if os.path.exists(paths_file):
        with open(paths_file) as f:
            already_embedded = json.load(f)
    else:
        already_embedded = []
    embedded_set = set(already_embedded)

    media = sorted(_list_media(library))
    pending = [m for m in media if os.path.basename(m) not in embedded_set]
    if not pending:
        return

    images = [p for p in pending if os.path.splitext(p)[1].lower() in IMAGE_EXTENSIONS]
    videos = [p for p in pending if os.path.splitext(p)[1].lower() in VIDEO_EXTENSIONS]

    from pixelkasten.tools.clip_embed import embed_images

    new_rows: list[np.ndarray] = []
    new_names: list[str] = []
    with progress("Embedding", len(pending)) as tick:
        # Images: batched through one CLIP forward pass per batch.
        completed = 0
        for start in range(0, len(images), EMBED_BATCH_SIZE):
            batch_paths = images[start : start + EMBED_BATCH_SIZE]
            batch_rows, batch_names = _embed_image_batch(batch_paths, embed_images)
            new_rows.extend(batch_rows)
            new_names.extend(batch_names)
            completed += len(batch_paths)
            tick(completed)

        # Videos: still sequential since each one needs its own ffmpeg pipeline.
        for video_path in videos:
            try:
                row = _embed_video(video_path, video_frames, embed_images)
            except Exception as e:
                print(f"enrich: skipping {video_path}: {e}", file=sys.stderr)
                completed += 1
                tick(completed)
                continue
            new_rows.append(row)
            new_names.append(os.path.basename(video_path))
            completed += 1
            tick(completed)

    if not new_rows:
        return

    new_matrix = np.vstack(new_rows).astype(np.float32)

    if os.path.exists(npy_file):
        existing = np.load(npy_file)
        combined = (
            np.vstack([existing, new_matrix]).astype(np.float32) if existing.size else new_matrix
        )
    else:
        combined = new_matrix

    np.save(npy_file, combined)
    with open(paths_file, "w") as f:
        json.dump(already_embedded + new_names, f)


def _embed_image_batch(paths: list[str], embed_images) -> tuple[list[np.ndarray], list[str]]:
    """
    Decode a batch of images, run one CLIP forward pass, return rows + names.

    Per-file decode failures (corrupt file, unsupported format) are logged and
    that file is dropped from the batch. A batch-level CLIP failure logs every
    member of the batch and drops the entire batch.
    """
    from PIL import Image

    from pixelkasten.tools.pil_setup import ensure_pil_plugins

    ensure_pil_plugins()

    images: list = []
    names: list[str] = []
    for path in paths:
        try:
            images.append(Image.open(path))
            names.append(os.path.basename(path))
        except Exception as e:
            print(f"enrich: skipping {path}: {e}", file=sys.stderr)

    if not images:
        return [], []

    try:
        matrix = embed_images(images)
    except Exception as e:
        for path in paths:
            print(f"enrich: skipping {path}: batch failed: {e}", file=sys.stderr)
        return [], []

    if matrix.size == 0:
        return [], []

    return [matrix[i] for i in range(matrix.shape[0])], names


def _embed_video(path: str, video_frames: int, embed_images) -> np.ndarray:
    from PIL import Image

    from pixelkasten.tools.ffmpeg import extract_frames
    from pixelkasten.tools.pil_setup import ensure_pil_plugins

    ensure_pil_plugins()
    frames = extract_frames(path, video_frames)
    images = [Image.open(io.BytesIO(b)) for b in frames]
    matrix = embed_images(images)
    if matrix.size == 0:
        raise RuntimeError(f"Empty embedding for {path}")
    mean = matrix.mean(axis=0)
    return mean / np.linalg.norm(mean)


# ---------- helpers ----------


def _list_pk_sidecars(sidecar_dir: str) -> list[str]:
    return [
        os.path.join(sidecar_dir, name)
        for name in os.listdir(sidecar_dir)
        if name.endswith(".pk.json")
    ]


def _list_media(library: str) -> list[str]:
    """Top-level media files in the working library (skips .pixelkasten/)."""
    return [
        os.path.join(library, name)
        for name in os.listdir(library)
        if not name.startswith(".")
        and os.path.isfile(os.path.join(library, name))
        and os.path.splitext(name)[1].lower() in (IMAGE_EXTENSIONS | VIDEO_EXTENSIONS)
    ]


def _read_json(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def _write_json(path: str, data: dict) -> None:
    with open(path, "w") as f:
        json.dump(data, f)
