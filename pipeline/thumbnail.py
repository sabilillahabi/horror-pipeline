"""`thumbnail` command: 1280x720 high-contrast thumbnail from a beat image."""
from __future__ import annotations

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

from .common import ROOT, Episode, PipelineError, ok, step
from . import visuals as V

W, H = 1280, 720


def _layout(words: list[str]) -> list[list[str]]:
    if len(words) <= 2:
        return [words] if sum(len(w) for w in words) <= 9 else [[w] for w in words]
    best, score = None, 10**9
    for i in range(1, len(words)):
        a, b = words[:i], words[i:]
        s = abs(len(" ".join(a)) - len(" ".join(b)))
        if s < score:
            best, score = [a, b], s
    return best


def cmd_thumbnail(ep: Episode, args) -> None:
    step(f"Thumbnail {ep.slug} {ep.ep}")
    from . import thumbs
    imported = thumbs.path(ep, "16x9")
    if imported.exists() and not args.generate:
        ok(f"Thumbnail dari Flow dipakai: {imported.relative_to(ROOT)} (buat dari beat: --generate)")
        return
    # fallback: script.yaml `thumbnail: {beat, text}`, overridable from the command line
    fb = ep.script.get("thumbnail") or {}
    args.beat = args.beat or fb.get("beat")
    args.text = args.text or fb.get("text")
    if not args.beat or not args.text:
        raise PipelineError("Tidak ada thumbnail dari Flow dan tidak ada `thumbnail: {beat, text}` di script.yaml "
                            "(atau --beat/--text).")
    words = args.text.upper().split()
    if not words:
        raise PipelineError("--text kosong.")
    if len(words) > 4:
        raise PipelineError(f"Teks thumbnail maksimal 4 kata (dapat {len(words)}: '{args.text}').")
    b = ep.get_beat(args.beat)
    src = ep.image_for(b)
    if not src:
        raise PipelineError(f"Gambar untuk beat {b.id} belum ada.")
    crop = args.crop or b.crop
    img = V.crop_region(V.load_rgb(src), crop, b.focus)
    img = V.cover(img, W, H)
    img = ImageEnhance.Contrast(img).enhance(1.3)
    img = ImageEnhance.Color(img).enhance(0.85)
    img = ImageEnhance.Sharpness(img).enhance(1.4)
    img = V.vignette(img, 0.85)

    pos = args.position
    # extra darkening behind the text for legibility
    shade = Image.new("L", (W, H), 0)
    sd = ImageDraw.Draw(shade)
    for i in range(W if pos in ("left", "right") else H):
        if pos == "left":
            a = max(0, 200 - int(200 * i / (W * 0.62)))
            sd.line([(i, 0), (i, H)], fill=a)
        elif pos == "right":
            a = max(0, 200 - int(200 * i / (W * 0.62)))
            sd.line([(W - 1 - i, 0), (W - 1 - i, H)], fill=a)
        elif pos == "bottom":
            a = max(0, 210 - int(210 * i / (H * 0.55)))
            sd.line([(0, H - 1 - i), (W, H - 1 - i)], fill=a)
        elif pos == "top":
            a = max(0, 210 - int(210 * i / (H * 0.55)))
            sd.line([(0, i), (W, i)], fill=a)
    img = Image.composite(Image.new("RGB", (W, H), "black"), img, shade.filter(ImageFilter.GaussianBlur(8)))

    lines = [" ".join(l) for l in _layout(words)]
    box_w = W * (0.56 if pos in ("left", "right") else 0.9)
    box_h = H * (0.75 if pos in ("left", "right", "center") else 0.45)
    size = 260
    while size > 40:
        fnt = V.font(ep.story, size)
        asc, desc = fnt.getmetrics()
        lh = (asc + desc) * 0.98
        if max(fnt.getlength(l) for l in lines) <= box_w and lh * len(lines) <= box_h:
            break
        size -= 4
    stroke = max(4, size // 12)
    total_h = lh * len(lines)
    if pos in ("left", "right", "center"):
        y = (H - total_h) / 2
    elif pos == "bottom":
        y = H - total_h - H * 0.07
    else:
        y = H * 0.07
    d = ImageDraw.Draw(img)
    colors = [args.color, args.accent]
    for i, ln in enumerate(lines):
        lw = fnt.getlength(ln)
        x = {"left": W * 0.05, "right": W * 0.95 - lw}.get(pos, (W - lw) / 2)
        fill = colors[-1] if (i == len(lines) - 1 and len(lines) > 1) else colors[0]
        d.text((x + size * 0.05, y + size * 0.06), ln, font=fnt, fill=(0, 0, 0),
               stroke_width=stroke, stroke_fill=(0, 0, 0))
        d.text((x, y), ln, font=fnt, fill=fill, stroke_width=stroke, stroke_fill=(0, 0, 0))
        y += lh
    out = ep.output / (args.out or f"thumbnail_{ep.ep}.png")
    img.save(out)
    ok(f"Thumbnail: {out.relative_to(ROOT)}")
