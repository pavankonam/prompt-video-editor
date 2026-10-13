"""Free local LLM planner using Ollama (https://ollama.com).

The model only translates the user's sentence into a JSON plan. It copies
times exactly as written; all conversions and checks happen in plan.py.
"""

from __future__ import annotations

import json
import os

import requests

from .media import MediaItem

DEFAULT_MODEL = os.environ.get("PVE_MODEL", "qwen2.5:7b")
DEFAULT_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
if not DEFAULT_HOST.startswith("http"):
    DEFAULT_HOST = "http://" + DEFAULT_HOST

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": ["clip", "image"]},
                    "source": {"type": "string"},
                    "start": {"type": "string"},
                    "end": {"type": "string"},
                    "duration": {"type": "string"},
                },
                "required": ["type", "source"],
            },
        }
    },
    "required": ["steps"],
}

SYSTEM_PROMPT = """You convert video editing instructions into a JSON edit plan.

Uploaded files:
{files}

Return ONLY JSON shaped like {{"steps": [ ... ]}}. Each step is one piece of the
final video, listed in the exact order it should play.

Step types:
1. A video piece: {{"type": "clip", "source": "<file name>", "start": "<time>", "end": "<time>"}}
   For a whole video use "start": "start" and "end": "end".
2. A photo: {{"type": "image", "source": "<file name>", "duration": "<seconds>"}}
   Use "3" when no duration is given.

Rules:
1. "source" must be one of the file names listed above (for example video1 or photo1).
2. Copy every time EXACTLY as the user wrote it, like "2:34". Never convert or calculate.
3. When the user defines clips and later refers to "the first clip" or "clip 2",
   put that clip's full step (source, start, end) at that position.
4. "the picture" or "the photo" means the uploaded photo. "the second video" means video2.
5. If time ranges are given without naming a video, use video1.
6. Do not add steps the user did not ask for.

Example
Files: video1 (video, 6:10), video2 (video, 0:45), photo1 (image)
Instruction: from the first video take 2:34 to 2:55 and 5:12 to 5:50. Combine the first clip, then the picture for 4 seconds, then the second clip, and finally the second video.
Answer: {{"steps": [
 {{"type": "clip", "source": "video1", "start": "2:34", "end": "2:55"}},
 {{"type": "image", "source": "photo1", "duration": "4"}},
 {{"type": "clip", "source": "video1", "start": "5:12", "end": "5:50"}},
 {{"type": "clip", "source": "video2", "start": "start", "end": "end"}}
]}}
"""


class LLMUnavailable(RuntimeError):
    pass


def describe_files(library: list[MediaItem]) -> str:
    from .timecode import fmt
    lines = []
    for m in library:
        if m.kind == "video":
            lines.append(f"{m.name} (video, length {fmt(m.duration)}, original name {m.original})")
        else:
            lines.append(f"{m.name} (image, original name {m.original})")
    return "\n".join(lines) or "(none)"


def is_available(host: str = DEFAULT_HOST) -> bool:
    try:
        return requests.get(f"{host}/api/tags", timeout=2).ok
    except requests.RequestException:
        return False


def installed_models(host: str = DEFAULT_HOST) -> list[str]:
    try:
        data = requests.get(f"{host}/api/tags", timeout=2).json()
        return [m["name"] for m in data.get("models", [])]
    except (requests.RequestException, ValueError, KeyError):
        return []


def ask(prompt: str, library: list[MediaItem], model: str = DEFAULT_MODEL,
        host: str = DEFAULT_HOST, feedback: str | None = None) -> list[dict]:
    """Ask the local model for a raw plan. Raises LLMUnavailable on connection problems."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT.format(files=describe_files(library))},
        {"role": "user", "content": prompt},
    ]
    if feedback:
        messages.append({"role": "user", "content":
                         f"Your previous plan had these problems:\n{feedback}\nReturn a corrected JSON plan."})
    try:
        resp = requests.post(
            f"{host}/api/chat",
            json={"model": model, "messages": messages, "stream": False,
                  "format": PLAN_SCHEMA, "options": {"temperature": 0}},
            timeout=180,
        )
    except requests.RequestException as e:
        raise LLMUnavailable(f"Could not reach Ollama at {host}: {e}") from e
    if resp.status_code == 404:
        raise LLMUnavailable(
            f"Model '{model}' is not installed. Run: ollama pull {model}")
    if not resp.ok:
        raise LLMUnavailable(f"Ollama error {resp.status_code}: {resp.text[:200]}")

    content = resp.json().get("message", {}).get("content", "")
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        raise ValueError(f"The model did not return valid JSON: {content[:200]}") from e
    steps = data.get("steps") if isinstance(data, dict) else data
    if not isinstance(steps, list):
        raise ValueError("The model's answer did not contain a list of steps.")
    return steps
