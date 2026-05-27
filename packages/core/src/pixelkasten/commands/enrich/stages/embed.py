"""CLIP-embed working-library media files."""

import os
import sys
from collections.abc import Callable

import numpy as np

from pixelkasten.commands.enrich.state import EnrichState
from pixelkasten.handlers import is_image, is_video
from pixelkasten.utils.clip import embed_video
from pixelkasten.utils.embeddings import load_embeddings, save_embeddings


# Number of images per CLIP forward pass; 32 is a conservative CPU/GPU default.
EMBED_BATCH_SIZE = 32


def embed(
    library: str,
    media: list[str],
    state: EnrichState,
    video_frames: int,
    progress: Callable,
) -> None:
    """CLIP-embed every media file not already represented in embeddings.paths.json."""
    existing_matrix, embedded_names = load_embeddings(library, strict=False)
    embedded_set = set(embedded_names)

    embedded = [m for m in media if os.path.basename(m) in embedded_set]
    pending = [m for m in media if os.path.basename(m) not in embedded_set]
    state.images_already_embedded = sum(1 for p in embedded if is_image(p))
    state.videos_already_embedded = sum(1 for p in embedded if is_video(p))

    if not pending:
        return

    images = [p for p in pending if is_image(p)]
    videos = [p for p in pending if is_video(p)]

    new_rows: list[np.ndarray] = []
    new_names: list[str] = []
    with progress("Embedding", len(pending)) as tick:
        completed = 0
        for start in range(0, len(images), EMBED_BATCH_SIZE):
            batch_paths = images[start : start + EMBED_BATCH_SIZE]
            batch_rows, batch_names, batch_failed = _embed_image_batch(batch_paths)
            new_rows.extend(batch_rows)
            new_names.extend(batch_names)
            state.images_embedded += len(batch_names)
            state.images_failed.extend(batch_failed)
            completed += len(batch_paths)
            tick(completed)

        for video_path in videos:
            try:
                row = embed_video(video_path, video_frames)
            except Exception as e:
                print(f"enrich: skipping {video_path}: {e}", file=sys.stderr)
                state.videos_failed.append(video_path)
            else:
                new_rows.append(row)
                new_names.append(os.path.basename(video_path))
                state.videos_embedded += 1

            completed += 1
            tick(completed)

    if not new_rows:
        return

    new_matrix = np.vstack(new_rows).astype(np.float32)

    if existing_matrix is None or existing_matrix.size == 0:
        combined_matrix = new_matrix
    else:
        combined_matrix = np.vstack([existing_matrix, new_matrix]).astype(np.float32)
    save_embeddings(library, combined_matrix, embedded_names + new_names)
    save_embeddings(library, combined_matrix, embedded_names + new_names)


def _embed_image_batch(paths: list[str]) -> tuple[list[np.ndarray], list[str], list[str]]:
    """
    Decode a batch of images, run one CLIP forward pass, return rows + names + failures.

    Per-file decode failures (corrupt file, unsupported format) are logged and
    that file is dropped from the batch. A batch-level CLIP failure logs every
    member of the batch and drops the entire batch. Returns
    ``(rows, names, failed_paths)``.
    """
    from PIL import Image

    from pixelkasten.utils.clip import embed_images
    from pixelkasten.utils.pil import ensure_pil_plugins

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
