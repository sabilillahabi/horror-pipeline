"""Per-part IG/FB covers (1080x1920) that reuse the episode thumbnail's exact title lettering.

1. title_epXX.png: the "TITLE" + "EPISODE n" block cut out of thumbnail/thumbnail_9x16.jpg (alpha from
   luminance/colour: cream + white letters and the red glow kept, dark background removed), full 1080x1920
   canvas so it lands in exactly the same place as on the thumbnail. Extracted once per episode.
2. Background per part: the strongest image in that part's time range (SFX hit / character close-up),
   never the same image for two parts, cropped 9:16 like the vertical video, top 40% darkened.
3. "PART n" under "EPISODE n" in a bold condensed sans with a thin shadow.
Output: output/vertical/covers/<name>_partN_cover.jpg (+ copy next to each part, embedded as cover art).
Optional per-part overrides in episodes/epXX/covers.yaml:  part3: {beat: b034}
"""
from __future__ import annotations

import json
import os
import random
import shutil
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from .common import ROOT, Episode, PipelineError, atomic_out, info, ok, run, step, warn
from . import visuals as V

W, H = 1080, 1920
TOP_DARK = 0.40          # share of the height darkened behind the title
SEARCH_H = 0.45          # the title block is looked for in the top 45% of the thumbnail


# ------------------------------------------------------------------ title cut-out
def _sans(size: int):
    """Bold condensed sans for PART n (Bahnschrift Bold Condensed on Windows, Oswald/Bebas/Narrow elsewhere)."""
    from . import fonts
    return fonts.font("condensed_bold", size)


def _text_mask(img: Image.Image) -> Image.Image:
    """255 where a pixel looks like lettering: cream (warm, bright) or near-white."""
    r, g, b = [c.point(lambda v: v) for c in img.split()]
    lum = img.convert("L")
    bright = lum.point(lambda v: 255 if v > 175 else 0)
    # warm cream: red clearly above blue; neutral white: very bright
    warm = ImageChops.subtract(r, b).point(lambda v: 255 if v > 22 else 0)
    white = lum.point(lambda v: 255 if v > 222 else 0)
    return ImageChops.multiply(bright, ImageChops.lighter(warm, white))


def _bands(mask: Image.Image) -> list[tuple[int, int, int, int]]:
    """Text lines as boxes: row bands with lettering, each cut at the first wide horizontal gap."""
    w, h = mask.size
    px = mask.load()
    rows = [sum(1 for x in range(0, w, 2) if px[x, y]) for y in range(h)]
    bands, y = [], 0
    while y < h:
        if rows[y] >= 6:
            y0 = y
            while y < h and rows[y] >= 3:
                y += 1
            if y - y0 >= 30:                       # ignore thin specks
                bands.append((y0, y))
        y += 1
    boxes = []
    for y0, y1 in bands:
        cols = [any(px[x, yy] for yy in range(y0, y1, 2)) for x in range(w)]
        xs = [x for x, c in enumerate(cols) if c]
        if not xs:
            continue
        x0 = xs[0]
        x1, gap = x0, 0
        for x in range(x0, w):                     # stop at the first gap wider than 90 px (moon, hair…)
            if cols[x]:
                x1, gap = x, 0
            else:
                gap += 1
                if gap > 90:
                    break
        boxes.append((x0, y0, x1 + 1, y1))
    return boxes


def extract_title(ep: Episode, force: bool = False) -> Path:
    """thumbnail/title_epXX.png (RGBA, 1080x1920) from thumbnail/thumbnail_9x16.jpg."""
    from . import thumbs
    out = ep.dir / "thumbnail" / f"title_{ep.ep}.png"
    src = thumbs.path(ep, "9x16")
    if out.exists() and not force and (not src.exists() or out.stat().st_mtime >= src.stat().st_mtime):
        return out
    if not src.exists():
        raise PipelineError(f"thumbnail/thumbnail_9x16.jpg belum ada (import thumb_ep{ep.number:02d}_9x16 dulu)")
    img = Image.open(src).convert("RGB")
    if img.size != (W, H):
        img = V.cover(img, W, H)
    top = img.crop((0, 0, W, int(H * SEARCH_H)))
    boxes = _bands(_text_mask(top))
    if len(boxes) < 2:
        raise PipelineError(f"Blok judul tidak terdeteksi di {src.name} ({len(boxes)} baris teks)")
    boxes = boxes[:3]                               # title lines (1-2) + "EPISODE n" line
    region = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(region)
    for i, (x0, y0, x1, y1) in enumerate(boxes):    # room for the red glow round the title lines; EPISODE has none
        m = 8 if i == len(boxes) - 1 else 34
        d.rectangle((x0 - m, y0 - m, x1 + m, y1 + m), fill=255)
    region = region.filter(ImageFilter.GaussianBlur(4))

    r, g, b = img.split()
    lum = img.convert("L")
    letters = lum.point(lambda v: max(0, min(255, (v - 110) * 255 // 70)))          # 110..180 → 0..255
    redness = ImageChops.subtract(r, ImageChops.lighter(g, b))
    glow = redness.point(lambda v: max(0, min(255, (v - 10) * 255 // 55)))         # red halo
    alpha = ImageChops.multiply(ImageChops.lighter(letters, glow), region)
    alpha = alpha.filter(ImageFilter.GaussianBlur(0.8))                             # feather
    # un-mix the dark background from semi-transparent glow pixels so it doesn't go muddy on new art
    rgba = img.copy()
    rgba.putalpha(alpha)
    out.parent.mkdir(parents=True, exist_ok=True)
    rgba.save(out)
    meta = {"source": src.name, "lines": boxes}
    out.with_suffix(".json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    info(f"Judul dipotong dari {src.name}: {len(boxes)} baris {boxes} → thumbnail/{out.name}")
    return out


def _title_lines(ep: Episode) -> list[tuple[int, int, int, int]]:
    p = ep.dir / "thumbnail" / f"title_{ep.ep}.json"
    return json.loads(p.read_text(encoding="utf-8"))["lines"]


# ------------------------------------------------------------------ backgrounds
def _crop_9x16(ep: Episode, b) -> Image.Image:
    from .vertical import crop_plan
    src = ep.image_for(b)
    cp = crop_plan(ep, b, src, 6.0, random.Random(b.key))
    img = V.load_rgb(src).crop(tuple(int(round(v)) for v in cp["box"]))
    x = (cp["x0"] + cp["x1"]) / 2
    ww = img.height * 9 / 16
    x0 = min(max(0, x * img.width - ww / 2), img.width - ww)
    return img.crop((int(x0), 0, int(x0 + ww), img.height)).resize((W, H), Image.LANCZOS)


def _background(ep: Episode, b) -> Image.Image:
    img = ImageEnhance.Contrast(_crop_9x16(ep, b)).enhance(1.05)
    shade = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(shade)
    end = int(H * TOP_DARK)
    for y in range(end):
        d.line([(0, y), (W, y)], fill=int(190 * (1 - y / end) ** 1.4))
    return Image.composite(Image.new("RGB", (W, H), "black"), img, shade)


def _score(ep: Episode, b, sfx: dict) -> float:
    from .threads import TENSE_SFX
    s = 0.0
    if any(k in sfx.get(b.key, "") for k in TENSE_SFX):
        s += 3
    chars = b.chars or (ep.resolve_ref(b.image_from).chars if b.image_from and ep.resolve_ref(b.image_from) else [])
    close = b.crop == "closeup_face" or "close-up" in (b.scene or "").lower()
    if chars and close:
        s += 3
    elif chars:
        s += 1
    if b.crop == "detail":   # a detail crop (hair, hands, objects up close) reads as abstract on a cover
        s -= 2
    return s


def pick_beats(ep: Episode, parts: list[dict], segs) -> dict[int, object]:
    """One beat per part: covers.yaml override, else the strongest image; an image is never used twice."""
    from .threads import _sfx_map
    cfg = _config(ep)
    sfx = _sfx_map(ep)
    used, picks = set(), {}
    for p in parts:
        n = p["n"]
        c = cfg.get(f"part{n}") or {}
        b = ep.resolve_ref(str(c["beat"])) if c.get("beat") else None
        if b is None:
            cands = [s.beat for s in segs if s.kind == "beat" and p["a"] <= s.start < p["b"]
                     and s.beat.visual == "image" and ep.image_for(s.beat)]
            cands = [x for x in cands if ep.image_for(x) not in used]
            if not cands:
                warn(f"Part {n}: tidak ada gambar yang belum dipakai untuk cover")
                continue
            b = max(cands, key=lambda x: (_score(ep, x, sfx), -cands.index(x)))
        picks[n] = b
        used.add(ep.image_for(b))
    return picks


# ------------------------------------------------------------------ compose
def make_cover(ep: Episode, b, n: int, out: Path) -> Path:
    img = _background(ep, b).convert("RGBA")
    title = Image.open(extract_title(ep)).convert("RGBA")
    img.alpha_composite(title)
    lines = _title_lines(ep)
    ex0, ey0, ex1, ey1 = lines[-1]                  # the "EPISODE n" line (last)
    cap = ey1 - ey0                                 # its letter height
    text = f"PART {n}"
    size = int(cap * 1.32)
    f = _sans(size)
    while f.getbbox("PART 0")[3] - f.getbbox("PART 0")[1] > cap * 0.97 and size > 20:
        size -= 2
        f = _sans(size)
    bb = f.getbbox(text)
    x = ex0 - bb[0]
    y = ey1 + int(cap * 0.28) - bb[1]
    shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).text((x + 4, y + 4), text, font=f, fill=(0, 0, 0, 200))
    img.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(3)))
    ImageDraw.Draw(img).text((x, y), text, font=f, fill=(255, 255, 255, 255))
    out.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(out, "JPEG", quality=92, optimize=True)
    return out


def embed(video: Path, cover: Path) -> None:
    """Replace (or add) the cover art stream; video/audio are copied untouched."""
    tmp = atomic_out(video)
    run(["ffmpeg", "-y", "-i", video, "-i", cover, "-map", "0:V", "-map", "0:a", "-map", "1", "-c", "copy",
         "-disposition:v:1", "attached_pic", "-movflags", "+faststart", tmp], f"cover {video.name}")
    os.replace(tmp, video)


def _config(ep: Episode) -> dict:
    p = ep.dir / "covers.yaml"
    if not p.exists():
        return {}
    import yaml
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def contact_sheet(paths: list[Path], labels: list[str], out: Path) -> Path:
    tw, pad = 360, 12
    th = int(tw * H / W)
    sheet = Image.new("RGB", (len(paths) * (tw + pad) + pad, th + 2 * pad + 44), (30, 30, 30))
    d = ImageDraw.Draw(sheet)
    from . import fonts
    f = fonts.font("sans_bold", 22)
    for i, (p, lab) in enumerate(zip(paths, labels)):
        x = pad + i * (tw + pad)
        sheet.paste(Image.open(p).resize((tw, th), Image.LANCZOS), (x, pad))
        d.text((x + 4, pad + th + 10), lab, font=f, fill=(255, 210, 60))
    sheet.save(out)
    return out


def part_covers(ep: Episode, parts: list[dict], segs, outdir: Path, name: str) -> list[Path]:
    """covers/<name>_partN_cover.jpg per part, copied next to the part and embedded in it."""
    extract_title(ep)
    picks = pick_beats(ep, parts, segs)
    cdir = outdir / "covers"
    made, labels = [], []
    for p in parts:
        n = p["n"]
        b = picks.get(n)
        if b is None:
            continue
        cover = make_cover(ep, b, n, cdir / f"{name}_part{n}_cover.jpg")
        side = outdir / f"{name}_part{n}_cover.jpg"
        shutil.copy2(cover, side)
        video = outdir / f"{name}_part{n}.mp4"
        if video.exists():
            embed(video, cover)
        made.append(cover)
        labels.append(f"Part {n}: {b.key} ({ep.image_for(b).name})")
        info(f"Part {n}: cover dari {b.key} ({ep.image_for(b).name})")
    if made:
        contact_sheet(made, labels, cdir / "covers_sheet.png")
    return made


def cmd_covers(ep: Episode, args) -> None:
    """Rebuild part covers and embed them, without re-rendering the parts."""
    step(f"Cover part IG/FB {ep.slug} {ep.ep}")
    if getattr(args, "force", False):
        extract_title(ep, force=True)
    mf = ep.cache / "render_vertical.json"
    if not mf.exists():
        raise PipelineError(f"Belum ada render vertikal penuh. Jalankan dulu: build {ep.slug} {ep.ep} --vertical")
    m = json.loads(mf.read_text(encoding="utf-8"))
    from types import SimpleNamespace
    segs = [SimpleNamespace(kind=s["kind"], start=s["start"],
                            beat=ep.resolve_ref(s["key"]) if s["kind"] == "beat" else None) for s in m["segments"]]
    if m.get("kind") == "vertical_parts":
        outdir, base = Path(m["outdir"]), m["base"]
    else:
        outdir, base = Path(m["output"]).parent, Path(m["output"]).stem
    made = part_covers(ep, m.get("parts") or [], segs, outdir, base)
    ok(f"{len(made)} cover di {(outdir / 'covers').relative_to(ROOT)} + covers_sheet.png")
