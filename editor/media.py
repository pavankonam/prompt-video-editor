"""Media library: gives each uploaded file a short name and reads its properties."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, asdict
from pathlib import Path

VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mkv", ".avi", ".webm", ".mpg", ".mpeg", ".3gp"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tif", ".tiff", ".heic"}


@dataclass
class MediaItem:
    name: str          # short name used in prompts, e.g. video1, photo1
    path: str          # absolute path on disk
    kind: str          # "video" or "image"
    original: str      # original file name
    duration: float = 0.0
    width: int = 0
    height: int = 0
    has_audio: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def require_ffmpeg() -> None:
    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            raise RuntimeError(
                f"{tool} was not found. On a Mac install it with: brew install ffmpeg"
            )


def kind_of(path: str | Path) -> str | None:
    ext = Path(path).suffix.lower()
    if ext in VIDEO_EXT:
        return "video"
    if ext in IMAGE_EXT:
        return "image"
    return None


def probe(path: str | Path) -> dict:
    """Return duration, width, height and audio presence using ffprobe."""
    require_ffmpeg()
    out = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration:stream=codec_type,width,height",
            "-of", "json", str(path),
        ],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        raise RuntimeError(f"Could not read {Path(path).name}: {out.stderr.strip()}")
    data = json.loads(out.stdout or "{}")
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), {})
    try:
        duration = float(data.get("format", {}).get("duration") or 0)
    except ValueError:
        duration = 0.0
    return {
        "duration": duration,
        "width": int(video.get("width") or 0),
        "height": int(video.get("height") or 0),
        "has_audio": any(s.get("codec_type") == "audio" for s in streams),
    }


def build_library(paths: list[str | Path]) -> list[MediaItem]:
    """Name files video1, video2, ... and photo1, photo2, ... in upload order."""
    items: list[MediaItem] = []
    counters = {"video": 0, "image": 0}
    for p in paths:
        p = Path(p)
        kind = kind_of(p)
        if kind is None:
            continue
        counters[kind] += 1
        name = f"video{counters[kind]}" if kind == "video" else f"photo{counters[kind]}"
        info = probe(p)
        if kind == "image":
            info["duration"] = 0.0
            info["has_audio"] = False
        items.append(MediaItem(name=name, path=str(p.resolve()), kind=kind,
                               original=p.name, **info))
    return items
