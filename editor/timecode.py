"""Time parsing and formatting.

All arithmetic lives here as plain Python, never inside the LLM.
"""

from __future__ import annotations

import re

_UNIT_RE = re.compile(
    r"^\s*(?:(?P<h>\d+(?:\.\d+)?)\s*h(?:ours?|rs?)?)?\s*"
    r"(?:(?P<m>\d+(?:\.\d+)?)\s*m(?:in(?:utes?|s)?)?)?\s*"
    r"(?:(?P<s>\d+(?:\.\d+)?)\s*s(?:ec(?:onds?|s)?)?)?\s*$",
    re.IGNORECASE,
)


class TimecodeError(ValueError):
    pass


def to_seconds(value) -> float:
    """Convert a time value into seconds.

    Accepts: 154, 154.5, "154", "2:34", "02:34.5", "1:02:34", "2m34s",
    "2 min 34 sec", "45s", "45 seconds".
    """
    if value is None:
        raise TimecodeError("missing time value")
    if isinstance(value, bool):
        raise TimecodeError(f"invalid time value: {value!r}")
    if isinstance(value, (int, float)):
        if value < 0:
            raise TimecodeError(f"time cannot be negative: {value}")
        return float(value)

    text = str(value).strip().lower()
    if not text:
        raise TimecodeError("empty time value")

    # Plain number, possibly with decimals
    if re.fullmatch(r"\d+(?:\.\d+)?", text):
        return float(text)

    # Colon formats: m:ss, mm:ss, h:mm:ss (optional fractional seconds)
    if ":" in text:
        parts = text.split(":")
        if len(parts) > 3 or not all(re.fullmatch(r"\d+(?:\.\d+)?", p) for p in parts):
            raise TimecodeError(f"invalid timecode: {value!r}")
        nums = [float(p) for p in parts]
        for n in nums[1:]:
            if n >= 60:
                raise TimecodeError(f"minutes/seconds must be under 60: {value!r}")
        total = 0.0
        for n in nums:
            total = total * 60 + n
        return total

    # Unit formats: 2m34s, 2 min 34 sec, 45 seconds, 1h2m
    m = _UNIT_RE.match(text)
    if m and any(m.group(k) for k in ("h", "m", "s")):
        h = float(m.group("h") or 0)
        mi = float(m.group("m") or 0)
        s = float(m.group("s") or 0)
        return h * 3600 + mi * 60 + s

    raise TimecodeError(f"could not understand time: {value!r}")


def fmt(seconds: float) -> str:
    """Format seconds as m:ss or h:mm:ss (keeps tenths if not whole)."""
    seconds = round(max(0.0, float(seconds)), 1)
    whole = int(seconds)
    frac = seconds - whole
    h, rem = divmod(whole, 3600)
    m, s = divmod(rem, 60)
    sec = f"{s:02d}" if frac < 0.05 else f"{s + frac:04.1f}"
    if h:
        return f"{h}:{m:02d}:{sec}"
    return f"{m}:{sec}"
