"""Edit plan: turns a raw plan (from the LLM or the rule parser) into checked,
fully numeric steps. Every number is computed here by ordinary Python."""

from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from pathlib import Path

from .media import MediaItem
from .timecode import TimecodeError, fmt, to_seconds

DEFAULT_IMAGE_SECONDS = 3.0
MAX_IMAGE_SECONDS = 600.0
END_TOLERANCE = 0.25  # seconds of slack for "end" slightly past the real end


@dataclass
class Step:
    type: str        # "clip" or "image"
    source: str      # media name, e.g. video1
    start: float     # seconds (0 for images)
    end: float       # seconds (duration for images)

    @property
    def duration(self) -> float:
        return self.end - self.start

    def to_dict(self) -> dict:
        d = asdict(self)
        d["duration"] = round(self.duration, 3)
        return d


class PlanError(ValueError):
    def __init__(self, errors: list[str]):
        super().__init__("\n".join(errors))
        self.errors = errors


_ALIASES = {
    "photo": "photo", "picture": "photo", "pic": "photo", "image": "photo", "img": "photo",
    "video": "video", "clip": "video", "vid": "video",
}


def resolve_source(ref, library: list[MediaItem]) -> MediaItem | None:
    """Match a reference like 'video1', 'Video 1', 'picture', 'beach.jpg'."""
    if ref is None:
        return None
    text = str(ref).strip().lower()
    by_name = {m.name: m for m in library}

    # exact short name, ignoring spaces, underscores and hyphens
    compact = re.sub(r"[\s_\-]+", "", text)
    if compact in by_name:
        return by_name[compact]

    # aliases with numbers: "picture 1", "image2", "vid 2"
    m = re.fullmatch(r"(photo|picture|pic|image|img|video|vid)(\d+)", compact)
    if m:
        base = _ALIASES[m.group(1)]
        return by_name.get(f"{base}{m.group(2)}")

    # bare words: "the picture" -> only image, "the video" -> only video
    word = re.sub(r"^(the|a|an)\s+", "", text)
    if word in ("photo", "picture", "pic", "image", "img", "photo1"):
        images = [x for x in library if x.kind == "image"]
        if len(images) >= 1:
            return images[0]

    # original file name or its stem
    for item in library:
        orig = item.original.lower()
        if text in (orig, Path(orig).stem):
            return item
    return None


def validate(raw_steps, library: list[MediaItem]) -> list[Step]:
    """Check a raw plan and convert all times to seconds. Raises PlanError."""
    if not isinstance(raw_steps, list) or not raw_steps:
        raise PlanError(["The plan is empty. Try describing which clips you want and their order."])

    steps: list[Step] = []
    errors: list[str] = []
    for i, raw in enumerate(raw_steps, start=1):
        label = f"Step {i}"
        if not isinstance(raw, dict):
            errors.append(f"{label}: not a valid step")
            continue
        item = resolve_source(raw.get("source"), library)
        if item is None:
            names = ", ".join(m.name for m in library) or "none uploaded"
            errors.append(f"{label}: unknown file {raw.get('source')!r} (available: {names})")
            continue

        stype = str(raw.get("type") or ("image" if item.kind == "image" else "clip")).lower()
        if item.kind == "image":
            try:
                dur = raw.get("duration")
                seconds = DEFAULT_IMAGE_SECONDS if dur in (None, "", 0, "0") else to_seconds(dur)
            except TimecodeError as e:
                errors.append(f"{label}: {e}")
                continue
            if seconds <= 0 or seconds > MAX_IMAGE_SECONDS:
                errors.append(f"{label}: photo duration must be between 0 and {int(MAX_IMAGE_SECONDS)} seconds")
                continue
            steps.append(Step("image", item.name, 0.0, seconds))
            continue

        if stype == "image":
            errors.append(f"{label}: {item.name} is a video, not a photo")
            continue

        try:
            start_raw = raw.get("start")
            end_raw = raw.get("end")
            start = 0.0 if start_raw in (None, "", "start", "beginning") else to_seconds(start_raw)
            if end_raw in (None, "", "end", "full", "all"):
                end = item.duration
            else:
                end = to_seconds(end_raw)
        except TimecodeError as e:
            errors.append(f"{label}: {e}")
            continue

        if item.duration and end > item.duration:
            if end - item.duration <= END_TOLERANCE:
                end = item.duration
            else:
                errors.append(
                    f"{label}: {item.name} is only {fmt(item.duration)} long, "
                    f"but the clip ends at {fmt(end)}"
                )
                continue
        if end <= start:
            errors.append(f"{label}: end ({fmt(end)}) must be after start ({fmt(start)})")
            continue
        steps.append(Step("clip", item.name, start, end))

    if errors:
        raise PlanError(errors)
    return steps


def summarize(steps: list[Step]) -> list[list]:
    """Rows for the timeline table shown in the interface."""
    rows = []
    t = 0.0
    for i, s in enumerate(steps, start=1):
        what = (f"{s.source} {fmt(s.start)} to {fmt(s.end)}" if s.type == "clip"
                else f"{s.source} (still photo)")
        rows.append([i, s.type, what, fmt(s.duration), f"{fmt(t)} to {fmt(t + s.duration)}"])
        t += s.duration
    return rows


def total_duration(steps: list[Step]) -> float:
    return sum(s.duration for s in steps)
