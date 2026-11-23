"""Video/audio encoder settings shared by every render.

Final encodes use a hardware H.264 encoder when one is present *and* works (a 0.2 s test encode),
else libx264 -preset veryfast. All targets: CRF/CQ 22, maxrate 6M / bufsize 12M, yuv420p, High profile,
30 fps, keyframe every 2 s, +faststart; audio AAC 160 kbps 48 kHz.
"""
from __future__ import annotations

import os
import subprocess
from functools import lru_cache

from .common import info

FPS = 30
GOP = 2 * FPS                       # keyframe every 2 s
QUALITY = 22
MAXRATE, BUFSIZE = "6M", "12M"
AUDIO = ["-c:a", "aac", "-b:a", "160k", "-ar", "48000"]
FASTSTART = ["-movflags", "+faststart"]

_COMMON = ["-pix_fmt", "yuv420p", "-profile:v", "high", "-g", str(GOP), "-keyint_min", str(GOP),
           "-maxrate", MAXRATE, "-bufsize", BUFSIZE]
CANDIDATES = {
    "h264_nvenc": ["-c:v", "h264_nvenc", "-preset", "p4", "-rc", "vbr", "-cq", str(QUALITY), "-b:v", "0",
                   "-bf", "2", *_COMMON],
    "h264_qsv": ["-c:v", "h264_qsv", "-preset", "veryfast", "-global_quality", str(QUALITY), "-look_ahead", "0",
                 *_COMMON],
    "h264_amf": ["-c:v", "h264_amf", "-quality", "speed", "-rc", "qvbr", "-qvbr_quality_level", str(QUALITY),
                 *_COMMON],
    "libx264": ["-c:v", "libx264", "-preset", "veryfast", "-crf", str(QUALITY), "-sc_threshold", "0", *_COMMON],
}


def _works(name: str) -> bool:
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-f", "lavfi", "-i",
           f"color=c=gray:s=640x360:r={FPS}:d=0.2", *CANDIDATES[name], "-f", "null", "-"]
    try:
        return subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


@lru_cache(maxsize=1)
def encoder() -> str:
    """First working encoder. HORROR_ENCODER=libx264 (or another name) forces one."""
    forced = os.environ.get("HORROR_ENCODER", "").strip()
    if forced in CANDIDATES:
        return forced
    for name in ("h264_nvenc", "h264_qsv", "h264_amf"):
        if _works(name):
            info(f"Encoder: {name} (hardware)")
            return name
    info("Encoder: libx264 -preset veryfast (tidak ada encoder hardware yang jalan)")
    return "libx264"


def video_args() -> list[str]:
    """Final-quality video encode arguments (without -r / output path)."""
    return list(CANDIDATES[encoder()])


def clip_args(threads: int = 2) -> list[str]:
    """Intermediate shot clips: always libx264 (parallel CPU jobs, near-lossless, keyframe every 2 s)."""
    return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-pix_fmt", "yuv420p",
            "-g", str(GOP), "-threads", str(threads)]


def workers() -> int:
    return max(1, (os.cpu_count() or 2) - 1)
