"""End to end test: builds small media files, runs the README example, checks the output."""

import shutil
import subprocess

import pytest

from editor.media import build_library, probe
from editor.planner import make_plan
from editor.render import render

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def _ff(*args):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], check=True)


@pytest.fixture(scope="module")
def media(tmp_path_factory):
    d = tmp_path_factory.mktemp("media")
    _ff("-f", "lavfi", "-i", "testsrc2=size=320x180:rate=30:duration=12",
        "-f", "lavfi", "-i", "sine=duration=12", "-c:v", "libx264", "-preset", "ultrafast",
        "-c:a", "aac", "-shortest", str(d / "a.mp4"))
    # second video has no audio track and a different shape
    _ff("-f", "lavfi", "-i", "smptebars=size=180x320:rate=25:duration=3",
        "-c:v", "libx264", "-preset", "ultrafast", str(d / "b.mp4"))
    _ff("-f", "lavfi", "-i", "color=c=orange:size=401x301", "-frames:v", "1", str(d / "p.png"))
    return build_library([d / "a.mp4", d / "p.png", d / "b.mp4"])


def test_full_pipeline(media, tmp_path):
    result = make_plan(
        "from video1 take 0:02 to 0:04 and 0:07 to 0:10. "
        "combine clip 1, then the photo for 2 seconds, then clip 2, then video2",
        media, engine="rules")
    out = render(result.steps, media, tmp_path / "out.mp4")
    info = probe(out)
    assert info["has_audio"]
    assert (info["width"], info["height"]) == (320, 180)
    assert abs(info["duration"] - (2 + 2 + 3 + 3)) < 0.5
