"""Channel intro/outro: a whispered tagline (Gemini TTS, generated once per channel) over a
black card with the tagline and signature. Used by `build` when story.yaml has `channel: <slug>`."""
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .common import (ROOT, SAMPLE_RATE, Episode, PipelineError, atomic_out, info, ok, probe_duration,
                     quantize, run, sha, step, warn)
from .timeline import Segment

CHANNELS = ROOT / "channels"
ROLES = ("intro", "outro")
LEAD = 0.5         # silence before the whisper starts (text is fading in meanwhile)
TEXT_TAIL = 1.5    # text stays this much longer than the voice clip (incl. its 0.8 s fade-out)
FADE = 0.8         # text fade in / out
OUTRO_BLACK = 1.0  # silent black after the outro text is gone
TARGET_LUFS = -16.0
TARGET_TP = -3.0  # limiter ceiling; whisper breaths overshoot in true peak
FX_VERSION = 3
TAGLINE_WIDTH = 0.66     # widest tagline line as a share of frame width
TAGLINE_WIDTH_VERTICAL = 0.86  # same on 9:16 (phone screens need bigger text)
SIGNATURE_RATIO = 0.74   # signature size relative to the tagline
FX = {
    "intro": "",
    # light reverb tail; pad first so the tail is not cut off
    "outro": "apad=pad_dur=1.4,aecho=0.8:0.6:70|130|210:0.22|0.13|0.07",
}
FONT_FALLBACKS = {
    "italic": ["georgiai.ttf", "timesi.ttf", "DejaVuSerif-Italic.ttf", "LiberationSerif-Italic.ttf"],
    "bold": ["georgiab.ttf", "timesbd.ttf", "DejaVuSerif-Bold.ttf", "LiberationSerif-Bold.ttf"],
}


class Channel:
    def __init__(self, slug: str):
        self.slug = slug
        path = CHANNELS / f"{slug}.yaml"
        if not path.exists():
            raise PipelineError(f"Channel '{slug}' tidak ada: {path.relative_to(ROOT)}")
        import yaml
        self.cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for k in ("tagline", "signature", "voice", "intro_style", "outro_style"):
            if not str(self.cfg.get(k) or "").strip():
                raise PipelineError(f"{path.relative_to(ROOT)}: '{k}' belum diisi")
        self.tagline = str(self.cfg["tagline"]).strip()
        self.signature = str(self.cfg["signature"]).strip()
        self.audio = CHANNELS / slug / "audio"
        self.raw = self.audio / "raw"

    def clip(self, role: str) -> Path:
        return self.audio / f"{role}.wav"

    def missing(self) -> list[str]:
        return [r for r in ROLES if not self.clip(r).exists()]

    # ------------------------------------------------------------- timeline
    def segment(self, role: str, fps: int) -> Segment:
        p = self.clip(role)
        if not p.exists():
            raise PipelineError(f"Klip {role} channel belum ada ({p.relative_to(ROOT)}).\n"
                                f"  Jalankan dulu: channel-tts <story> <ep>  (atau tts, yang juga membuatnya)")
        d = probe_duration(p)
        text_dur = quantize(d + TEXT_TAIL, fps)  # on screen: voice length + 1.5 s
        slot = text_dur + (OUTRO_BLACK if role == "outro" else 0.0)
        # no subtitle text: the tagline is already on screen
        return Segment(role, quantize(slot, fps), p, d, text="", lead=LEAD,
                       card={"text_dur": text_dur, **self.card_cfg()})

    def card_cfg(self) -> dict:
        # `layout` is part of the clip cache key: bump it whenever card_image() changes
        return {"layout": f"2:{TAGLINE_WIDTH}:{SIGNATURE_RATIO}", "tagline": self.tagline, "signature": self.signature,
                "color": str(self.cfg.get("text_color") or "#E8E2D6"),
                "tagline_font": _font_path(self.cfg.get("tagline_font"), "italic"),
                "signature_font": _font_path(self.cfg.get("signature_font"), "bold")}


def for_episode(ep: Episode) -> Channel | None:
    slug = ep.story.get("channel")
    return Channel(str(slug)) if slug else None


# ------------------------------------------------------------------ visual
def _font_path(given, style: str) -> str | None:
    if given:
        for cand in (Path(given), ROOT / given, ROOT / "assets" / "fonts" / given):
            if cand.exists():
                return str(cand)
        warn(f"Font '{given}' tidak ditemukan, pakai serif sistem.")
    from . import fonts
    return fonts.path("serif_italic" if style == "italic" else "serif_bold")


def card_image(card: dict, W: int, H: int) -> Image.Image:
    from .visuals import wrap_px
    img = Image.new("RGB", (W, H), (0, 0, 0))
    d = ImageDraw.Draw(img)
    s = W / 1920

    def ft(path, size):
        return ImageFont.truetype(path, size) if path else ImageFont.load_default(size)

    # one sentence per line; size the tagline so its widest line spans TAGLINE_WIDTH of the frame
    lines = [x.strip() for x in re.split(r"(?<=[.!?…])\s+", card["tagline"]) if x.strip()]
    ref = ft(card["tagline_font"], 100)
    widest = max(ref.getlength(ln) for ln in lines) or 1
    share = TAGLINE_WIDTH_VERTICAL if H > W else TAGLINE_WIDTH
    size = max(12, min(int(150 * max(s, 0.75)), int(100 * share * W / widest)))
    f1 = ft(card["tagline_font"], size)
    f2 = ft(card["signature_font"], int(size * SIGNATURE_RATIO))
    if f1.getlength(max(lines, key=f1.getlength)) > W * 0.9:  # a very long single sentence: wrap
        lines = wrap_px(card["tagline"], f1, int(W * share))
    a1, d1 = f1.getmetrics()
    a2, d2 = f2.getmetrics()
    lh1 = (a1 + d1) * 1.25
    gap = 0.75 * f1.size
    block = lh1 * len(lines) + gap + (a2 + d2)
    y = (H - block) / 2
    for ln in lines:
        d.text(((W - f1.getlength(ln)) / 2, y), ln, font=f1, fill=card["color"])
        y += lh1
    y += gap
    d.text(((W - f2.getlength(card["signature"])) / 2, y), card["signature"], font=f2, fill=card["color"])
    return img


# ------------------------------------------------------------------ watermark
WM_VERSION = 1            # part of the video cache key: bump when the watermark look changes
WM_LAYOUT = {             # size, opacity and position per orientation (approved 24 Nov 2026, option A)
    "vertical": {"size": 44, "x": "center", "y": 175},          # just under the "Title · Eps N · Part N/M" label
    "landscape": {"size": 42, "right": 48, "bottom": 40},       # bottom-right corner
}


def watermark(ch: "Channel | None", vertical: bool, out_dir: Path, W: int, H: int):
    """(png name, x, y) of the channel-name watermark, or None (no channel / `watermark: false`).

    Bold serif signature font, channel text colour, ~60% opacity with a soft shadow. The PNG is written to
    out_dir; the caller overlays it in the final encode."""
    if ch is None:
        return None
    cfg = ch.cfg.get("watermark", {})
    if cfg is False:
        return None
    cfg = cfg or {}
    text = str(cfg.get("text") or ch.cfg.get("name") or ch.signature.lstrip("—– ").strip())
    opacity = float(cfg.get("opacity", 0.6))
    lay = WM_LAYOUT["vertical" if vertical else "landscape"]
    size = int(cfg.get("size_vertical" if vertical else "size_landscape", lay["size"]))
    font = ImageFont.truetype(ch.card_cfg()["signature_font"], size) if ch.card_cfg()["signature_font"] \
        else ImageFont.load_default(size)
    from PIL import ImageColor
    rgb = ImageColor.getrgb(str(ch.cfg.get("text_color") or "#E8E2D6"))
    w, h = int(font.getlength(text)) + 12, size + 18
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.text((7, 5), text, font=font, fill=(0, 0, 0, int(255 * opacity * 0.8)))
    d.text((5, 3), text, font=font, fill=(*rgb, int(255 * opacity)))
    from .common import sha
    name = f"wm_{'v' if vertical else 'h'}_{sha([text, opacity, size, WM_VERSION, rgb])}.png"
    out_dir.mkdir(parents=True, exist_ok=True)
    img.save(out_dir / name)
    if vertical:
        x, y = (W - w) // 2, int(lay["y"])
    else:
        x, y = W - w - int(lay["right"]), H - h - int(lay["bottom"])
    return name, x, y


# ------------------------------------------------------------------ audio generation
def _level(src: Path, dst: Path, role: str) -> None:
    """48 kHz mono s16, optional reverb, gain to TARGET_LUFS; a limiter catches breath peaks."""
    pre = ",".join(f for f in (FX[role], f"aresample={SAMPLE_RATE}") if f)
    p = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(src), "-af",
                        f"{pre},loudnorm=I={TARGET_LUFS}:TP={TARGET_TP}:print_format=json", "-f", "null", "-"],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", p.stderr)
    if p.returncode or not m:
        raise PipelineError(f"Ukur loudness {role} gagal:\n{p.stderr[-600:]}")
    meas = json.loads(m.group(0))
    gain = TARGET_LUFS - float(meas["input_i"])
    lim = 10 ** (TARGET_TP / 20)
    tmp = atomic_out(dst)
    run(["ffmpeg", "-y", "-i", src, "-af", f"{pre},volume={gain:.2f}dB,"
         f"alimiter=limit={lim:.3f}:attack=3:release=60:level=false,aformat=sample_fmts=s16:channel_layouts=mono",
         "-ac", "1", "-c:a", "pcm_s16le", tmp], f"proses klip {role}")
    os.replace(tmp, dst)
    info(f"{role}: {float(meas['input_i']):.1f} → {float(meas['input_i']) + gain:.1f} LUFS, "
         f"{probe_duration(dst):.2f}s")


def generate(ep: Episode, ch: Channel, force: bool = False) -> None:
    """Make intro.wav / outro.wav once. Existing clips are kept unless force=True."""
    from . import gemini_tts as G

    todo = [r for r in ROLES if force or not ch.clip(r).exists()]
    # re-process from the cached raw clip if only the effect/level settings changed
    for r in ROLES:
        if r in todo:
            continue
        meta = ch.raw / f"{r}.json"
        if meta.exists() and json.loads(meta.read_text(encoding="utf-8")).get("fx") != FX_VERSION:
            _level(ch.raw / f"{r}.wav", ch.clip(r), r)
            meta.write_text(json.dumps({**json.loads(meta.read_text(encoding="utf-8")), "fx": FX_VERSION},
                                       indent=2, ensure_ascii=False), encoding="utf-8")
    if not todo:
        info(f"Intro/outro channel '{ch.slug}' sudah ada (buat ulang: channel-tts ... --force)")
        return
    step(f"Intro/outro channel '{ch.slug}'  [Gemini · {ch.cfg['voice']}]")
    voice = str(ch.cfg["voice"])
    used = {str((v or {}).get("voice", "")).lower(): k for k, v in (ep.story.get("gemini_voices") or {}).items()}
    if voice.lower() in used:
        raise PipelineError(f"Voice channel '{voice}' juga dipakai karakter '{used[voice.lower()]}' di "
                            "story.yaml. Pilih voice lain untuk channel atau karakter itu.")
    ring = G.KeyRing(G.api_keys())
    try:
        voices = G.fetch_voices(ring.key, ep.cache / "gemini_voices.json")
        v = G._find_voice(voice, voices)
        if v is None:
            import difflib
            fem = [G._vname(x) for x in voices if G._vgender(x) == str(ch.cfg.get("gender", "female")).lower()]
            close = difflib.get_close_matches(voice, fem, n=5, cutoff=0.4)
            raise PipelineError(f"Voice channel '{voice}' tidak ada di katalog Gemini. "
                                f"Pilihan terdekat: {', '.join(close or fem[:8])}")
        want, got = str(ch.cfg.get("gender") or "").lower(), G._vgender(v)
        if want and got and want != got:
            warn(f"Gender voice {voice} = {got}, channel minta {want}")
        info(f"voice → {G._vname(v)} ({got or '?'}, {v.get('description') or '-'})")
        model = str(ch.cfg.get("gemini_model") or ep.story.get("gemini_model") or G.DEFAULT_MODEL)
        ch.raw.mkdir(parents=True, exist_ok=True)
        client = G._client(ring.key)
        for r in todo:
            params = {"model": model, "voice": voice, "language": str(ch.cfg.get("language") or "id-ID"),
                      "style": str(ch.cfg[f"{r}_style"]).strip(), "text": ch.tagline}
            raw = ch.raw / f"{r}.wav"
            while True:
                try:
                    G.synth(client, params, raw)
                    break
                except G.DailyQuota as e:
                    spent = ring.label
                    if not ring.next():
                        raise PipelineError(
                            f"Kuota harian habis di semua {len(ring.keys)} key; klip channel yang belum ada: "
                            f"{', '.join(ch.missing())}. Coba lagi setelah kuota reset (tidak ada fallback "
                            f"ke edge-tts untuk klip channel).\n  {e}")
                    warn(f"Kuota harian {spent} habis → pindah ke {ring.label}")
                    client = G._client(ring.key)
            (ch.raw / f"{r}.json").write_text(json.dumps({**params, "hash": sha(params), "fx": FX_VERSION},
                                                         indent=2, ensure_ascii=False), encoding="utf-8")
            _level(raw, ch.clip(r), r)
            print(f"  {r}.wav  ({voice})", flush=True)
    except PipelineError as e:
        raise PipelineError(ring.scrub(str(e))) from None
    ok(f"Klip channel di {ch.audio.relative_to(ROOT)}")


def cmd_channel_tts(ep: Episode, args) -> None:
    ch = for_episode(ep)
    if ch is None:
        raise PipelineError("story.yaml belum punya `channel: <slug>`")
    generate(ep, ch, force=args.force)


# ------------------------------------------------------------------ final audio
def wrap_audio(story_mix: Path, intro: Segment | None, outro: Segment | None, out: Path) -> None:
    """intro + story mix + outro, each padded to its slot; nothing from the story bleeds across."""
    inputs, parts, labels = [], [], []
    fmt = "aformat=sample_rates=48000:sample_fmts=s16:channel_layouts=stereo"

    def channel_part(seg: Segment, idx: int):
        ms = int(round(seg.lead * 1000))
        parts.append(f"[{idx}:a]{fmt},adelay={ms}|{ms},apad=whole_dur={seg.slot:.4f},"
                     f"atrim=0:{seg.slot:.4f}[c{idx}]")
        labels.append(f"[c{idx}]")

    order = [(intro, "seg"), (story_mix, "mix"), (outro, "seg")]
    for item, kind in order:
        if item is None:
            continue
        idx = len(inputs) // 2
        if kind == "seg":
            inputs += ["-i", item.audio]
            channel_part(item, idx)
        else:
            inputs += ["-i", item]
            parts.append(f"[{idx}:a]{fmt}[c{idx}]")
            labels.append(f"[c{idx}]")
    parts.append("".join(labels) + f"concat=n={len(labels)}:v=0:a=1[a]")
    tmp = atomic_out(out)
    run(["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(parts), "-map", "[a]", "-c:a", "pcm_s16le", tmp],
        "gabung intro/outro")
    try:
        os.replace(tmp, out)
    except PermissionError:
        # another render (e.g. the vertical build) is reading `out`; same timeline → same bytes
        import filecmp
        if out.exists() and filecmp.cmp(tmp, out, shallow=False):
            tmp.unlink()
        else:
            raise
