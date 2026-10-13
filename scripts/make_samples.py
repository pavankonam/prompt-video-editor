"""Create sample media to try the app without your own files.

Makes samples/video1.mp4 (6:10 long), samples/video2.mp4 (0:20) and
samples/photo1.png, matching the example in the README.
"""

import subprocess
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "samples"


def run(cmd):
    print(" ".join(cmd))
    subprocess.run(cmd, check=True, capture_output=True)


def main(long_seconds=370, short_seconds=20):
    OUT.mkdir(exist_ok=True)
    # Video 1: test pattern with a running clock and a tone
    run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"testsrc2=size=640x360:rate=30:duration={long_seconds}",
         "-f", "lavfi", "-i", f"sine=frequency=440:duration={long_seconds}",
         "-vf", "drawtext=text='VIDEO 1  %{pts\\:hms}':fontsize=28:fontcolor=white:box=1:boxcolor=black@0.6:x=40:y=40",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "30", "-c:a", "aac", "-shortest", str(OUT / "video1.mp4")])
    # Video 2: different pattern, vertical phone shape, different tone
    run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"smptebars=size=360x640:rate=30:duration={short_seconds}",
         "-f", "lavfi", "-i", f"sine=frequency=660:duration={short_seconds}",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "30", "-c:a", "aac", "-shortest", str(OUT / "video2.mp4")])
    # Photo
    run(["ffmpeg", "-y", "-f", "lavfi", "-i", "mandelbrot=size=1024x768", "-frames:v", "1",
         str(OUT / "photo1.png")])
    print(f"Samples written to {OUT}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--quick":
        main(long_seconds=360, short_seconds=5)
    else:
        main()
