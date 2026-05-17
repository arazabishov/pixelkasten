"""
Video frame extraction via ffmpeg subprocesses.

Used by enrich (for video embeddings) and caption (for multi-frame VLM input).
"""

import shutil
import subprocess


def check_ffmpeg() -> None:
    """Raise RuntimeError if ffmpeg or ffprobe is not on PATH."""
    for binary in ("ffmpeg", "ffprobe"):
        if shutil.which(binary) is None:
            raise RuntimeError(f"{binary} is required. Install with `brew install ffmpeg`.")


def extract_frames(video_path: str, n_frames: int) -> list[bytes]:
    """
    Extract `n_frames` uniformly-distributed JPEG frames from `video_path`.

    Returns a list of JPEG bytes, one per sampled frame. Raises RuntimeError
    if ffprobe/ffmpeg fails or the video has zero duration.
    """
    if n_frames < 1:
        raise ValueError("n_frames must be >= 1")

    duration = _probe_duration(video_path)
    if duration <= 0:
        raise RuntimeError(f"Could not determine duration for {video_path}")

    # Sample at the midpoints of n equal-width segments to avoid first/last-frame artifacts.
    timestamps = [duration * (i + 0.5) / n_frames for i in range(n_frames)]

    return [_capture_frame(video_path, t) for t in timestamps]


def _probe_duration(video_path: str) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            video_path,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed for {video_path}: {result.stderr.strip()}")
    try:
        return float(result.stdout.strip())
    except ValueError as e:
        raise RuntimeError(f"ffprobe returned non-numeric duration: {result.stdout!r}") from e


def _capture_frame(video_path: str, timestamp: float) -> bytes:
    # -ss BEFORE -i is fast (input seek) but can land on non-decodable positions
    # in some MP4 variants. Putting -ss AFTER -i is slower but reliably decodes
    # from the nearest keyframe; we accept the cost for correctness.
    result = subprocess.run(
        [
            "ffmpeg",
            "-loglevel",
            "error",
            "-i",
            video_path,
            "-ss",
            f"{timestamp:.3f}",
            "-frames:v",
            "1",
            "-f",
            "image2pipe",
            "-vcodec",
            "mjpeg",
            "-",
        ],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg frame extraction failed at t={timestamp:.3f}s for {video_path}: "
            f"{result.stderr.decode(errors='replace').strip()}"
        )
    payload = result.stdout
    # A valid JPEG always starts with FF D8 FF. Empty / non-JPEG output usually
    # means ffmpeg silently failed to decode this frame.
    if not payload.startswith(b"\xff\xd8\xff"):
        raise RuntimeError(
            f"ffmpeg produced no decodable frame at t={timestamp:.3f}s for {video_path} "
            f"({len(payload)} bytes returned); the codec or seek position may be unsupported."
        )
    return payload
