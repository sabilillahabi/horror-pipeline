"""Pillow helpers: crops, cards, vertical composites, subtitles, placeholders, vignette."""
from __future__ import annotations

import random
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

from .common import find_font, find_serif_font

# crop name -> (fraction of frame size, default focus x, default focus y)
# closeup_face: 50% box, horizontally centred, touching the top edge (focus y is clamped)
# detail:       40% box in the exact centre
CROP_SPECS = {
    "wide": (1.0, 0.5, 0.5),
    "medium": (0.72, 0.5, 0.48),   # internal: alternate crop for long beats
    "closeup_face": (0.50, 0.5, 0.25),
    "detail": (0.40, 0.5, 0.5),
}


def font(story_cfg: dict, size: int, key: str = "font") -> ImageFont.FreeTypeFont:
    path = find_font(story_cfg, key)
    if path:
        return ImageFont.truetype(path, size)
    return ImageFont.load_default(size)


def load_rgb(path: Path) -> Image.Image:
    img = Image.open(path)
    img = ImageOps.exif_transpose(img)
    return img.convert("RGB")


def cover(img: Image.Image, w: int, h: int, focus=(0.5, 0.5)) -> Image.Image:
    """Scale to fill w×h and crop around focus point."""
    return ImageOps.fit(img, (w, h), Image.LANCZOS, centering=focus)


def crop_region(img: Image.Image, crop: str, focus=None, shift: float = 0.0,
                aspect: float = 16 / 9) -> Image.Image:
    """Cut a region of `aspect` from the image. shift moves the crop centre horizontally."""
    frac, fx, fy = CROP_SPECS.get(crop, CROP_SPECS["wide"])
    if focus:
        fx, fy = focus
    fx = fx + shift
    W, H = img.size
    # largest `aspect` box that fits inside the image
    bw, bh = (W, W / aspect) if W / H <= aspect else (H * aspect, H)
    cw, ch = bw * frac, bh * frac
    cx = min(max(fx * W, cw / 2), W - cw / 2)
    cy = min(max(fy * H, ch / 2), H - ch / 2)
    box = (int(cx - cw / 2), int(cy - ch / 2), int(cx + cw / 2), int(cy + ch / 2))
    return img.crop(box)


def wrap_px(text: str, fnt, max_w: int) -> list[str]:
    lines = []
    for para in text.split("\n"):
        words, cur = para.split(), ""
        for w in words:
            trial = f"{cur} {w}".strip()
            if cur and fnt.getlength(trial) > max_w:
                lines.append(cur)
                cur = w
            else:
                cur = trial
        lines.append(cur)
    return lines


def draw_centered(draw: ImageDraw.ImageDraw, lines, fnt, W: int, cy: float, fill, spacing=1.18,
                  stroke=0, stroke_fill="black", shadow=False):
    asc, desc = fnt.getmetrics()
    lh = (asc + desc) * spacing
    y = cy - lh * len(lines) / 2
    for ln in lines:
        x = (W - fnt.getlength(ln)) / 2
        if shadow:
            off = max(2, int(fnt.size * 0.06))
            draw.text((x + off, y + off), ln, font=fnt, fill=(0, 0, 0, 160),
                      stroke_width=stroke, stroke_fill=(0, 0, 0, 160))
        draw.text((x, y), ln, font=fnt, fill=fill, stroke_width=stroke, stroke_fill=stroke_fill)
        y += lh
    return y


def chapter_card(story_cfg: dict, top: str, title: str, W: int, H: int) -> Image.Image:
    img = Image.new("RGB", (W, H), "black")
    d = ImageDraw.Draw(img)
    s = W / 1920
    f_top = font(story_cfg, int(34 * s))
    f_title = font(story_cfg, int(96 * s))
    lines = wrap_px(title.upper(), f_title, int(W * 0.8))
    d.text(((W - f_top.getlength(top)) / 2, H * 0.36), top, font=f_top, fill=(170, 170, 170))
    lw = int(W * 0.06)
    d.line([(W / 2 - lw, H * 0.43), (W / 2 + lw, H * 0.43)], fill=(150, 20, 20), width=max(2, int(3 * s)))
    draw_centered(d, lines, f_title, W, H * 0.55, "white")
    return img


def text_card(story_cfg: dict, text: str, W: int, H: int, size: int | None = None) -> Image.Image:
    """White serif text, centred and wrapped, on pure black."""
    img = Image.new("RGB", (W, H), (0, 0, 0))
    d = ImageDraw.Draw(img)
    landscape = W > H
    size = size or int(64 * W / 1920 if landscape else 72 * W / 1080)
    path = find_serif_font(story_cfg)
    fnt = ImageFont.truetype(path, size) if path else ImageFont.load_default(size)
    max_w = int(W * (0.70 if landscape else 0.82))
    lines = wrap_px(" ".join(str(text).split()), fnt, max_w)
    while len(lines) > 6 and size > 20:  # very long card text: shrink to fit
        size = int(size * 0.9)
        fnt = ImageFont.truetype(path, size) if path else ImageFont.load_default(size)
        lines = wrap_px(" ".join(str(text).split()), fnt, max_w)
    draw_centered(d, lines, fnt, W, H / 2, (255, 255, 255), spacing=1.35)
    return img


def vignette(img: Image.Image, strength: float = 0.6) -> Image.Image:
    """Darken edges with a radial gradient."""
    W, H = img.size
    small = Image.new("L", (256, 256), 0)
    px = small.load()
    for y in range(256):
        for x in range(256):
            dx, dy = (x - 127.5) / 127.5, (y - 127.5) / 127.5
            r = min(1.0, (dx * dx + dy * dy) ** 0.5 / 1.25)
            px[x, y] = int(255 * (r ** 2.2) * strength)
    mask = small.resize((W, H), Image.BICUBIC).filter(ImageFilter.GaussianBlur(W / 80))
    black = Image.new("RGB", (W, H), "black")
    return Image.composite(black, img, mask)


def vertical_composite(src: Image.Image, W: int, H: int, fg_scale: float = 1.15) -> Image.Image:
    """16:9 picture centred on a blurred, darkened copy of itself (for 9:16 shorts)."""
    bg = cover(src, max(1, W // 8), max(1, H // 8)).filter(ImageFilter.GaussianBlur(4))
    bg = bg.resize((W, H), Image.BICUBIC)
    bg = ImageEnhance.Brightness(bg).enhance(0.45)
    fw = int(W * fg_scale)
    fh = int(fw * src.height / src.width)
    fg = src.resize((fw, fh), Image.LANCZOS)
    if fw > W:
        fg = fg.crop(((fw - W) // 2, 0, (fw - W) // 2 + W, fh))
    out = bg.copy()
    y = int(H * 0.5 - fh / 2 - H * 0.04)
    out.paste(fg, ((W - fg.width) // 2, y))
    # soft fade at the picture's top/bottom edges
    edge = Image.new("L", (W, fh), 255)
    ed = ImageDraw.Draw(edge)
    fade = max(1, int(fh * 0.08))
    for i in range(fade):
        a = int(255 * i / fade)
        ed.line([(0, i), (W, i)], fill=a)
        ed.line([(0, fh - 1 - i), (W, fh - 1 - i)], fill=a)
    region = bg.crop((0, y, W, y + fh))
    pic = out.crop((0, y, W, y + fh))
    out.paste(Image.composite(pic, region, edge), (0, y))
    return out


def subtitle_png(story_cfg: dict, text: str, W: int, H: int, cy: float, size: int,
                 color=(255, 255, 255), highlight=None) -> Image.Image:
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    fnt = font(story_cfg, size, "subtitle_font")
    lines = wrap_px(text, fnt, int(W * 0.86))
    draw_centered(d, lines, fnt, W, cy, color, spacing=1.12, stroke=max(3, size // 11),
                  stroke_fill=(0, 0, 0, 255), shadow=True)
    return img


def placeholder(path: Path, key: str, scene: str, chars: list, W=1920, H=1080) -> None:
    rnd = random.Random(key)
    base = (rnd.randint(10, 35), rnd.randint(10, 30), rnd.randint(15, 40))
    img = Image.new("RGB", (W, H), base)
    d = ImageDraw.Draw(img)
    for _ in range(40):  # random dark blobs for something to Ken-Burns over
        x, y, r = rnd.randint(0, W), rnd.randint(0, H), rnd.randint(60, 380)
        c = tuple(min(255, v + rnd.randint(0, 45)) for v in base)
        d.ellipse([x - r, y - r, x + r, y + r], fill=c)
    img = img.filter(ImageFilter.GaussianBlur(40))
    img = vignette(img, 0.8)
    d = ImageDraw.Draw(img)
    big = font({}, 150)
    small = font({}, 40)
    d.text((W / 2 - big.getlength(key.upper()) / 2, H * 0.22), key.upper(), font=big, fill=(200, 40, 40))
    desc = textwrap.fill(scene or "(tanpa deskripsi scene)", 70)
    d.multiline_text((W / 2, H * 0.6), desc, font=small, fill=(210, 210, 210), anchor="mm", align="center")
    if chars:
        tag = "  |  ".join(n + (f" ({', '.join(x for x in (p, v) if x)})" if (p or v) else "")
                           for n, p, v in chars)
        d.text((W / 2 - small.getlength(tag) / 2, H * 0.85), tag, font=small, fill=(150, 150, 150))
    # face-ish marker in the closeup region so crops are visibly different
    d.ellipse([W * 0.47, H * 0.28, W * 0.53, H * 0.42], outline=(120, 120, 120), width=4)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)


def reference_placeholder(path: Path, name: str, block: str) -> None:
    W, H = 1024, 1024
    img = Image.new("RGB", (W, H), (25, 25, 30))
    d = ImageDraw.Draw(img)
    d.ellipse([W * 0.35, H * 0.15, W * 0.65, H * 0.48], fill=(70, 70, 80))
    d.rounded_rectangle([W * 0.25, H * 0.5, W * 0.75, H * 0.95], 60, fill=(55, 55, 65))
    f = font({}, 70)
    d.text((W / 2, H * 0.08), name.upper(), font=f, fill="white", anchor="mm")
    d.multiline_text((W / 2, H * 0.72), textwrap.fill(block, 40), font=font({}, 26),
                     fill=(200, 200, 200), anchor="mm", align="center")
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
