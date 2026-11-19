"""
End-to-end pipeline test — no WhatsApp, no Meta, no credentials needed.
Creates a tiny test clip with ffmpeg and runs it through the edit
functions (compress, text, trim, hd, brand), verifying each output
with ffprobe. Run:  python test_pipeline.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from video_edit import (  # noqa: E402
    EditError,
    add_brand,
    add_text,
    compress,
    enhance_hd,
    file_size_mb,
    probe,
    trim,
)

HERE = Path(__file__).parent
TEST_DIR = HERE / "test_output"
TEST_DIR.mkdir(exist_ok=True)


def make_test_clip(path: Path) -> None:
    """5s, 1280x720 test video with a moving pattern + tone audio."""
    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "testsrc=duration=5:size=1280x720:rate=30",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=5",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest",
            str(path),
        ],
        check=True,
        timeout=120,
    )


def check(path: Path, label: str) -> None:
    info = probe(str(path))
    size = file_size_mb(str(path))
    assert info["duration"] > 0, f"{label}: zero duration"
    assert size > 0, f"{label}: empty file"
    print(f"  OK {label}: {info['width']}x{info['height']}, "
          f"{info['duration']:.2f}s, {size:.2f} MB")


def main() -> int:
    src = TEST_DIR / "sample.mp4"
    print("Making test clip...")
    make_test_clip(src)
    check(src, "sample")

    print("compress ...")
    check(Path(compress(str(src), str(TEST_DIR / "out_compress.mp4"))), "compress")

    print("text ...")
    check(Path(add_text(str(src), str(TEST_DIR / "out_text.mp4"), "Bijli Tips Part 24")), "text")

    print("trim 0:01 -> 0:03 ...")
    out = Path(trim(str(src), str(TEST_DIR / "out_trim.mp4"), 1.0, 3.0))
    check(out, "trim")
    assert abs(probe(str(out))["duration"] - 2.0) < 0.3, "trim length wrong"

    print("hd ...")
    check(Path(enhance_hd(str(src), str(TEST_DIR / "out_hd.mp4"))), "hd")

    print("brand ...")
    check(Path(add_brand(str(src), str(TEST_DIR / "out_brand.mp4"))), "brand")

    print("\nAll pipeline tests PASSED ✅")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except EditError as exc:
        print(f"FAILED: {exc}")
        raise SystemExit(1)
