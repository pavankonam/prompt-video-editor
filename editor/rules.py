"""Offline rule based parser.

Used when no local LLM is running (or when you pick the "rules" engine).
It understands prompts such as:

    From video1 take 2:34 to 2:55 and 5:12 to 5:50.
    Then put clip 1, the picture for 4 seconds, clip 2 and then video2.

It returns a raw plan in the same shape the LLM produces, so both engines
share the same validation and rendering code.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .media import MediaItem

ORDINALS = {
    "first": 1, "1st": 1, "second": 2, "2nd": 2, "third": 3, "3rd": 3,
    "fourth": 4, "4th": 4, "fifth": 5, "5th": 5, "sixth": 6, "6th": 6,
    "seventh": 7, "7th": 7, "eighth": 8, "8th": 8, "last": -1,
}
ORD = "|".join(sorted(ORDINALS, key=len, reverse=True))

TIME = r"\d{1,2}(?::\d{1,2}){1,2}(?:\.\d+)?|\d+(?:\.\d+)?\s*(?:s|sec|secs|seconds)\b"
RANGE_RE = re.compile(
    rf"(?:between\s+(?P<a1>{TIME})\s+and\s+(?P<b1>{TIME}))"
    rf"|(?:(?:from\s+)?(?P<a2>{TIME})\s*(?:to|till|until|through|thru|[-–—~])\s*(?P<b2>{TIME}))",
    re.IGNORECASE,
)
SENTENCE_SPLIT = re.compile(r"[;!?\n]|\.(?!\d)")
SOURCE_LEAD = re.compile(r"(?:from|of|in|out\s+of)\s+(?:the\s+)?$", re.IGNORECASE)
DURATION_AFTER = re.compile(
    rf"^[\s,(]*(?:for\s+|lasting\s+|of\s+)?(?P<d>\d+(?:\.\d+)?)\s*(?:s|sec|secs|seconds)\b",
    re.IGNORECASE,
)
GLOBAL_PHOTO_DURATION = re.compile(
    r"(?:photo|picture|pic|image|img)s?\b[^.;\n]{0,25}?\bfor\s+(?P<d>\d+(?:\.\d+)?)\s*(?:s|sec|secs|seconds)\b",
    re.IGNORECASE,
)


@dataclass
class Mention:
    start: int
    end: int
    kind: str            # "media" or "clip"
    media: str | None    # media name for kind == media
    clip_index: int | None  # 1 based, or -1 for "last", for kind == clip
    is_source: bool = False


def _mention_regex(library: list[MediaItem]) -> re.Pattern:
    names = []
    for item in library:
        names.append(re.escape(item.original.lower()))
        stem = item.original.rsplit(".", 1)[0].lower()
        if len(stem) >= 3:
            names.append(re.escape(stem))
    names.sort(key=len, reverse=True)
    parts = []
    if names:
        parts.append(rf"(?P<file>(?<![\w.])(?:{'|'.join(names)})(?![\w]))")
    parts += [
        r"(?P<named>\b(?P<nk>video|vid|photo|picture|pic|image|img)\s*#?(?P<nn>\d+)\b)",
        rf"(?P<ordm>\b(?P<oo>{ORD})\s+(?P<ok>video|vid|photo|picture|pic|image|img)\b)",
        r"(?P<clipn>\b(?:clip|cut|segment|part)\s*#?(?P<cn>\d+)\b)",
        rf"(?P<clipo>\b(?P<co>{ORD})\s+(?:clip|cut|segment|part)\b)",
        r"(?P<bare>\b(?:photo|picture|pic|image|img)\b(?!\s*#?\d))",
    ]
    return re.compile("|".join(parts), re.IGNORECASE)


def _nth(items: list[MediaItem], n: int) -> MediaItem | None:
    if not items:
        return None
    if n == -1:
        return items[-1]
    return items[n - 1] if 1 <= n <= len(items) else None


def _find_mentions(text: str, library: list[MediaItem]) -> list[Mention]:
    videos = [m for m in library if m.kind == "video"]
    images = [m for m in library if m.kind == "image"]
    by_name = {m.name: m for m in library}
    by_file = {}
    for m in library:
        by_file[m.original.lower()] = m
        by_file.setdefault(m.original.rsplit(".", 1)[0].lower(), m)

    mentions: list[Mention] = []
    for mt in _mention_regex(library).finditer(text):
        item = None
        if mt.group("file"):
            item = by_file.get(mt.group("file").lower())
        elif mt.group("named"):
            k = mt.group("nk").lower()
            base = "video" if k in ("video", "vid") else "photo"
            item = by_name.get(f"{base}{int(mt.group('nn'))}")
        elif mt.group("ordm"):
            k = mt.group("ok").lower()
            pool = videos if k in ("video", "vid") else images
            item = _nth(pool, ORDINALS[mt.group("oo").lower()])
        elif mt.group("clipn"):
            mentions.append(Mention(mt.start(), mt.end(), "clip", None, int(mt.group("cn"))))
            continue
        elif mt.group("clipo"):
            mentions.append(Mention(mt.start(), mt.end(), "clip", None, ORDINALS[mt.group("co").lower()]))
            continue
        elif mt.group("bare"):
            item = images[0] if images else None
        if item is not None:
            mentions.append(Mention(mt.start(), mt.end(), "media", item.name, None))
    return mentions


def _sentence_id(pos: int, bounds: list[int]) -> int:
    sid = 0
    for b in bounds:
        if pos >= b:
            sid += 1
    return sid


def parse(prompt: str, library: list[MediaItem]) -> tuple[list[dict], list[str]]:
    """Return (raw_steps, notes). Times are left as text for validate() to compute."""
    text = prompt.lower()
    notes: list[str] = []
    videos = [m for m in library if m.kind == "video"]
    kinds = {m.name: m.kind for m in library}

    mentions = _find_mentions(text, library)
    ranges = list(RANGE_RE.finditer(text))
    bounds = [m.end() for m in SENTENCE_SPLIT.finditer(text)]

    # Decide which video mentions are sources of the time ranges
    for men in mentions:
        if men.kind != "media" or kinds.get(men.media) != "video":
            continue
        before = text[: men.start]
        lead = SOURCE_LEAD.search(before[-20:]) is not None
        same_sentence_range = any(
            _sentence_id(r.start(), bounds) == _sentence_id(men.start, bounds) for r in ranges
        )
        follows_directly = any(
            0 <= r.start() - men.end <= 30
            and not re.search(r"\bthen\b|,", text[men.end:r.start()])
            for r in ranges
        )
        if (lead and same_sentence_range) or follows_directly:
            men.is_source = True

    # Build the clip list from the ranges, in the order they were written
    clips: list[dict] = []
    sources = [m for m in mentions if m.is_source]
    for r in ranges:
        a = r.group("a1") or r.group("a2")
        b = r.group("b1") or r.group("b2")
        sid = _sentence_id(r.start(), bounds)
        same = [m for m in sources if _sentence_id(m.start, bounds) == sid]
        src = None
        before_same = [m for m in same if m.start < r.start()]
        after_same = [m for m in same if m.start > r.start()]
        if before_same:
            src = before_same[-1].media
        elif after_same:
            src = after_same[0].media
        else:
            earlier = [m for m in sources if m.start < r.start()]
            if earlier:
                src = earlier[-1].media
        if src is None:
            if not videos:
                raise ValueError("Time ranges were given but no video is uploaded.")
            src = videos[0].name
            if len(videos) > 1:
                note = f"Some time ranges did not name a video, so {src} was used for them."
                if note not in notes:
                    notes.append(note)
        clips.append({"type": "clip", "source": src, "start": a.strip(), "end": b.strip()})

    # Photo durations
    photo_seconds: dict[str, str] = {}
    for men in mentions:
        if men.kind == "media" and kinds.get(men.media) == "image":
            m = DURATION_AFTER.match(text[men.end: men.end + 30])
            if m:
                photo_seconds[men.media] = m.group("d")
    g = GLOBAL_PHOTO_DURATION.search(text)
    default_photo = g.group("d") if g else None

    def image_step(name: str) -> dict:
        d = photo_seconds.get(name) or default_photo
        return {"type": "image", "source": name, **({"duration": d} if d else {})}

    # Order. If the prompt refers to clips ("clip 1", "the second clip"), the
    # time ranges are only definitions. Otherwise each range is placed where
    # it was written. Everything else follows reading order.
    has_clip_refs = any(m.kind == "clip" for m in mentions)
    events: list[tuple[int, dict]] = []
    for men in mentions:
        if men.is_source:
            continue
        if men.kind == "clip":
            idx = men.clip_index
            if not clips:
                raise ValueError("A clip was mentioned but no time ranges were found.")
            clip = clips[-1] if idx == -1 else (clips[idx - 1] if 1 <= idx <= len(clips) else None)
            if clip is None:
                raise ValueError(f"Clip {idx} was mentioned but only {len(clips)} clip(s) were defined.")
            events.append((men.start, dict(clip)))
        elif kinds.get(men.media) == "image":
            events.append((men.start, image_step(men.media)))
        else:
            events.append((men.start, {"type": "clip", "source": men.media, "start": "start", "end": "end"}))
    if not has_clip_refs:
        events += [(r.start(), dict(c)) for r, c in zip(ranges, clips)]
    events.sort(key=lambda e: e[0])
    steps: list[dict] = [e[1] for e in events]

    if not steps:
        for item in library:
            steps.append(image_step(item.name) if item.kind == "image"
                         else {"type": "clip", "source": item.name, "start": "start", "end": "end"})
        notes.append("No clips or order were found, so all files are joined in upload order.")
    return steps, notes
