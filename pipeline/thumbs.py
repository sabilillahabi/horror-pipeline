"""Imported episode thumbnails: thumb_epXX_16x9 / thumb_epXX_9x16 from Flow → episodes/epXX/thumbnail/."""
from __future__ import annotations

import io
import os
import re
import shutil
from pathlib import Path

from PIL import Image

from .common import IMAGE_EXTS, Episode, atomic_out, info, warn
from . import visuals as V

# thumb_ep01_16x9, [thumb_ep01_9x16]_ab12cd34_2K (1).jpg, thumb-ep1-16x9-2K.png ...
THUMB_RE = re.compile(r"thumb[\s_-]*ep\s*0*(\d+)[\s_-]*(16x9|9x16)", re.I)
SIZES = {"16x9": (1280, 720), "9x16": (1080, 1920)}
MAX_16x9 = 2 * 1024 * 1024 - 64 * 1024   # YouTube limit is 2 MB; keep a margin


def match(name: str) -> tuple[int, str] | None:
    m = THUMB_RE.search(name)
    return (int(m.group(1)), m.group(2).lower()) if m else None


def path(ep: Episode, ratio: str) -> Path:
    return ep.dir / "thumbnail" / f"thumbnail_{ratio}.jpg"


def existing(ep: Episode) -> dict[str, Path]:
    return {r: path(ep, r) for r in SIZES if path(ep, r).exists()}


def install(src: Path, ep: Episode, ratio: str) -> Path:
    """Cover-crop to the exact size and save as JPEG (16:9 kept under 2 MB)."""
    w, h = SIZES[ratio]
    img = V.cover(V.load_rgb(src), w, h)
    dst = path(ep, ratio)
    dst.parent.mkdir(parents=True, exist_ok=True)
    q = 92
    while True:
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=q, optimize=True, progressive=True)
        if ratio != "16x9" or buf.tell() <= MAX_16x9 or q <= 60:
            break
        q -= 4
    tmp = atomic_out(dst)
    tmp.write_bytes(buf.getvalue())
    os.replace(tmp, dst)
    return dst


def import_from(files: list[Path], ep: Episode) -> list[str]:
    """Install the newest thumb_ep<N>_<ratio> file of each ratio among `files`. Returns log lines."""
    best: dict[str, Path] = {}
    for f in files:
        mt = match(f.stem)
        if not mt or mt[0] != ep.number or f.suffix.lower() not in IMAGE_EXTS:
            continue
        r = mt[1]
        if r not in best or f.stat().st_mtime > best[r].stat().st_mtime:
            best[r] = f
    out = []
    for r, f in sorted(best.items()):
        dst = install(f, ep, r)
        with Image.open(dst) as im:
            size = im.size
        out.append(f"{f.name}  →  thumbnail/{dst.name}  ({size[0]}x{size[1]}, {dst.stat().st_size / 1e6:.2f} MB)")
    return out


def cover_copy(ep: Episode, video: Path) -> Path | None:
    """Vertical outputs: thumbnail_9x16.jpg next to the video (<name>_cover.jpg) and embedded as cover art."""
    src = path(ep, "9x16")
    if not src.exists():
        return None
    dst = video.with_name(video.stem + "_cover.jpg")
    shutil.copy2(src, dst)
    from .common import run
    tmp = atomic_out(video)
    run(["ffmpeg", "-y", "-i", video, "-i", src, "-map", "0", "-map", "1", "-c", "copy",
         "-disposition:v:1", "attached_pic", "-movflags", "+faststart", tmp], f"cover {video.name}")
    os.replace(tmp, video)
    return dst
