"""`build --vertical`: 1080x1920 full-bleed version of the same timeline, audio and sound mix.

Each 16:9 image is cut to a 9:16 window: centred on the character(s) from `characters_in_scene`,
or slowly panned across scenes without characters. Per-beat overrides in script.yaml:
    vertical_crop_x: 0.0-1.0           # window position, 0 = left edge, 1 = right edge
    vertical_pan: left_to_right | right_to_left | none
Outputs (output/vertical/): one file per script part (`parts:` in script.yaml, each <= 2:55) used as-is
for YouTube Shorts, TikTok, IG Reels and FB Reels, part covers and captions.txt; the full vertical
episode only with --full.
"""
from __future__ import annotations

import json
import math
import os
import random
import re
from pathlib import Path

from PIL import Image

from .common import (ROOT, Episode, PipelineError, atomic_out, fmt_ts, info, ok, run,
                     sha, step, warn)
from . import channel as C
from . import thumbs
from . import visuals as V
from .render import TEXT_CARD_FADE, render_clip, save_still, split_slot

W, H = 1080, 1920
POS_X = {"left": 0.30, "center": 0.50, "centre": 0.50, "middle": 0.50, "foreground": 0.50, "right": 0.70,
         "center-left": 0.44, "centre-left": 0.44, "center-right": 0.56, "centre-right": 0.56}


def pos_x(p: str) -> float:
    """Window centre for a `position` value; the first known word wins ("left foreground" → left)."""
    key = p.strip().lower()
    if key in POS_X:
        return POS_X[key]
    for tok in key.replace(",", " ").split():
        if tok in POS_X and tok not in ("foreground",):
            return POS_X[tok]
    return 0.5
VZOOM = 0.08              # Ken Burns zoom inside the crop (horizontal uses ~0.12)
PAN_SPEED = 0.04          # max pan speed, share of image width per second ("slow")
HASHTAGS = "#KemenyanMalam #JuruKunciWringinpitu #ceritahoror #horor"
SUB_FONT, SUB_SIZE, SUB_MAX_W, SUB_MAX_WORDS = "arialbd.ttf", 64, 780, 6   # ~1.8x the horizontal size vs frame width
SUB_MARGIN_V, SUB_MARGIN_L, SUB_MARGIN_R = 380, 150, 150  # centred; bottom 320 px and right 140 px stay clear
LABEL_SIZE, LABEL_MARGIN_V = 40, 120
TENSE_SFX = ("hit", "knock", "impact", "boom", "whoosh")


# ------------------------------------------------------------------ crop planning
def region_box(w: int, h: int, crop: str, focus) -> tuple[float, float, float, float]:
    """The horizontal build's crop region (pixels) — vertical windows are cut from inside it."""
    frac, fx, fy = V.CROP_SPECS.get(crop, V.CROP_SPECS["wide"])
    if focus:
        fx, fy = focus
    aspect = 16 / 9
    bw, bh = (w, w / aspect) if w / h <= aspect else (h * aspect, h)
    cw, ch = bw * frac, bh * frac
    cx = min(max(fx * w, cw / 2), w - cw / 2)
    cy = min(max(fy * h, ch / 2), h - ch / 2)
    return cx - cw / 2, cy - ch / 2, cx + cw / 2, cy + ch / 2


def crop_plan(ep: Episode, b, src: Path, dur: float, rnd: random.Random, aspect: float = 9 / 16) -> dict:
    """{mode: static|pan, x0, x1 (window centre as share of the region width), wf, box, why}"""
    with Image.open(src) as im:
        w, h = im.size
    box = region_box(w, h, b.crop, b.focus)
    rw, rh = box[2] - box[0], box[3] - box[1]
    wf = min(1.0, rh * aspect / rw)                      # window width as share of the region
    lo, hi = wf / 2, 1 - wf / 2
    clamp = lambda x: min(max(x, lo), hi)                # noqa: E731
    to_region = lambda fx: (fx * w - box[0]) / rw         # noqa: E731
    raw = b.raw or {}
    pan = str(raw.get("vertical_pan") or "").strip().lower() or None
    # draw the random pan direction for every character-less beat, even when overridden, so an
    # override never shifts the directions (and clip cache) of the beats after it
    auto_pan = rnd.choice(["left_to_right", "right_to_left"]) if not b.chars else None
    if raw.get("vertical_crop_x") is not None:
        x = lo + float(raw["vertical_crop_x"]) * (hi - lo)
        base, why = x, f"vertical_crop_x={raw['vertical_crop_x']}"
    else:
        # a reused image (`reuse` + crop) has no characters of its own: take the source beat's
        chars = b.chars
        if not chars and b.image_from:
            srcb = ep.resolve_ref(b.image_from)
            chars = srcb.chars if srcb else []
        xs = [(n, pos_x(p)) for n, p, _ in chars]
        # pans are for wide/establishing shots only; a close-up or detail stays put
        close = b.crop in ("closeup_face", "detail") or \
            re.match(r"\s*(extreme\s+)?close[\s-]?up|\s*detail", b.scene or "", re.I)
        if not xs:
            base, why = 0.5, "close-up tanpa karakter" if close else "tanpa karakter"
            pan = pan or (None if close else auto_pan)
        elif len(xs) == 1:
            base, why = to_region(xs[0][1]), f"{xs[0][0]} ({chars[0][1] or 'center'})"
        else:
            pts = [to_region(x) for _, x in xs]
            if max(pts) - min(pts) <= wf * 0.8:
                base, why = (max(pts) + min(pts)) / 2, "di antara " + " & ".join(n for n, _ in xs)
            else:
                sp = next((to_region(x) for n, x in xs if n.lower() == b.speaker.lower()), None)
                base, why = (sp, f"pembicara {b.speaker}") if sp is not None else \
                    ((max(pts) + min(pts)) / 2, "di antara (pembicara tidak di gambar)")
    if pan in ("left_to_right", "right_to_left") and hi > lo:
        span = min(hi - lo, PAN_SPEED * dur * (w / rw))
        a, z = clamp(base - span / 2), clamp(base + span / 2)
        if z - a < span:  # pushed against an edge
            a, z = (lo, lo + span) if a <= lo else (hi - span, hi)
        x0, x1 = (a, z) if pan == "left_to_right" else (z, a)
        return {"mode": "pan", "x0": x0, "x1": x1, "wf": wf, "box": box, "size": (w, h), "why": why}
    x = clamp(base)
    return {"mode": "static", "x0": x, "x1": x, "wf": wf, "box": box, "size": (w, h), "why": why}


def plan(ep: Episode, segs, override: dict | None = None) -> list[dict]:
    """override: {beat key: image beat} — a black/text_card beat in a part's first 3 s is shown as that
    beat's image with a slow push-in instead (vertical only)."""
    r = ep.render
    fps = int(r["fps"])
    rnd = random.Random(f"{ep.slug}-{ep.ep}-vertical")
    shots, flip = [], 0
    override = override or {}
    for s in segs:
        if s.beat is not None and s.beat.key in override:
            ib = override[s.beat.key]
            src = ep.image_for(ib)
            cp = crop_plan(ep, ib, src, s.slot, random.Random(ib.key))
            shots.append({"kind": "image", "slot": s.slot, "src": src, "crop": ib.crop, "focus": ib.focus,
                          "key": s.beat.key, "mode": "static", "box": cp["box"], "wf": cp["wf"],
                          "why": f"3 detik pertama: gambar {ib.key} menggantikan {s.beat.visual}",
                          "size": cp["size"], "x0": cp["x0"], "x1": cp["x0"], "dir": "zoom_in",
                          "zoom": VZOOM * 0.6, "stand_in": ib.key})
            continue
        if s.kind in ("intro", "outro"):
            shots.append({"kind": "channel", "slot": s.slot, "card": s.card, "dir": "static",
                          "fade": C.FADE, "fade_slot": s.card["text_dur"], "key": s.kind})
            continue
        if s.kind in ("lead", "card"):
            shots.append({"kind": "black", "slot": s.slot, "key": s.kind})
            continue
        b = s.beat
        if b is None or b.visual == "black":
            shots.append({"kind": "black", "slot": s.slot, "key": b.key if b else s.kind})
            continue
        if b.visual == "text_card":
            shots.append({"kind": "text", "slot": s.slot, "text": b.card_text or b.text, "dir": "static",
                          "fade": TEXT_CARD_FADE, "key": b.key})
            continue
        src = ep.image_for(b)
        if src is None:
            raise PipelineError(f"Gambar untuk {b.key} tidak ada.")
        cp = crop_plan(ep, b, src, s.slot, rnd)
        k = max(1, math.ceil(s.slot / float(r["max_shot"]) - 1e-6))
        parts = split_slot(s.slot, k, fps)
        t = 0.0
        for j, part in enumerate(parts):
            sh = {"kind": "image", "slot": part, "src": src, "crop": b.crop, "focus": b.focus, "key": b.key,
                  "mode": cp["mode"], "box": cp["box"], "wf": cp["wf"], "why": cp["why"], "size": cp["size"]}
            if cp["mode"] == "pan":  # one continuous pan over the whole beat
                f0, f1 = t / s.slot, (t + part) / s.slot
                sh["x0"] = cp["x0"] + (cp["x1"] - cp["x0"]) * f0
                sh["x1"] = cp["x0"] + (cp["x1"] - cp["x0"]) * f1
                sh["dir"] = "pan"
            else:
                sh["x0"] = sh["x1"] = cp["x0"]
                sh["dir"] = "zoom_in" if flip % 2 == 0 else "zoom_out"
                flip += 1
            shots.append(sh)
            t += part
    return shots


# ------------------------------------------------------------------ rendering
def _region_image(sh: dict) -> Image.Image:
    img = V.load_rgb(sh["src"])
    return img.crop(tuple(int(round(v)) for v in sh["box"]))


def _render_pan(sh: dict, out: Path, dur: float, r: dict, still_dir: Path, h_: str) -> None:
    """Fixed-size 9:16 window sliding across the region (1.5x still, scaled down → smooth)."""
    from .encode import clip_args
    fps = int(r["fps"])
    n = max(1, round(dur * fps))
    sh_h = int(H * 1.5)
    still = still_dir / f"pan_{h_}.jpg"
    if not still.exists():
        reg = _region_image(sh)
        sw = int(round(reg.width * sh_h / reg.height))
        still.parent.mkdir(parents=True, exist_ok=True)
        reg.resize((sw, sh_h), Image.LANCZOS).save(still, quality=93)
    with Image.open(still) as im:
        sw = im.width
    ww = int(round(sh_h * 9 / 16))
    # window centre runs x0 → x1 across the shot's slot, then holds for the crossfade tail
    p = f"min(1,t/{max(0.04, sh['slot']):.3f})"
    e = f"({p}*{p}*(3-2*{p}))"
    cx = f"({sh['x0']:.5f}+({sh['x1'] - sh['x0']:.5f})*{e})"
    x = f"max(0,min({sw - ww},{cx}*{sw}-{ww / 2:.1f}))"
    tmp = atomic_out(out)
    run(["ffmpeg", "-y", "-loop", "1", "-framerate", fps, "-i", still, "-vf",
         f"crop={ww}:{sh_h}:x='{x}':y=0,scale={W}:{H}:flags=lanczos,format=yuv420p",
         "-frames:v", n, "-r", fps, *clip_args(), "-an", tmp], f"pan {out.name}")
    os.replace(tmp, out)


def render(ep: Episode, shots: list[dict], force: bool, label="vclip") -> list[Path]:
    from .render import KB_VERSION, content_hash, run_parallel
    r = ep.render
    D = float(r["crossfade"])
    clip_dir, still_dir = ep.cache / "clips_v", ep.cache / "stills_v"
    clip_dir.mkdir(parents=True, exist_ok=True)
    still_dir.mkdir(parents=True, exist_ok=True)
    paths, jobs = [], []
    for sh in shots:
        dur = sh["slot"] + D
        sig = {k: v for k, v in sh.items() if k not in ("src", "why", "slot", "key")}
        if sh["kind"] == "channel":
            sig["vlayout"] = C.TAGLINE_WIDTH_VERTICAL  # vertical card layout is part of the cache key
        sig.update(img=content_hash(sh.get("src")), dur=round(dur, 4), fps=r["fps"], zoom=sh.get("zoom", VZOOM),
                   v=3, kb=KB_VERSION, serif=V.find_serif_font(ep.story))
        h_ = sha(sig)
        out = clip_dir / f"{label}_{h_}.mp4"
        paths.append(out)
        if out.exists() and not force:
            continue

        def job(sh=sh, out=out, h_=h_, dur=dur):
            if sh["kind"] == "black":
                render_clip(None, out, dur, "static", r, W, H)
            elif sh["kind"] == "image" and sh["mode"] == "pan":
                _render_pan(sh, out, dur, r, still_dir, h_)
            else:
                still = still_dir / f"{h_}.jpg"
                if not still.exists():
                    if sh["kind"] == "image":
                        reg = _region_image(sh)
                        ww = reg.height * 9 / 16
                        x0 = min(max(0, sh["x0"] * reg.width - ww / 2), reg.width - ww)
                        img = reg.crop((int(x0), 0, int(x0 + ww), reg.height))
                    elif sh["kind"] == "text":
                        img = V.text_card(ep.story, sh["text"], int(W * 1.5), int(H * 1.5))
                    else:  # channel outro (full vertical only)
                        img = C.card_image(sh["card"], int(W * 1.5), int(H * 1.5))
                    save_still(img, still, W, H)
                render_clip(still, out, dur, sh.get("dir", "static"), r, W, H,
                            zoom=sh.get("zoom", VZOOM) if sh["kind"] == "image" else None,
                            fade=sh.get("fade", 0.0), slot=sh.get("fade_slot", sh["slot"]))
        jobs.append(job)
    info(f"{len(jobs)} klip vertikal dirender, {len(shots) - len(jobs)} dari cache")
    run_parallel(jobs, label)
    return paths


# ------------------------------------------------------------------ subtitles (ASS)
def _font():
    from . import fonts  # Arial Bold on Windows, Liberation/DejaVu Sans Bold on Linux
    return fonts.font("sans_bold", SUB_SIZE)


def _split2(words: list[str], fnt) -> tuple[list[str], float] | None:
    """Best 2-line (or 1-line) layout of `words`; None if it can't fit. Prefers breaks after commas."""
    def fits(ws):
        return len(ws) <= SUB_MAX_WORDS and fnt.getlength(" ".join(ws)) <= SUB_MAX_W
    if fits(words):
        return [" ".join(words)], 0.0
    best = None
    for i in range(1, len(words)):
        a, b = words[:i], words[i:]
        if not (fits(a) and fits(b)):
            continue
        wa, wb = fnt.getlength(" ".join(a)), fnt.getlength(" ".join(b))
        cost = abs(wa - wb) - (250 if a[-1].endswith((",", ";", ":", "—")) else 0)
        if len(b) == 1 or len(a) == 1:
            cost += 300  # no lonely words
        if best is None or cost < best[1]:
            best = ([" ".join(a), " ".join(b)], cost)
    return best


def cues(segs) -> list[tuple[float, float, str]]:
    """≤ 2 balanced lines per cue (≤ SUB_MAX_WORDS words, ≤ SUB_MAX_W px each); sentences kept apart."""
    fnt = _font()
    out = []
    for s in segs:
        if not s.text or not s.audio_dur:
            continue
        groups = []
        for sent in re.split(r"(?<=[.!?…])\s+", " ".join(s.text.split())):
            words = sent.split(" ")
            # fewest cues that fit, then the most even lengths; breaking after punctuation is cheaper
            n = len(words)
            best = [(0, 0.0, -1)] + [(10**6, 0.0, -1)] * n
            for j in range(1, n + 1):
                for i in range(j - 1, -1, -1):
                    if _split2(words[i:j], fnt) is None:
                        if j - i > 1:
                            break
                        continue
                    L = len(" ".join(words[i:j]))
                    c = best[i][1] + L * L - (400 if i and words[i - 1].endswith((",", ";", ":", "—", "...")) else 0)
                    cand = (best[i][0] + 1, c, i)
                    if cand[:2] < best[j][:2]:
                        best[j] = cand
            cuts, j = [], n
            while j > 0:
                i = best[j][2] if best[j][2] >= 0 else j - 1
                cuts.append((i, j))
                j = i
            for i, j in reversed(cuts):
                lay = _split2(words[i:j], fnt)
                groups.append(lay[0] if lay else [" ".join(words[i:j])])
        total = sum(len(" ".join(g)) for g in groups) or 1
        t = s.start + s.lead
        for g in groups:
            d = s.audio_dur * len(" ".join(g)) / total
            out.append((t, t + d, "\\N".join(g)))
            t += d
    return out


def _ass_ts(t: float) -> str:
    t = max(0.0, t)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def write_ass(path: Path, cue_list, label: str, total: float) -> None:
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sub,Arial,{SUB_SIZE},&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,5,1.5,2,{SUB_MARGIN_L},{SUB_MARGIN_R},{SUB_MARGIN_V},1
Style: Label,Arial,{LABEL_SIZE},&H20E8E2D6,&H20E8E2D6,&H00000000,&H00000000,0,0,0,0,100,100,1,0,1,2,0,8,150,150,{LABEL_MARGIN_V},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev = [f"Dialogue: 1,{_ass_ts(0)},{_ass_ts(total)},Label,,0,0,0,,{label}"]
    ev += [f"Dialogue: 0,{_ass_ts(a)},{_ass_ts(b)},Sub,,0,0,0,,{t}" for a, b, t in cue_list]
    path.write_text(head + "\n".join(ev) + "\n", encoding="utf-8")


def write_srt(path: Path, cue_list) -> None:
    lines = []
    for i, (a, b, t) in enumerate(cue_list, 1):
        lines += [str(i), f"{fmt_ts(a, True)} --> {fmt_ts(b, True)}", t.replace("\\N", "\n"), ""]
    path.write_text("\n".join(lines), encoding="utf-8")




PART_LUFS, PART_TP = -14.0, -2.5   # AAC overshoots the target peak by ~1 dB
TAIL_FADE = 0.5                    # each part ends on its cliffhanger: 0.5 s ambience/music fade-out
FIRST_SECONDS = 3.0                # a part's first 3 s are never black and never a text card


def part_audio(mix: Path, a: float, b: float, out: Path) -> str:
    """Slice [a, b] of the episode mix, fade the last TAIL_FADE s, normalise to PART_LUFS (static gain +
    limiter; loudnorm's dynamic mode pumps). The episode mix is never recomputed for vertical."""
    import json as _json
    import subprocess
    dur = b - a
    sl = (f"atrim={a:.3f}:{b:.3f},asetpts=PTS-STARTPTS,afade=t=in:d=0.04,"
          f"afade=t=out:st={max(0.0, dur - TAIL_FADE):.3f}:d={TAIL_FADE}")
    ln = f"loudnorm=I={PART_LUFS}:TP={PART_TP}:LRA=11"
    p = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(mix), "-af", f"{sl},{ln}:print_format=json",
                        "-f", "null", "-"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                       encoding="utf-8", errors="replace")
    mm = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", p.stderr)
    if p.returncode or not mm:
        raise PipelineError(f"loudness part (ukur) gagal:\n{p.stderr[-600:]}")
    d = _json.loads(mm.group(0))
    gain = PART_LUFS - float(d["input_i"]) if d["input_i"] not in ("-inf", "inf") else 0.0
    af = f"{sl},volume={gain:.2f}dB,alimiter=limit={10 ** (PART_TP / 20):.4f}:attack=2:release=80:level=false"
    tmp = atomic_out(out)
    run(["ffmpeg", "-y", "-i", mix, "-af", af, "-ar", "48000", "-c:a", "pcm_s16le", tmp], f"audio {out.name}")
    os.replace(tmp, out)
    return f"{float(d['input_i']):.1f} → {PART_LUFS:.0f} LUFS"


def first_seconds_override(ep: Episode, psegs) -> dict:
    """{key of a black/text_card beat starting in the first 3 s: the image beat shown instead} — the
    nearest strong image of the part (cover scoring: tense SFX, characters, close-up; detail crops avoided)."""
    from .covers import _score
    from .threads import _sfx_map
    bad = [s for s in psegs if s.start < FIRST_SECONDS and s.beat is not None
           and s.beat.visual in ("black", "text_card")]
    if not bad:
        return {}
    imgs = [(i, s.beat) for i, s in enumerate(psegs) if s.beat is not None and s.beat.visual == "image"
            and ep.image_for(s.beat)]
    if not imgs:
        warn("Part tanpa gambar sama sekali: 3 detik pertama tetap hitam/kartu")
        return {}
    sfx = _sfx_map(ep)
    out = {}
    for s in bad:
        i0 = psegs.index(s)
        _, best = max(imgs, key=lambda ib: _score(ep, ib[1], sfx) - 0.35 * abs(ib[0] - i0))
        out[s.beat.key] = best
    return out


def part_ranges(ep: Episode, segs, sel=None) -> list[dict]:
    """One range per script part (timeline = episode mix timebase). Trailing long_only beats (e.g. a
    'Bersambung' card) stay out: a part ends on its cliffhanger."""
    from .timeline import cliffhanger
    rows = []
    beat_segs = [s for s in segs if s.kind == "beat"]
    if sel:
        keys = {b.key for b in sel}
        ss = [s for s in beat_segs if s.beat.key in keys and not s.beat.long_only]
        return [{"n": 1, "title": "preview", "segs": ss}] if ss else []
    for pi, part in enumerate(ep.parts):
        cb = cliffhanger(ep, pi)
        ss = [s for s in beat_segs if s.beat.chapter == pi]
        if cb is not None:
            ss = ss[: [x.beat.key for x in ss].index(cb.key) + 1]
        if ss:
            rows.append({"n": pi + 1, "title": part["title"], "segs": ss})
    return rows


def _piece(ep: Episode, args, name: str, label: str, psegs, mix: Path, outdir: Path,
           first_rule: bool = True) -> dict:
    """Render one vertical video (a part, or the full episode with --full) straight from its segments."""
    from copy import copy
    from .render import xfade_join
    a = psegs[0].start
    b = psegs[-1].start + psegs[-1].slot
    dur = b - a
    rel = []
    for s in psegs:
        c = copy(s)
        c.start = s.start - a
        rel.append(c)
    override = first_seconds_override(ep, rel) if first_rule else {}
    shots = plan(ep, rel, override)
    clips = render(ep, shots, args.force)
    cue_list = cues(rel)
    ass = ep.cache / f"v_{name}.ass"
    write_ass(ass, cue_list, label, dur)
    r = {**ep.render, "width": W, "height": H, "_size": (W, H)}
    video = ep.cache / f"vvideo_{name}.mp4"
    work = ep.cache / "groups_v"
    work.mkdir(exist_ok=True)
    xfade_join(clips, [x["slot"] for x in shots], video, r, work, final=True, force=True,
               post=f"ass={ass.name}", cwd=ep.cache)
    audio = ep.cache / f"vaudio_{name}.wav"
    lufs = part_audio(mix, a, b, audio)
    out = outdir / f"{name}.mp4"
    from .encode import AUDIO, FASTSTART
    tmp = atomic_out(out)
    run(["ffmpeg", "-y", "-i", video, "-i", audio, "-map", "0:v", "-map", "1:a", "-c:v", "copy", *AUDIO,
         "-t", f"{dur:.3f}", *FASTSTART, tmp], f"mux {out.name}")
    os.replace(tmp, out)
    write_srt(outdir / f"{name}.srt", cue_list)
    t, first3 = 0.0, []
    for sh in shots:
        if t < FIRST_SECONDS:
            first3.append({"kind": sh["kind"], "key": sh.get("key"), "stand_in": sh.get("stand_in")})
        t += sh["slot"]
    words = sum(len(s.text.split()) for s in psegs if s.text)
    return {"file": out.name, "a": round(a, 3), "b": round(b, 3), "dur": round(dur, 3), "words": words,
            "wpm": round(words / (dur / 60), 1) if dur else 0, "first_beat": psegs[0].beat.key,
            "last_beat": psegs[-1].beat.key, "first_line": psegs[0].text, "last_line": psegs[-1].text,
            "first3": first3, "stand_ins": {k: v.key for k, v in override.items()}, "lufs": lufs,
            "size_mb": round(out.stat().st_size / 1e6, 1),
            "crops": [{"key": x["key"], "src": str(x["src"]), "box": x["box"], "wf": x["wf"], "x0": x["x0"],
                       "x1": x["x1"], "mode": x["mode"], "why": x["why"], "size": x["size"]}
                      for x in shots if x["kind"] == "image"]}


def _hook(ep: Episode, segs, a: float, b: float) -> str:
    """Caption hook: the part's most gripping line (same scoring as the Threads hook), with the line
    before it when they read as one moment."""
    from .threads import _beat_score, _sfx_map, tlen
    sfx = _sfx_map(ep)
    beats = [s.beat for s in segs if s.kind == "beat" and s.text and a <= s.start < b and s.beat.visual != "text_card"]
    if not beats:
        return ""
    allb = [s.beat for s in segs if s.kind == "beat"]
    def nxt(bt):
        i = allb.index(bt)
        return allb[i + 1] if i + 1 < len(allb) else None
    cut = max(1, int(len(beats) * 0.85))          # don't give away the part's ending
    top = max(beats[:cut], key=lambda bt: (_beat_score(ep, bt, sfx, nxt(bt)), -beats.index(bt)))
    i = beats.index(top)
    hook = top.text.strip()
    if i > 0 and beats[i - 1].speaker == top.speaker and tlen(beats[i - 1].text + " " + hook) <= 160:
        hook = beats[i - 1].text.strip() + " " + hook
    return hook


# ------------------------------------------------------------------ command
def build_vertical(ep: Episode, args, sel, segs, mix: Path, narration: Path, story_total: float) -> Path:
    """Vertical 1080x1920 parts (YouTube Shorts / TikTok / IG Reels / FB Reels, same files), cut at the
    script's part boundaries and rendered directly from the shared episode mix. No opening card, no
    closing card, no channel outro. --full additionally renders the whole episode vertically."""
    from .covers import part_covers
    step("Part vertikal 1080x1920 (Shorts/TikTok/Reels)")
    outdir = ep.output / "vertical"
    outdir.mkdir(parents=True, exist_ok=True)
    title = ep.story.get("title", ep.slug)
    ranges = part_ranges(ep, segs, sel)
    if not ranges:
        raise PipelineError("Tidak ada beat untuk part vertikal.")
    M = len(ranges)
    base = f"preview_{sel[0].key}-{sel[-1].key}" if sel else ep.ep
    if not sel:
        for old in outdir.glob(f"{base}_part*.mp4"):
            old.unlink()
    parts = []
    for pr in ranges:
        n = pr["n"]
        name = base if sel else f"{base}_part{n}"
        label = f"{title} · Eps {ep.number}" + ("" if sel else f" · Part {n}/{M}")
        step(f"Part {n}/{M}: {pr['segs'][0].beat.key}–{pr['segs'][-1].beat.key}")
        row = _piece(ep, args, name, label, pr["segs"], mix, outdir)
        row.update(n=n, title=pr["title"], last=(n == M))
        parts.append(row)
        info(f"Part {n}: {fmt_ts(row['dur'])} · {row['wpm']:.0f} wpm · {row['size_mb']:.0f} MB · {row['lufs']}"
             + (f" · 3 dtk pertama: {', '.join(f'{k}→{v}' for k, v in row['stand_ins'].items())}"
                if row["stand_ins"] else ""))
    if not sel:
        part_covers(ep, parts, segs, outdir, base)   # title from thumbnail_9x16 + "PART N", embedded
        captions = []
        for p in parts:
            captions += [f"=== Part {p['n']}/{M} · {p['file']} · {fmt_ts(p['dur'])} ===",
                         _hook(ep, segs, p["a"], p["b"]), "",
                         f"{title} · Eps {ep.number} · Part {p['n']}/{M}", "", HASHTAGS, ""]
        (outdir / "captions.txt").write_text("\n".join(captions), encoding="utf-8")
    if getattr(args, "full", False) and not sel:
        step("Vertikal penuh (--full)")
        allsegs = [s for s in segs if s.kind == "beat" and not s.beat.long_only]
        full = _piece(ep, args, base, f"{title} · Eps {ep.number}", allsegs, mix, outdir)
        thumbs.cover_copy(ep, outdir / full["file"])
        ok(f"Vertikal penuh: {full['file']} ({fmt_ts(full['dur'])})")
    (outdir / f"parts_{base}.json").write_text(json.dumps(parts, indent=2, ensure_ascii=False), encoding="utf-8")
    ok(f"{M} part di {outdir.relative_to(ROOT)}")
    rows = [{"kind": s.kind, "key": s.beat.key if s.beat else s.kind, "start": round(s.start, 3)} for s in segs]
    m = {"kind": "vertical_parts", "outdir": str(outdir), "parts": parts, "segments_total": story_total,
         "segments": rows,
         "base": base, "max_shot": float(ep.render["max_shot"])}
    mp = ep.cache / f"render_vertical{'_preview' if sel else ''}.json"
    mp.write_text(json.dumps(m, indent=2, ensure_ascii=False), encoding="utf-8")
    if not getattr(args, "no_review", False):
        from .review import review
        review(ep, mp)
    return mp
