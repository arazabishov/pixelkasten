"""
Enrich command — geocode and CLIP-embed assets in a working library.

Walks the records directory for geocoding and the flat top-level media
files for embedding. Both steps are idempotent: re-running an enriched
library is a no-op. Failures (corrupt image, missing ffmpeg, etc.) are
logged to stderr and the file is skipped — the run continues. The end
of the run returns an ``EnrichResult`` so the caller (or CLI) can
report what changed and what failed.
"""

import io
import json
import os
import sys
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field

import numpy as np

from pixelkasten.configuration import EnrichOptions
from pixelkasten.handlers import is_image, is_video
from pixelkasten.configuration import RECORDS_DIR
from pixelkasten.utils.record import read_record, write_record
from pixelkasten.utils.record import records_dir
from pixelkasten.utils.embeddings import embeddings_npy_path, embeddings_paths_json_path


@dataclass
class EnrichResult:
    """End-of-run counts from the `enrich` command.

    Populated by ``enrich`` and rendered by
    ``pixelkasten_cli.render.render_enrich``. Per-file failure paths are
    recorded so the renderer can show a sample inline.
    """

    # total records walked across the working library
    records_total: int = 0

    # records that gained a `location` field this run
    locations_added: int = 0

    # records skipped because `location` was already set
    locations_already_set: int = 0

    # images that gained an embedding this run
    images_embedded: int = 0

    # videos that gained an embedding this run
    videos_embedded: int = 0

    # files skipped because their embedding was already in embeddings.npy
    already_embedded: int = 0

    # absolute paths of images that failed to embed (corrupt, decode error)
    images_failed: list[str] = field(default_factory=list)

    # absolute paths of videos that failed to embed (ffmpeg / CLIP failure)
    videos_failed: list[str] = field(default_factory=list)


# How many images go through one CLIP forward pass. The per-call Python/GPU
# overhead dominates when batch=1, so batching helps a lot; 32 is a
# conventional default with diminishing returns past it. Adjust here if
# you've benchmarked otherwise on your hardware.
EMBED_BATCH_SIZE = 32


@contextmanager
def _noop_progress(label: str, total: int):
    """Fallback progress factory used when none is supplied."""

    def _tick(_: int) -> None:
        pass

    yield _tick


def enrich(options: EnrichOptions, progress: Callable | None = None) -> EnrichResult:
    """Geocode + embed all assets in the working library; return counts."""
    library = options.library
    rdir = records_dir(library)
    if not os.path.isdir(rdir):
        raise RuntimeError(
            f"Not a working library (missing {RECORDS_DIR}/ at {library}). "
            "Run `pixelkasten import` first."
        )

    progress = progress or _noop_progress
    summary = EnrichResult()

    _geocode(rdir, summary, progress)
    _embed(library, options.video_frames, summary, progress)

    return summary


def _geocode(rdir: str, summary: EnrichResult, progress: Callable) -> None:
    """Reverse-geocode every record with geo set but no location yet."""
    pending = _pending_geocodes(rdir, summary)
    if not pending:
        return

    import reverse_geocoder as rg

    coords = list(pending.keys())
    results = rg.search(coords, verbose=False)

    total = sum(len(v) for v in pending.values())
    with progress("Reverse geocoding", total) as tick:
        _apply_geocode_results(pending, results, summary, tick)


def _pending_geocodes(rdir: str, summary: EnrichResult) -> dict[tuple[float, float], list[str]]:
    """Group records-needing-geocoding by rounded coordinate.

    Returns a dict whose keys are (lat, lon) rounded to 2dp and whose
    values are lists of record paths sharing that bucket. Also populates
    ``records_total`` and ``locations_already_set`` on ``summary``.
    """
    record_paths = sorted(_list_records(rdir))
    summary.records_total = len(record_paths)

    pending: dict[tuple[float, float], list[str]] = {}
    for path in record_paths:
        data = read_record(path)
        if data.get("location") is not None:
            summary.locations_already_set += 1
            continue
        geo = data.get("geo")
        if not geo:
            continue
        lat, lon = round(geo["latitude"], 2), round(geo["longitude"], 2)
        pending.setdefault((lat, lon), []).append(path)
    return pending


def _format_location(rg_result: dict) -> dict:
    """Shape one reverse_geocoder hit into the record's ``location`` field."""
    city = rg_result.get("name", "")
    region = rg_result.get("admin1", "")
    country = rg_result.get("cc", "")
    parts = [p for p in [city, region, country] if p]
    return {
        "name": ", ".join(parts),
        "region": ", ".join([p for p in [region, country] if p]),
        "country": country,
    }


def _apply_geocode_results(
    pending: dict[tuple[float, float], list[str]],
    results: list[dict],
    summary: EnrichResult,
    tick: Callable[[int], None],
) -> None:
    """Write each formatted location into every record sharing that bucket."""
    done = 0
    for coord, result in zip(pending.keys(), results):
        location = _format_location(result)
        for record_file in pending[coord]:
            data = read_record(record_file)
            data["location"] = location
            write_record(record_file, data)
            summary.locations_added += 1
            done += 1
            tick(done)


def _embed(
    library: str,
    video_frames: int,
    summary: EnrichResult,
    progress: Callable,
) -> None:
    """CLIP-embed every media file not already represented in embeddings.paths.json."""
    paths_file = embeddings_paths_json_path(library)
    npy_file = embeddings_npy_path(library)

    already_embedded: list[str]
    if os.path.exists(paths_file):
        with open(paths_file) as f:
            already_embedded = json.load(f)
    else:
        already_embedded = []
    embedded_set = set(already_embedded)

    media = sorted(_list_media(library))
    pending = [m for m in media if os.path.basename(m) not in embedded_set]
    summary.already_embedded = len(media) - len(pending)
    if not pending:
        return

    images = [p for p in pending if is_image(p)]
    videos = [p for p in pending if is_video(p)]

    from pixelkasten.utils.clip_embed import embed_images

    new_rows: list[np.ndarray] = []
    new_names: list[str] = []
    with progress("Embedding", len(pending)) as tick:
        # Images: batched through one CLIP forward pass per batch.
        completed = 0
        for start in range(0, len(images), EMBED_BATCH_SIZE):
            batch_paths = images[start : start + EMBED_BATCH_SIZE]
            batch_rows, batch_names, failed = _embed_image_batch(batch_paths, embed_images)
            new_rows.extend(batch_rows)
            new_names.extend(batch_names)
            summary.images_embedded += len(batch_names)
            summary.images_failed.extend(failed)
            completed += len(batch_paths)
            tick(completed)

        # Videos: still sequential since each one needs its own ffmpeg pipeline.
        for video_path in videos:
            try:
                row = _embed_video(video_path, video_frames, embed_images)
            except Exception as e:
                print(f"enrich: skipping {video_path}: {e}", file=sys.stderr)
                summary.videos_failed.append(video_path)
                completed += 1
                tick(completed)
                continue
            new_rows.append(row)
            new_names.append(os.path.basename(video_path))
            summary.videos_embedded += 1
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


def _embed_image_batch(
    paths: list[str], embed_images
) -> tuple[list[np.ndarray], list[str], list[str]]:
    """
    Decode a batch of images, run one CLIP forward pass, return rows + names + failures.

    Per-file decode failures (corrupt file, unsupported format) are logged and
    that file is dropped from the batch. A batch-level CLIP failure logs every
    member of the batch and drops the entire batch. Returns
    ``(rows, names, failed_paths)``.
    """
    from PIL import Image

    from pixelkasten.utils.pil_setup import ensure_pil_plugins

    ensure_pil_plugins()

    images: list = []
    names: list[str] = []
    failed: list[str] = []
    for path in paths:
        try:
            images.append(Image.open(path))
            names.append(os.path.basename(path))
        except Exception as e:
            print(f"enrich: skipping {path}: {e}", file=sys.stderr)
            failed.append(path)

    if not images:
        return [], [], failed

    try:
        matrix = embed_images(images)
    except Exception as e:
        for path in paths:
            print(f"enrich: skipping {path}: batch failed: {e}", file=sys.stderr)
        # The batch failure invalidates the per-file decoded set too; report
        # every input path as failed since none produced an embedding.
        return [], [], list(paths)

    if matrix.size == 0:
        return [], [], failed

    return [matrix[i] for i in range(matrix.shape[0])], names, failed


def _embed_video(path: str, video_frames: int, embed_images) -> np.ndarray:
    from PIL import Image

    from pixelkasten.utils.ffmpeg import extract_frames
    from pixelkasten.utils.pil_setup import ensure_pil_plugins

    ensure_pil_plugins()
    frames = extract_frames(path, video_frames)
    images = [Image.open(io.BytesIO(b)) for b in frames]
    matrix = embed_images(images)
    if matrix.size == 0:
        raise RuntimeError(f"Empty embedding for {path}")
    mean = matrix.mean(axis=0)
    return mean / np.linalg.norm(mean)


def _list_records(rdir: str) -> list[str]:
    return [os.path.join(rdir, name) for name in os.listdir(rdir) if name.endswith(".pk.json")]


def _list_media(library: str) -> list[str]:
    """Top-level media files in the working library (skips the records dir)."""
    return [
        os.path.join(library, name)
        for name in os.listdir(library)
        if not name.startswith(".")
        and os.path.isfile(os.path.join(library, name))
        and (is_image(name) or is_video(name))
    ]
