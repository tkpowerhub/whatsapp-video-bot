"""
Video editing engine for the Tk PowerHub WhatsApp video-edit bot.
Pure ffmpeg — no AI generation. All outputs are phone-friendly
(720p default, 1080p max, H.264 + AAC, faststart for WhatsApp).
"""

from __future__ import annotations

import os
import re
import subprocess

# ---------------------------------------------------------------------------
# Paths / constants
# ---------------------------------------------------------------------------

FONT_PATH = os.environ.get(
    "BOT_FONT_PATH", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
)
BRAND_TEXT = "Tk PowerHub"

# WhatsApp caps a video message at 16 MB. Keep a safety margin.
MAX_RETURN_MB = 15.0

# Video bitrates (crf-based, capped) — light enough for a weak phone.
CRF_720 = "24"
CRF_1080 = "22"


class EditError(Exception):
    """Raised when ffmpeg fails or the input is unusable."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_ffmpeg(args: list[str], timeout: int = 600) -> None:
    """Run ffmpeg, raising EditError with the tail of stderr on failure."""
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"] + args
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        tail = (proc.stderr or "").strip()[-600:]
        raise EditError(f"ffmpeg failed ({proc.returncode}): {tail}")


def probe(path: str) -> dict:
    """Return width/height/duration of a video file via ffprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        path,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        raise EditError(f"ffprobe failed on {path}: {(proc.stderr or '').strip()[-300:]}")
    lines = [ln.strip() for ln in proc.stdout.strip().splitlines() if ln.strip()]
    if len(lines) < 3:
        raise EditError(f"Could not read video info from {path}")
    return {
        "width": int(lines[0]),
        "height": int(lines[1]),
        "duration": float(lines[2]),
    }


def file_size_mb(path: str) -> float:
    return os.path.getsize(path) / (1024 * 1024)


def parse_timestamp(value: str) -> float:
    """Accept 'SS', 'MM:SS' or 'HH:MM:SS' -> seconds."""
    value = value.strip()
    if re.fullmatch(r"\d+(\.\d+)?", value):
        return float(value)
    parts = value.split(":")
    if len(parts) not in (2, 3):
        raise EditError(f"Ghalat time format: '{value}' — '0:05' ya '1:20' likho.")
    try:
        nums = [float(p) for p in parts]
    except ValueError:
        raise EditError(f"Ghalat time format: '{value}'")
    total = 0.0
    for n in nums:
        total = total * 60 + n
    return total


# ---------------------------------------------------------------------------
# drawtext escaping
# ---------------------------------------------------------------------------

def _escape_drawtext(text: str) -> str:
    """Escape text for ffmpeg drawtext. Keeps it to one safe line."""
    text = " ".join(text.split())  # collapse whitespace / newlines
    text = text.replace("\\", "\\\\").replace("'", "\\'").replace(":", "\\:")
    text = text.replace("%", "\\%")
    return text


def _drawtext_filter(text: str, fontsize: int = 56, y: str = "h-90") -> str:
    safe = _escape_drawtext(text)
    return (
        f"drawtext=fontfile={FONT_PATH}:text='{safe}':"
        f"fontsize={fontsize}:fontcolor=white:"
        f"borderw=2:bordercolor=black:x=(w-text_w)/2:y={y}"
    )


# ---------------------------------------------------------------------------
# Edit operations — each takes (src, dst) and returns dst
# ---------------------------------------------------------------------------

def compress(src: str, dst: str) -> str:
    """Light phone-friendly version: 720p, capped bitrate, faststart."""
    _run_ffmpeg([
        "-i", src,
        "-vf", "scale=720:-2",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", CRF_720,
        "-maxrate", "1500k", "-bufsize", "3000k",
        "-c:a", "aac", "-b:a", "96k",
        "-movflags", "+faststart",
        dst,
    ])
    _enforce_size(src, dst)
    return dst


def enhance_hd(src: str, dst: str) -> str:
    """Upscale/enhance to 1080p with light sharpening (no fake pixels)."""
    info = probe(src)
    if info["width"] >= 1080 and info["height"] >= 1920:
        # Already 1080p or better — just re-encode cleanly at good quality.
        _run_ffmpeg([
            "-i", src,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", CRF_1080,
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart",
            dst,
        ])
    else:
        _run_ffmpeg([
            "-i", src,
            "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,"
                   "crop=1080:1920,unsharp=5:5:0.6:5:5:0.0",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", CRF_1080,
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart",
            dst,
        ])
    _enforce_size(src, dst)
    return dst


def trim(src: str, dst: str, start: float, end: float) -> str:
    """Cut a segment. Raises EditError on a bad range."""
    info = probe(src)
    if start < 0 or end <= start:
        raise EditError("Trim range ghalat hai — end time start se bara hona chahiye.")
    if start >= info["duration"]:
        raise EditError(
            f"Start time video se lamba hai — video sirf {info['duration']:.0f} second ki hai."
        )
    end = min(end, info["duration"])
    _run_ffmpeg([
        "-ss", str(start), "-i", src,
        "-t", str(end - start),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", CRF_720,
        "-c:a", "aac", "-b:a", "96k",
        "-movflags", "+faststart",
        dst,
    ])
    _enforce_size(src, dst)
    return dst


def add_text(src: str, dst: str, text: str) -> str:
    """Burn a text line at the bottom centre of the video."""
    if not text.strip():
        raise EditError("Text khaali hai — 'text' ke baad kuch likho.")
    if len(text) > 120:
        raise EditError("Text bohat lamba hai — 120 harf se kam rakho.")
    _run_ffmpeg([
        "-i", src,
        "-vf", _drawtext_filter(text),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", CRF_720,
        "-c:a", "copy",
        "-movflags", "+faststart",
        dst,
    ])
    _enforce_size(src, dst)
    return dst


def add_brand(src: str, dst: str) -> str:
    """Tk PowerHub text watermark, top-right corner."""
    _run_ffmpeg([
        "-i", src,
        "-vf",
        f"drawtext=fontfile={FONT_PATH}:text='{BRAND_TEXT}':"
        "fontsize=44:fontcolor=gold:borderw=2:bordercolor=black:"
        "x=w-text_w-30:y=30",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", CRF_720,
        "-c:a", "copy",
        "-movflags", "+faststart",
        dst,
    ])
    _enforce_size(src, dst)
    return dst


def _enforce_size(src: str, dst: str) -> None:
    """If the output is over WhatsApp's 16 MB cap, re-encode smaller once."""
    if file_size_mb(dst) <= MAX_RETURN_MB:
        return
    tmp = dst + ".small.mp4"
    _run_ffmpeg([
        "-i", dst,
        "-vf", "scale=720:-2",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "28",
        "-maxrate", "900k", "-bufsize", "1800k",
        "-c:a", "aac", "-b:a", "64k",
        "-movflags", "+faststart",
        tmp,
    ])
    os.replace(tmp, dst)
    if file_size_mb(dst) > MAX_RETURN_MB:
        raise EditError(
            f"Video abhi bhi {file_size_mb(dst):.1f} MB hai — "
            "WhatsApp 16 MB se bara video nahi bhejta. Pehle 'trim' se chhota hissa bhejo."
        )
