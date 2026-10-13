"""FFmpeg renderer: cuts clips, turns photos into short videos, and joins them."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Callable

from .media import MediaItem, require_ffmpeg
from .plan import Step

FPS = 30
AUDIO_RATE = 48000
DEFAULT_SIZE = (1280, 720)
MAX_LONG_SIDE = 1920


def _even(n: int) -> int:
    return max(2, int(n) // 2 * 2)


def target_size(steps: list[Step], library: dict[str, MediaItem]) -> tuple[int, int]:
    """Use the first video in the plan; fall back to the first photo, then 720p."""
    ordered = [library[s.source] for s in steps]
    for item in [m for m in ordered if m.kind == "video"] + ordered:
        if item.width and item.height:
            w, h = item.width, item.height
            scale = min(1.0, MAX_LONG_SIDE / max(w, h))
            return _even(w * scale), _even(h * scale)
    return DEFAULT_SIZE


def _video_filter(w: int, h: int) -> str:
    return (
        f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
        f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black,"
        f"setsar=1,fps={FPS},format=yuv420p"
    )


ENCODE = [
    "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
    "-c:a", "aac", "-b:a", "160k", "-ar", str(AUDIO_RATE), "-ac", "2",
]
SILENCE = ["-f", "lavfi", "-i", f"anullsrc=r={AUDIO_RATE}:cl=stereo"]


def _run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.strip().splitlines()[-8:])
        raise RuntimeError(f"FFmpeg failed:\n{tail}")


def segment_command(step: Step, item: MediaItem, out: Path, w: int, h: int) -> list[str]:
    vf = _video_filter(w, h)
    dur = f"{step.duration:.3f}"
    if step.type == "image":
        return ["ffmpeg", "-y", "-loop", "1", "-framerate", str(FPS), "-i", item.path,
                *SILENCE, "-t", dur, "-map", "0:v:0", "-map", "1:a:0",
                "-vf", vf, *ENCODE, str(out)]
    cmd = ["ffmpeg", "-y", "-ss", f"{step.start:.3f}", "-i", item.path]
    if item.has_audio:
        cmd += ["-t", dur, "-map", "0:v:0", "-map", "0:a:0"]
    else:
        cmd += [*SILENCE, "-t", dur, "-map", "0:v:0", "-map", "1:a:0"]
    return cmd + ["-vf", vf, *ENCODE, str(out)]


def render(steps: list[Step], library: list[MediaItem], output: str | Path,
           progress: Callable[[float, str], None] | None = None) -> Path:
    """Render the plan into one MP4 file and return its path."""
    require_ffmpeg()
    lib = {m.name: m for m in library}
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    w, h = target_size(steps, lib)

    with tempfile.TemporaryDirectory(prefix="pve_") as tmp:
        tmp = Path(tmp)
        parts = []
        for i, step in enumerate(steps, start=1):
            if progress:
                progress((i - 1) / (len(steps) + 1), f"Preparing part {i} of {len(steps)}")
            part = tmp / f"part_{i:03d}.mp4"
            _run(segment_command(step, lib[step.source], part, w, h))
            parts.append(part)

        if progress:
            progress(len(steps) / (len(steps) + 1), "Joining parts")
        listing = tmp / "parts.txt"
        listing.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts))
        _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
              "-c", "copy", "-movflags", "+faststart", str(output)])
    if progress:
        progress(1.0, "Done")
    return output
