"""CLIP-embed working-library media files."""

from collections.abc import Callable

from pixelkasten.commands.enrich.state import Embed, EnrichEntry, EnrichState
from pixelkasten.handlers import is_image, is_video
from pixelkasten.pipeline import Status
from pixelkasten.tools.clip import embed_video


# Number of images per CLIP forward pass; 32 is a conservative CPU/GPU default.
EMBED_BATCH_SIZE = 32


def embed(state: EnrichState, video_frames: int, progress: Callable) -> None:
    """Compute an embedding for every entry, recording it on `entry.embed`.

    Pure stage: the expensive work (CLIP forward passes, ffmpeg frame
    extraction) happens here, but the result is staged on each entry for
    `emit` to persist. Every run re-embeds from scratch — there is no
    skip-if-already-embedded, matching ingest's "each run is a full run".
    """
    if not state.entries:
        return

    images = [e for e in state.entries if is_image(e.media)]
    videos = [e for e in state.entries if is_video(e.media)]

    with progress("Embedding", len(state.entries)) as tick:
        completed = 0

        # Images go through CLIP in batches — one forward pass per EMBED_BATCH_SIZE files.
        for start in range(0, len(images), EMBED_BATCH_SIZE):
            batch = images[start : start + EMBED_BATCH_SIZE]
            _embed_image_batch(batch)
            completed += len(batch)
            tick(completed)

        # Videos go one at a time — each is its own batch of sampled frames.
        for entry in videos:
            try:
                row = embed_video(entry.media, video_frames)
            except Exception as e:
                entry.embed = Embed(status=Status.ERROR, error=str(e))
            else:
                entry.embed = Embed(status=Status.PROCESSED, embedding=row)
            completed += 1
            tick(completed)


def _embed_image_batch(entries: list[EnrichEntry]) -> None:
    """Decode a batch of images, run one CLIP forward pass, set `entry.embed`.

    Per-file decode failures (corrupt file, unsupported format) mark just that
    entry `ERROR` and drop it from the batch — an isolated, per-item failure. A
    batch-level CLIP failure is fatal: it propagates and aborts the run, the
    same way a hard exiftool failure aborts `reconcile` during import.
    """
    from PIL import Image

    from pixelkasten.tools.clip import embed_images
    from pixelkasten.utils.pil import ensure_pil_plugins

    ensure_pil_plugins()

    decoded_images: list = []
    decoded_entries: list[EnrichEntry] = []
    for entry in entries:
        try:
            decoded_images.append(Image.open(entry.media))
            decoded_entries.append(entry)
        except Exception as e:
            entry.embed = Embed(status=Status.ERROR, error=str(e))

    if not decoded_images:
        return

    # A CLIP failure here is fatal (fail fast): let it propagate rather than
    # marking the batch ERROR and continuing to build a half-complete store.
    matrix = embed_images(decoded_images)

    for i, entry in enumerate(decoded_entries):
        entry.embed = Embed(status=Status.PROCESSED, embedding=matrix[i])
