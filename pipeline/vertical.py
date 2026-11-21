"""`build --vertical`: 1080x1920 full-bleed version of the same timeline, audio and sound mix.

Each 16:9 image is cut to a 9:16 window: centred on the character(s) from `characters_in_scene`,
or slowly panned across scenes without characters. Per-beat overrides in script.yaml:
    vertical_crop_x: 0.0-1.0           # window position, 0 = left edge, 1 = right edge
    vertical_pan: left_to_right | right_to_left | none
Outputs (output/vertical/): the full video (TikTok), 2-3 minute parts (Instagram/Facebook) cut at
beat boundaries, and captions.txt.
"""
from __future__ import annotations

import json
import math
import os
import random
import re
from pathlib import Path

from PIL import Image, ImageFont

from .common import (ROOT, Episode, PipelineError, atomic_out, file_sig, fmt_ts, info, ok, quantize, run,
                     sha, step, warn)
from . import channel as C
from . import thumbs
from . import visuals as V
from .render import TEXT_CARD_FADE, render_clip, save_still, split_slot, xfade_join

W, H = 1080, 1920
POS_X = {"left": 0.30, "center": 0.50, "centre": 0.50, "middle": 0.50, "foreground": 0.50, "right": 0.70}
VZOOM = 0.08              # Ken Burns zoom inside the crop (horizontal uses ~0.12)
PAN_SPEED = 0.04          # max pan speed, share of image width per second ("slow")
PART_MAX = 180.0          # Instagram/Facebook part length incl. cards
PART_TARGET = 165.0
START_CARD, END_CARD = 1.0, 1.5
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
        xs = [(n, POS_X.get(p.lower(), 0.5)) for n, p, _ in chars]
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


def plan(ep: Episode, segs) -> list[dict]:
    r = ep.render
    fps = int(r["fps"])
    rnd = random.Random(f"{ep.slug}-{ep.ep}-vertical")
    shots, flip = [], 0
    for s in segs:
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
         "-frames:v", n, "-r", fps, "-c:v", "libx264", "-preset", r["clip_preset"], "-crf", "18",
         "-pix_fmt", "yuv420p", "-an", tmp], f"pan {out.name}")
    os.replace(tmp, out)


def render(ep: Episode, shots: list[dict], force: bool, label="vclip") -> list[Path]:
    r = ep.render
    D = float(r["crossfade"])
    clip_dir, still_dir = ep.cache / "clips_v", ep.cache / "stills_v"
    clip_dir.mkdir(parents=True, exist_ok=True)
    still_dir.mkdir(parents=True, exist_ok=True)
    paths, rendered = [], 0
    for i, sh in enumerate(shots):
        dur = sh["slot"] + D
        sig = {k: v for k, v in sh.items() if k not in ("src", "why")}
        if sh["kind"] == "channel":
            sig["vlayout"] = C.TAGLINE_WIDTH_VERTICAL  # vertical card layout is part of the cache key
        sig.update(src=file_sig(sh.get("src")), dur=dur, fps=r["fps"], zoom=VZOOM, v=2,
                   serif=V.find_serif_font(ep.story))
        h_ = sha(sig)
        out = clip_dir / f"{label}_{h_}.mp4"
        paths.append(out)
        if out.exists() and not force:
            continue
        print(f"  [{i + 1}/{len(shots)}] {label} {sh['kind']:<7} {dur:5.2f}s {sh.get('dir', '')}", flush=True)
        if sh["kind"] == "black":
            render_clip(None, out, dur, "static", r, W, H)
        elif sh["kind"] == "image" and sh["mode"] == "pan":
            _render_pan(sh, out, dur, r, still_dir, h_)
        else:
            if sh["kind"] == "image":
                reg = _region_image(sh)
                ww = reg.height * 9 / 16
                x0 = min(max(0, sh["x0"] * reg.width - ww / 2), reg.width - ww)
                img = reg.crop((int(x0), 0, int(x0 + ww), reg.height))
            elif sh["kind"] == "text":
                img = V.text_card(ep.story, sh["text"], W * 2, H * 2)
            else:  # channel outro
                img = C.card_image(sh["card"], W * 2, H * 2)
            still = save_still(img, still_dir / f"{h_}.jpg", W, H)
            render_clip(still, out, dur, sh.get("dir", "static"), r, W, H,
                        zoom=VZOOM if sh["kind"] == "image" else None,
                        fade=sh.get("fade", 0.0), slot=sh.get("fade_slot", sh["slot"]))
        rendered += 1
    info(f"{rendered} klip vertikal dirender, {len(shots) - rendered} dari cache")
    return paths


def join(ep: Episode, shots, clips, force: bool, name: str) -> Path:
    r = {**ep.render, "width": W, "height": H, "_size": (W, H)}
    slots = [s["slot"] for s in shots]
    video = ep.cache / f"vvideo_{name}_{sha([str(c) for c in clips] + slots + [r['crossfade'], r['crf'], r['grain']])}.mp4"
    if force or not video.exists():
        work = ep.cache / "groups_v"
        work.mkdir(exist_ok=True)
        xfade_join(clips, slots, video, r, work, final=True, force=force)
    else:
        info("Video vertikal dipakai dari cache")
    return video


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


def normalize_part(f: Path) -> str:
    """Two-pass loudnorm of a part's audio to PART_LUFS / PART_TP; video (and cover art) copied untouched."""
    import json as _json
    import subprocess
    ln = f"loudnorm=I={PART_LUFS}:TP={PART_TP}:LRA=11"
    p = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(f), "-map", "0:a", "-af",
                        f"{ln}:print_format=json", "-f", "null", "-"], stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
    mm = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", p.stderr)
    if p.returncode or not mm:
        raise PipelineError(f"loudnorm {f.name} (ukur) gagal:\n{p.stderr[-600:]}")
    d = _json.loads(mm.group(0))
    # static gain to the target, then a limiter for the peaks (loudnorm's linear mode would give up
    # on loudness to respect the peak ceiling, and its dynamic mode pumps)
    gain = PART_LUFS - float(d["input_i"])
    af = (f"volume={gain:.2f}dB,alimiter=limit={10 ** (PART_TP / 20):.4f}:attack=2:release=80:level=false,"
          "aresample=48000")
    tmp = atomic_out(f)
    run(["ffmpeg", "-y", "-i", f, "-map", "0", "-c:v", "copy", "-af", af, "-c:a", "aac", "-b:a", "192k",
         "-ar", "48000", "-movflags", "+faststart", tmp], f"loudnorm {f.name}")
    os.replace(tmp, f)
    return f"{float(d['input_i']):.1f} → {PART_LUFS:.0f} LUFS"


def _ff(cmd: list, cwd: Path, desc: str) -> None:
    import subprocess
    p = subprocess.run([str(c) for c in cmd], cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       text=True, encoding="utf-8", errors="replace")
    if p.returncode:
        raise PipelineError(f"{desc} gagal:\n{p.stderr[-1200:]}")


# grain makes CRF alone balloon (≈17 Mbps); cap it so parts stay a sane upload size
ENC = ["-c:v", "libx264", "-preset", "medium", "-crf", "20", "-maxrate", "8M", "-bufsize", "16M", "-pix_fmt", "yuv420p",
       "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart"]


# ------------------------------------------------------------------ parts
def _tension(ep: Episode, s, sfx: dict) -> tuple[int, str]:
    """How good a cut right after this beat is (higher = tenser), with the reason."""
    b, score, why = s.beat, 0, []
    fx = sfx.get(b.key) or {}
    if fx and any(k in str(fx.get("file", "")) for k in TENSE_SFX):
        score += 3
        why.append(f"SFX {fx['file']}")
    t = (b.text or "").strip()
    if t.endswith(("?", "!", "...", "…")):
        score += 2
        why.append("kalimat menggantung")
    elif "..." in t or "…" in t:
        score += 1
        why.append("jeda dalam kalimat")
    if b.visual == "black" or (b.pause_after or 0) >= 1.0:
        score += 1
        why.append("jeda dramatis")
    return score, ", ".join(why) or "batas beat"


def choose_parts(ep: Episode, segs, total: float) -> list[dict]:
    from .sound import load_config
    sfx = {}
    for k, v in ((load_config(ep) or {}).get("sfx") or {}).items():
        b = ep.resolve_ref(str(k))
        if b:
            sfx[b.key] = v
    cands = []
    for s in segs[:-1]:
        if s.kind == "beat":
            sc, why = _tension(ep, s, sfx)
            cands.append({"t": s.start + s.slot, "score": sc, "why": why, "after": s.beat.key})
    room = PART_MAX - START_CARD - END_CARD          # story seconds per part
    n = max(1, math.ceil(total / (room - 8)))
    while True:
        cuts, a, feasible = [], 0.0, True
        for i in range(1, n):
            target = a + (total - a) / (n - i + 1)
            left = n - i
            pool = [c for c in cands if a + 60 <= c["t"] <= a + room and total - c["t"] <= left * room + END_CARD]
            if not pool:
                feasible = False
                break
            best = max(pool, key=lambda c: c["score"] - abs(c["t"] - target) / 15)
            cuts.append(best)
            a = best["t"]
        if feasible and total - a <= room + END_CARD:
            break
        n += 1
        if n > 40:
            raise PipelineError("Tidak bisa membagi video jadi part ≤ 3 menit di batas beat.")
    parts, a = [], 0.0
    for i, c in enumerate(cuts + [None]):
        b = c["t"] if c else total
        last = c is None
        parts.append({"n": i + 1, "a": a, "b": b, "last": last, "why": None if last else c["why"],
                      "after": None if last else c["after"],
                      "dur": START_CARD + (b - a) + (0 if last else END_CARD)})
        a = b
    return parts


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
def build_vertical(ep: Episode, args, sel, segs, story_starts, mix: Path, narration: Path, total: float, ch):
    from .render import _write_manifest
    step("Video vertikal 1080x1920")
    outdir = ep.output / "vertical"
    outdir.mkdir(parents=True, exist_ok=True)
    name = f"preview_{sel[0].key}-{sel[-1].key}" if sel else ep.ep
    tag = "_vertical" + ("_preview" if sel else "")
    title = ep.story.get("title", ep.slug)
    label = f"{title} · Eps {ep.number}"

    shots = plan(ep, segs)
    clips = render(ep, shots, args.force)
    step("Crossfade & gabung video vertikal")
    video = join(ep, shots, clips, args.force, name)

    cue_list = cues(segs)
    ass = ep.cache / f"v_{name}.ass"
    write_ass(ass, cue_list, label, total)
    out = outdir / f"{name}.mp4"
    srt = outdir / f"{name}.srt"
    write_srt(srt, cue_list)
    tmp = atomic_out(out)
    _ff(["ffmpeg", "-y", "-i", video, "-i", mix, "-vf", f"ass={ass.name}", "-map", "0:v", "-map", "1:a",
         *ENC, "-t", f"{total:.3f}", tmp], ep.cache, "encode vertikal penuh")
    os.replace(tmp, out)
    covers = [thumbs.cover_copy(ep, out)]
    ok(f"Vertikal penuh: {out.relative_to(ROOT)}  ({fmt_ts(total)})")

    # ---- parts for Instagram / Facebook
    step("Part Instagram/Facebook (≤ 3 menit, dipotong di batas beat)")
    parts = choose_parts(ep, segs, total)
    N = len(parts)
    for old in outdir.glob(f"{name}_part*.mp4"):
        old.unlink()
    card_shots = []
    for p in parts:
        card_shots.append({"kind": "text", "slot": START_CARD, "text": f"{label} · Part {p['n']}",
                           "dir": "static", "fade": 0.25, "key": f"part{p['n']}_start"})
        if not p["last"]:
            card_shots.append({"kind": "text", "slot": END_CARD, "text": f"Lanjut ke Part {p['n'] + 1}",
                               "dir": "static", "fade": 0.3, "key": f"part{p['n']}_end"})
    card_clips = dict(zip([s["key"] for s in card_shots], render(ep, card_shots, args.force, label="vcard")))
    captions = []
    for p in parts:
        a, b, n = p["a"], p["b"], p["n"]
        body = b - a
        pcues = [(x - a + START_CARD, y - a + START_CARD, t) for x, y, t in cue_list
                 if x >= a - 0.01 and y <= b + 0.01]
        p_ass = ep.cache / f"v_{name}_part{n}.ass"
        write_ass(p_ass, pcues, f"{label} · Part {n}", p["dur"])
        po = outdir / f"{name}_part{n}.mp4"
        ins = ["-i", card_clips[f"part{n}_start"], "-i", video, "-i", mix]
        fc = (f"[0:v]trim=0:{START_CARD},setpts=PTS-STARTPTS[c0];"
              f"[1:v]trim={a:.3f}:{b:.3f},setpts=PTS-STARTPTS,fade=t=in:d=0.3[m];")
        aud = f"[2:a]atrim={a:.3f}:{b:.3f},asetpts=PTS-STARTPTS,afade=t=in:d=0.3"
        if p["last"]:
            fc += "[c0][m]concat=n=2:v=1:a=0"
        else:
            ins += ["-i", card_clips[f"part{n}_end"]]
            fc += f"[3:v]trim=0:{END_CARD},setpts=PTS-STARTPTS[c1];[c0][m][c1]concat=n=3:v=1:a=0"
            aud += f",afade=t=out:st={max(0.0, body - 0.4):.3f}:d=0.4"
        ms = int(START_CARD * 1000)
        fc += f",ass={p_ass.name}[v];{aud},adelay={ms}|{ms},apad=whole_dur={p['dur']:.3f}[a]"
        tmp = atomic_out(po)
        _ff(["ffmpeg", "-y", *ins, "-filter_complex", fc, "-map", "[v]", "-map", "[a]", *ENC,
             "-t", f"{p['dur']:.3f}", tmp], ep.cache, f"encode part {n}")
        os.replace(tmp, po)
        normalize_part(po)  # a slice of the episode mix is not -14 LUFS on its own
        p["file"] = po.name
        captions += [f"=== Part {n}/{N} · {po.name} · {fmt_ts(p['dur'])} ===",
                     _hook(ep, segs, a, b), "",
                     f"{title} · Eps {ep.number} · Part {n}/{N}" + ("" if p["last"] else f" (lanjut ke Part {n + 1})"),
                     "", HASHTAGS, ""]
    from .covers import part_covers  # one cover per part (covers.yaml), embedded in each part
    covers += part_covers(ep, parts, segs, outdir, name)
    cap = outdir / (f"captions_{name}.txt" if sel else "captions.txt")
    cap.write_text("\n".join(captions), encoding="utf-8")
    for p in parts:
        info(f"Part {p['n']}: {fmt_ts(p['dur'])}  ({fmt_ts(p['a'])}–{fmt_ts(p['b'])})"
             + (f"  · potong setelah {p['after']} ({p['why']})" if not p["last"] else "  · diakhiri outro"))
    ok(f"{N} part + {cap.name} di {outdir.relative_to(ROOT)}")
    if any(covers):
        info(f"Cover: thumbnail_9x16.jpg untuk video penuh, cover sendiri untuk {len(parts)} part")
    else:
        warn("Cover vertikal dilewati: thumbnail/thumbnail_9x16.jpg belum ada (import thumb_epXX_9x16)")
    (outdir / f"parts_{name}.json").write_text(json.dumps(parts, indent=2, ensure_ascii=False), encoding="utf-8")

    crops = [{"key": s["key"], "src": str(s["src"]), "box": s["box"], "wf": s["wf"], "x0": s["x0"],
              "x1": s["x1"], "mode": s["mode"], "why": s["why"], "size": s["size"]}
             for s in shots if s["kind"] == "image"]
    manifest = _write_manifest(ep, out, srt, tag, total, segs, story_starts, shots, narration, ch,
                               vertical=True, burned_subs=True, crops=crops, parts=parts)
    if not getattr(args, "no_review", False):
        from .review import review
        review(ep, manifest)
