"""`review`: technical self-check of the last render → output/review_report.md + contact sheets.

Reads cache/render[_preview].json (written by `build`) and checks loudness, bed level, shot lengths,
silence, black/frozen video and subtitles; contact sheets (one frame every 4 s, subtitles burned in as
in the review copy) are for a human/visual pass.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .common import (PART_MAX_S, ROOT, WPM_HIGH, WPM_LOW, Episode, PipelineError, fmt_ts, info, ok,
                     step)

LUFS_TARGET, LUFS_TOL, TP_MAX = -14.0, 1.0, -1.0
BED_MAX_GAP, BED_MIN_GAP = 26.0, 12.0     # bed (music+ambience) in pauses vs voice during speech
SHOT_WARN = 12.0
SILENCE_DB, SILENCE_MIN = -50.0, 3.0
SHEET_EVERY, SHEET_COLS, SHEET_ROWS, THUMB_W = 4.0, 4, 4, 480
SUB_STYLE = ("FontName=Arial,FontSize=17,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
             "BorderStyle=1,Outline=1.6,Shadow=0.6,MarginV=22")  # same as the review copy


def _ff(args: list, cwd=None) -> str:
    p = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", *map(str, args)], cwd=cwd, stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
    if p.returncode:
        raise PipelineError(f"ffmpeg (review) gagal:\n{p.stderr[-800:]}")
    return p.stderr


# ------------------------------------------------------------------ checks
def loudness(out: Path) -> dict:
    s = _ff(["-i", out, "-map", "0:a", "-af", "ebur128=peak=true", "-f", "null", "-"])
    summ = s[s.rfind("Summary:"):]
    g = lambda pat: float(re.search(pat, summ).group(1))  # noqa: E731
    return {"I": g(r"I:\s*(-?[\d.]+) LUFS"), "LRA": g(r"LRA:\s*(-?[\d.]+) LU"),
            "TP": g(r"Peak:\s*(-?[\d.]+|-inf) dBFS") if "Peak:" in summ else None}


def bed_gap(m: dict) -> dict | None:
    from .sound import _emean, _momentary, _psum
    st = m["stems"]
    if not all(Path(st[k]).exists() for k in ("music", "amb")):
        return None
    voice, music, amb = (_momentary(Path(p)) for p in (m["narration"], st["music"], st["amb"]))
    story = [s for s in m["segments"] if s["kind"] in ("beat", "lead", "recap", "card")]
    if not story:
        return None
    s0 = story[0]["story_start"]
    end = story[-1]["story_start"] + story[-1]["slot"]
    speech = [(s["story_start"] + s["lead"], s["story_start"] + s["lead"] + s["audio_dur"])
              for s in story if s["audio_dur"] > 0.8]
    muted = {k.lower() for k in m.get("mute_on_beats", [])}
    mute_iv = [(s["story_start"], s["story_start"] + s["slot"]) for s in story if s["key"].lower() in muted]
    inside = lambda t, iv, a=0.0, b=0.0: any(x - a <= t <= y + b for x, y in iv)  # noqa: E731
    v_sp = [v for t, v in voice if inside(t, speech, -0.4, -0.1)]          # well inside each line
    vmap = {round(t, 1): v for t, v in voice}
    bed = {round(t, 1): v for t, v in music}
    bed_all = [(t, _psum(bed.get(round(t, 1), -120.0), v)) for t, v in amb]
    # pauses: the 400 ms window holds (almost) no voice; skip mute_on_beats and the fades at either end
    pauses = [v for t, v in bed_all if s0 + 3.0 <= t <= end - 4.0 and vmap.get(round(t, 1), -120.0) < -45.0
              and not inside(t, mute_iv)]
    under = [v for t, v in bed_all if inside(t, speech, -0.4 - 0.25, -0.1)]
    if not v_sp or not pauses:
        return None
    vs, bp = _emean(v_sp), _emean(pauses)
    return {"voice": vs, "bed": bp, "gap": vs - bp, "pause_s": len(pauses) / 10,
            "under": _emean(under) if under else None}


def long_shots(m: dict) -> list[dict]:
    """Images on screen > SHOT_WARN s: one shot, or consecutive shots of the same image (split crops)."""
    rows, run_ = [], None
    for s in m["shots"] + [{"kind": None}]:
        same = run_ and s["kind"] == "image" and s.get("src") == run_["src"]
        if same:
            run_["slot"] += s["slot"]
            run_["n"] += 1
            continue
        if run_ and run_["slot"] > SHOT_WARN + 1e-3:
            rows.append(run_)
        run_ = ({"start": s["start"], "src": s["src"], "slot": s["slot"], "n": 1, "crop": s.get("crop")}
                if s["kind"] == "image" else None)
    return rows


def _seg_at(m: dict, t: float) -> list[dict]:
    return [s for s in m["segments"] if s["start"] - 0.05 <= t <= s["start"] + s["slot"] + 0.05]


def _intentional(m: dict, a: float, b: float) -> str | None:
    """Why a silent/black stretch [a, b] is on purpose, or None."""
    muted = {k.lower() for k in m.get("mute_on_beats", [])}
    segs = [s for s in m["segments"] if s["start"] < b - 0.2 and s["start"] + s["slot"] > a + 0.2]
    why, plain = [], False
    for s in segs:
        if s["kind"] in ("lead", "outro", "intro", "card"):
            why.append({"lead": "cold open", "outro": "outro", "intro": "intro", "card": "kartu bab"}[s["kind"]])
        elif s["visual"] in ("black", "text_card"):
            why.append(f"{s['key']} ({s['visual']})")
        elif (s["pause_after"] or 0) >= 2.0:
            why.append(f"{s['key']} (pause_after {s['pause_after']}s)")
        elif s["key"].lower() in muted:
            why.append(f"{s['key']} (mute_on_beats)")
        else:
            plain = True
    # a stretch is only "intentional" if every segment it covers is one of the above
    return " + ".join(why) if why and not plain else None


def silences(m: dict, out: Path) -> list[dict]:
    s = _ff(["-i", out, "-map", "0:a", "-af", f"silencedetect=noise={SILENCE_DB}dB:d={SILENCE_MIN}",
             "-f", "null", "-"])
    starts = [float(x) for x in re.findall(r"silence_start:\s*(-?[\d.]+)", s)]
    ends = [float(x) for x in re.findall(r"silence_end:\s*([\d.]+)", s)]
    rows = []
    for i, a in enumerate(starts):
        b = ends[i] if i < len(ends) else m["total"]
        rows.append({"a": max(0.0, a), "b": b, "why": _intentional(m, a, b)})
    return rows


def video_gaps(m: dict, out: Path) -> dict:
    s = _ff(["-i", out, "-an", "-vf", "scale=480:-2,blackdetect=d=1.0:pic_th=0.98:pix_th=0.08,"
             "freezedetect=n=-55dB:d=5", "-f", "null", "-"])
    black = [(float(a), float(b)) for a, b in re.findall(r"black_start:([\d.]+)\s+black_end:([\d.]+)", s)]
    fs = [float(x) for x in re.findall(r"freeze_start:\s*([\d.]+)", s)]
    fe = [float(x) for x in re.findall(r"freeze_end:\s*([\d.]+)", s)]
    freeze = [(a, fe[i] if i < len(fe) else m["total"]) for i, a in enumerate(fs)]
    tag = lambda iv: [{"a": a, "b": b, "why": _intentional(m, a, b)} for a, b in iv]  # noqa: E731
    return {"black": tag(black), "freeze": tag(freeze)}


def subtitles(m: dict) -> dict:
    srt = Path(m["srt"])
    if not srt.exists():
        return {"cues": 0, "issues": ["SRT tidak ada"]}
    blocks = [b for b in re.split(r"\n\s*\n", srt.read_text(encoding="utf-8").strip()) if b.strip()]
    ts = lambda x: sum(float(p) * f for p, f in zip(x.replace(",", ".").split(":"), (3600, 60, 1)))  # noqa: E731
    cues, issues = [], []
    for b in blocks:
        ln = b.splitlines()
        a, z = (ts(x.strip()) for x in ln[1].split("-->"))
        cues.append((a, z, " ".join(ln[2:])))
    for i, (a, z, t) in enumerate(cues):
        if i and a < cues[i - 1][1] - 0.01:
            issues.append(f"cue {i + 1} tumpang tindih dengan cue {i} ({fmt_ts(a)})")
        cps = len(t) / max(0.01, z - a)
        if cps > 22:
            issues.append(f"cue {i + 1} terlalu cepat dibaca: {cps:.0f} karakter/detik ({fmt_ts(a)})")
    if m.get("channel"):
        from .channel import Channel
        tag = Channel(m["channel"]).tagline.split(".")[0]
        if any(tag in t for _, _, t in cues):
            issues.append("tagline channel masih ada di subtitle")
    return {"cues": len(cues), "issues": issues}


def chapters(ep: Episode, m: dict) -> dict:
    out = Path(m["output"])
    desc = ep.output / ("description.txt" if not out.stem.startswith("preview_") else f"description_{out.stem}.txt")
    if not desc.exists():
        return {"file": None, "stamps": [], "issues": ["deskripsi tidak ada"]}
    stamps = re.findall(r"^(\d{2}:\d{2}(?::\d{2})?) (.+)$", desc.read_text(encoding="utf-8"), re.M)
    want = sorted({s["chapter"] for s in m["segments"] if s["chapter"] is not None})
    issues = []
    if not stamps or stamps[0][0] not in ("00:00", "00:00:00"):
        issues.append("timestamp pertama bukan 00:00")
    if len([x for x in stamps if x[1].startswith(("Bab", "Part"))]) != len(want):
        issues.append(f"{len(stamps)} timestamp untuk {len(want)} part")
    return {"file": desc.name, "stamps": stamps, "issues": issues}


def thumbs_check(ep: Episode) -> list[str]:
    """thumbnail/thumbnail_16x9.jpg (1280x720, < 2 MB) and thumbnail_9x16.jpg (1080x1920)."""
    from . import thumbs
    issues = []
    for r, (w, h) in thumbs.SIZES.items():
        p = thumbs.path(ep, r)
        if not p.exists():
            issues.append(f"thumbnail_{r}.jpg tidak ada")
            continue
        with Image.open(p) as im:
            if im.size != (w, h):
                issues.append(f"thumbnail_{r}.jpg {im.size[0]}x{im.size[1]} (harus {w}x{h})")
        if r == "16x9" and p.stat().st_size > 2 * 1024 * 1024:
            issues.append(f"thumbnail_16x9.jpg {p.stat().st_size / 1e6:.2f} MB (> 2 MB, ditolak YouTube)")
    return issues


def parts_check(m: dict) -> list[dict]:
    """Each IG/FB part file: duration, loudness, true peak, silence and black frames outside the cards."""
    outdir = Path(m["output"]).parent
    rows = []
    for p in m.get("parts") or []:
        f = outdir / p.get("file", "")
        if not f.is_file():
            rows.append({"n": p["n"], "file": f.name, "issues": ["file tidak ada"]})
            continue
        L = loudness(f)
        dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                                    "csv=p=0", str(f)], stdout=subprocess.PIPE, text=True).stdout.strip() or 0)
        start_card, end_card = 1.0, (0.0 if p["last"] else 1.5)
        to_full = lambda t: t - start_card + p["a"]  # noqa: E731
        s = _ff(["-i", f, "-af", f"silencedetect=noise={SILENCE_DB}dB:d={SILENCE_MIN}", "-vf",
                 "scale=320:-2,blackdetect=d=1.0:pic_th=0.98:pix_th=0.08", "-f", "null", "-"])
        issues = []
        s_starts = [float(x) for x in re.findall(r"silence_start:\s*(-?[\d.]+)", s)]
        s_ends = [float(x) for x in re.findall(r"silence_end:\s*([\d.]+)", s)]
        for i, a in enumerate(s_starts):
            b = s_ends[i] if i < len(s_ends) else dur
            if b <= start_card + 0.2 or a >= dur - end_card - 0.2:
                continue
            if not _intentional(m, to_full(a), to_full(b)):
                issues.append(f"hening {fmt_ts(a)}–{fmt_ts(b)}")
        for a, b in re.findall(r"black_start:([\d.]+)\s+black_end:([\d.]+)", s):
            a, b = float(a), float(b)
            if b <= start_card + 0.3 or a >= dur - end_card - 0.3:
                continue
            if not _intentional(m, to_full(max(a, start_card)), to_full(min(b, dur - end_card))):
                issues.append(f"layar hitam {fmt_ts(a)}–{fmt_ts(b)}")
        if abs(L["I"] - LUFS_TARGET) > LUFS_TOL:
            issues.append(f"loudness {L['I']:.1f} LUFS")
        if L["TP"] is None or L["TP"] > TP_MAX:
            issues.append(f"true peak {L['TP']} dBTP")
        if dur > 180.0 + 0.05:
            issues.append(f"durasi {fmt_ts(dur)} > 3 menit")
        rows.append({"n": p["n"], "file": f.name, "dur": dur, "I": L["I"], "TP": L["TP"],
                     "cover": f.with_name(f.stem + "_cover.jpg").exists(), "issues": issues})
    return rows


def threads_check(ep: Episode) -> dict | None:
    """output/threads/threads.json: posts over the Threads limit, threads over 15 posts."""
    f = ep.output / "threads" / "threads.json"
    if not f.exists():
        return None
    from .threads import HARD_LIMIT, MAX_POSTS
    th = json.loads(f.read_text(encoding="utf-8"))
    issues = []
    for t in th:
        issues += [f"{t['bab']} post {i}: {n} karakter (> {HARD_LIMIT})" for i, n in enumerate(t["posts"], 1) if n > HARD_LIMIT]
        if len(t["posts"]) > MAX_POSTS:
            issues.append(f"{t['bab']}: {len(t['posts'])} post (> {MAX_POSTS})")
    return {"n": len(th), "threads": th, "issues": issues}


# ------------------------------------------------------------------ contact sheets
def contact_sheets(m: dict, ep: Episode, prefix: str = "review_sheet") -> list[Path]:
    out, srt = Path(m["output"]), Path(m["srt"])
    base = out.parent
    for old in base.glob(f"{prefix}_[0-9]*.png"):
        old.unlink()
    vertical = bool(m.get("vertical"))
    cols, rows, thumb = (6, 3, 300) if vertical else (SHEET_COLS, SHEET_ROWS, THUMB_W)
    tmp = Path(tempfile.mkdtemp(prefix="review_", dir=ep.cache))
    try:
        # subtitles burned like the review copy, unless the video already has them burned in
        sub = (f",subtitles={srt.name}:force_style='{SUB_STYLE}'"
               if srt.exists() and not m.get("burned_subs") else "")
        vf = (f"trim=start={SHEET_EVERY / 2},select='isnan(prev_selected_t)+gte(t-prev_selected_t\\,"
              f"{SHEET_EVERY - 0.02})'{sub},scale={thumb}:-2")
        _ff(["-i", out, "-an", "-vf", vf, "-fps_mode", "vfr", tmp / "f_%04d.png"], cwd=srt.parent)
        frames = sorted(tmp.glob("f_*.png"))
        from . import fonts
        fnt = fonts.font("sans_bold", 18)
        per = cols * rows
        sheets = []
        for n in range(0, len(frames), per):
            batch = frames[n:n + per]
            w0, h0 = Image.open(batch[0]).size
            pad = 6
            sheet = Image.new("RGB", (cols * (w0 + pad) + pad, rows * (h0 + pad) + pad), (40, 40, 40))
            d = ImageDraw.Draw(sheet)
            for j, f in enumerate(batch):
                t = SHEET_EVERY / 2 + (n + j) * SHEET_EVERY
                x, y = pad + (j % cols) * (w0 + pad), pad + (j // cols) * (h0 + pad)
                sheet.paste(Image.open(f), (x, y))
                segs = _seg_at(m, t)
                label = f"{fmt_ts(t)}  {segs[0]['key'] if segs else ''}"
                d.rectangle((x, y, x + fnt.getlength(label) + 10, y + 26), fill=(0, 0, 0))
                d.text((x + 5, y + 3), label, font=fnt, fill=(255, 210, 60))
            p = base / f"{prefix}_{n // per + 1:02d}.png"
            sheet.save(p)
            sheets.append(p)
        return sheets
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def crop_maps(m: dict) -> list[Path]:
    """Vertical only: each source image with its 9:16 window (yellow = start, cyan = end of a pan)."""
    base = Path(m["output"]).parent
    for old in base.glob("review_crops_*.png"):
        old.unlink()
    seen, tiles = set(), []
    from . import fonts
    fnt = fonts.font("sans_bold", 16)
    TW = 420
    for c in m.get("crops", []):
        if c["key"] in seen:
            continue
        seen.add(c["key"])
        img = Image.open(c["src"]).convert("RGB")
        s = TW / img.width
        th = img.resize((TW, int(img.height * s)))
        d = ImageDraw.Draw(th)
        bx0, by0, bx1, by1 = (v * s for v in c["box"])
        if (bx1 - bx0) < TW - 2:
            d.rectangle((bx0, by0, bx1, by1), outline=(150, 150, 150), width=1)
        rw = bx1 - bx0
        ww = (by1 - by0) * 9 / 16
        for x, col in ((c["x0"], (255, 210, 60)), (c["x1"], (60, 220, 255))):
            left = bx0 + min(max(0, x * rw - ww / 2), rw - ww)
            d.rectangle((left, by0, left + ww, by1 - 1), outline=col, width=3)
            if c["mode"] != "pan":
                break
        label = f"{c['key']} · {c['mode']} · {c['why']}"
        tile = Image.new("RGB", (TW, th.height + 24), (25, 25, 25))
        tile.paste(th, (0, 24))
        ImageDraw.Draw(tile).text((4, 3), label[:52], font=fnt, fill=(255, 255, 255))
        tiles.append(tile)
    out, per, cols = [], 12, 4
    for n in range(0, len(tiles), per):
        batch = tiles[n:n + per]
        th = max(t.height for t in batch)
        rows = (len(batch) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * (TW + 6) + 6, rows * (th + 6) + 6), (40, 40, 40))
        for j, t in enumerate(batch):
            sheet.paste(t, (6 + (j % cols) * (TW + 6), 6 + (j // cols) * (th + 6)))
        p = base / f"review_crops_{n // per + 1:02d}.png"
        sheet.save(p)
        out.append(p)
    return out


# ------------------------------------------------------------------ report
def wpm_by_part(ep: Episode, m: dict) -> list[dict]:
    """Words per minute per script part, from the long video's segments (part = beat range incl. pauses)."""
    rows = {}
    for s in m["segments"]:
        if s["kind"] != "beat" or s["chapter"] is None:
            continue
        b = ep.resolve_ref(s["key"])
        if b is not None and b.long_only:
            continue
        r = rows.setdefault(s["chapter"], {"n": s["chapter"] + 1, "a": s["start"], "b": 0.0, "words": 0})
        r["b"] = s["start"] + s["slot"]
        r["words"] += s.get("words", 0)
    out = []
    for r in rows.values():
        r["dur"] = r["b"] - r["a"]
        r["wpm"] = r["words"] / (r["dur"] / 60) if r["dur"] else 0.0
        out.append(r)
    return sorted(out, key=lambda r: r["n"])


# ------------------------------------------------------------------ vertical parts
FIRST_S, LUMA_MIN = 3.0, 20.0


def _first_lumas(f: Path) -> list[tuple[float, float]]:
    """Mean luma (0-255) of frames every 0.25 s over the first 3 s."""
    p = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-t", f"{FIRST_S:.2f}", "-i", str(f), "-an", "-vf",
                        "fps=4,scale=270:-2,signalstats,metadata=print:key=lavfi.signalstats.YAVG",
                        "-f", "null", "-"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                       encoding="utf-8", errors="replace")
    ts = [float(x) for x in re.findall(r"pts_time:([\d.]+)", p.stderr)]
    ys = [float(x) for x in re.findall(r"YAVG=([\d.]+)", p.stderr)]
    return list(zip(ts, ys))


def _first_second_db(f: Path) -> float:
    s = _ff(["-t", "1", "-i", f, "-vn", "-af", "astats=measure_overall=RMS_level:measure_perchannel=none",
             "-f", "null", "-"])
    m = re.findall(r"RMS level dB:\s*(-?[\d.]+|-inf)", s)
    return float(m[-1]) if m and m[-1] != "-inf" else -120.0


def first_frames_sheet(parts: list[dict], outdir: Path) -> Path:
    """output/vertical/first_frames.png: frame 0 of every part, labelled."""
    from .covers import contact_sheet
    tmp = Path(tempfile.mkdtemp(prefix="ff_", dir=outdir))
    try:
        paths, labels = [], []
        for p in parts:
            png = tmp / f"p{p['n']}.png"
            _ff(["-i", outdir / p["file"], "-frames:v", "1", "-an", png])
            paths.append(png)
            labels.append(f"Part {p['n']} · {fmt_ts(p['dur'])} · {p['wpm']:.0f} wpm")
        return contact_sheet(paths, labels, outdir / "first_frames.png")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def review_parts(ep: Episode, m: dict) -> Path:
    outdir = Path(m["outdir"])
    step(f"Review part vertikal ({len(m['parts'])} part)")
    passes, fixes, warns, rows = [], [], [], []
    for p in m["parts"]:
        f = outdir / p["file"]
        if not f.is_file():
            fixes.append(f"Part {p['n']}: file {p['file']} tidak ada")
            continue
        dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                    str(f)], stdout=subprocess.PIPE, text=True).stdout.strip() or 0)
        L = loudness(f)
        lum = _first_lumas(f)
        dark = [(t, y) for t, y in lum if y < LUMA_MIN]
        cards = [x for x in p.get("first3", []) if x["kind"] in ("text", "black", "channel")]
        db1 = _first_second_db(f)
        wpm = p["words"] / (dur / 60) if dur else 0
        iss = []
        if dur > PART_MAX_S + 0.05:
            iss.append(f"durasi {fmt_ts(dur)} > 2:55")
        if dark:
            iss.append(f"3 detik pertama gelap (luma {min(y for _, y in dark):.0f} < {LUMA_MIN:.0f} "
                       f"di {', '.join(f'{t:.2f}s' for t, _ in dark[:4])})")
        if cards:
            iss.append("3 detik pertama berisi " + ", ".join(f"{x['kind']} ({x['key']})" for x in cards))
        if db1 < SILENCE_DB:
            iss.append(f"detik pertama hening ({db1:.0f} dB)")
        if not (WPM_LOW <= wpm <= WPM_HIGH):
            iss.append(f"tempo {wpm:.0f} wpm (batas {WPM_LOW}–{WPM_HIGH})")
        if abs(L["I"] - LUFS_TARGET) > LUFS_TOL:
            iss.append(f"loudness {L['I']:.1f} LUFS")
        if L["TP"] is None or L["TP"] > TP_MAX:
            iss.append(f"true peak {L['TP']} dBTP")
        size = f.stat().st_size / 1e6
        if size > 40:
            warns.append(f"Part {p['n']}: {size:.0f} MB (target 20–40 MB)")
        cover = f.with_name(f.stem + "_cover.jpg").exists()
        rows.append({**p, "dur": dur, "wpm": wpm, "I": L["I"], "TP": L["TP"], "db1": db1, "size": size,
                     "luma_min": min((y for _, y in lum), default=0), "issues": iss, "cover": cover})
        (fixes if iss else passes).append(f"Part {p['n']}: " + ("; ".join(iss) if iss else
                                          f"{fmt_ts(dur)}, {wpm:.0f} wpm, 3 dtk pertama terang (luma ≥ "
                                          f"{min((y for _, y in lum), default=0):.0f}), detik 1 {db1:.0f} dB"))
    sheet = first_frames_sheet([r for r in rows], outdir) if rows else None
    sheets = []
    for r in rows:
        f = outdir / r["file"]
        sheets += contact_sheets({"output": str(f), "srt": str(f.with_suffix(".srt")), "burned_subs": True,
                                  "vertical": True, "segments": []}, ep, prefix=f"review_sheet_part{r['n']}")
    crop_sheets = crop_maps({"output": str(outdir / "x.mp4"), "crops": [c for r in rows for c in r.get("crops", [])]})
    TB = thumbs_check(ep)
    (fixes if TB else passes).append("Thumbnail 16x9 + 9x16: " + ("ada" if not TB else "; ".join(TB)))

    rep = [f"# Review — part vertikal {m['base']}", "",
           f"{dt.datetime.now():%Y-%m-%d %H:%M} · {len(rows)} part · first frames: first_frames.png", "",
           "| Part | Durasi | Kata | WPM | Ukuran | LUFS / TP | Luma min 0–3 s | Detik 1 | Cover | Status |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        rep.append(f"| {r['n']} | {fmt_ts(r['dur'])} | {r['words']} | {r['wpm']:.0f} | {r['size']:.0f} MB | "
                   f"{r['I']:.1f} / {r['TP']:.1f} | {r['luma_min']:.0f} | {r['db1']:.0f} dB | "
                   f"{'✓' if r['cover'] else '✗'} | {'**' + '; '.join(r['issues']) + '**' if r['issues'] else 'OK'} |")
    rep += ["", "## Baris pertama / terakhir", ""]
    for r in rows:
        rep += [f"- **Part {r['n']}** ({r['first_beat']}–{r['last_beat']})",
                f"  - hook: {r['first_line']}", f"  - cliffhanger: {r['last_line']}"]
        if r.get("stand_ins"):
            rep.append("  - 3 detik pertama: " + ", ".join(f"{k} diganti gambar {v}" for k, v in r["stand_ins"].items()))
    rep += ["", "## Contact sheet", ""] + [f"- {x.name}" for x in sheets + crop_sheets]
    notes = outdir / f"review_visual_{m['base']}_parts.md"
    rep += ["", "### Cek visual", ""]
    rep += (notes.read_text(encoding="utf-8").strip().splitlines() if notes.exists()
            else [f"- (belum dicek — tulis temuan di {notes.name})"])
    rep += ["", "## Hasil", "", "**PASS**", ""] + [f"- {x}" for x in passes]
    rep += ["", "**PERINGATAN**", ""] + ([f"- {x}" for x in warns] or ["- tidak ada"])
    rep += ["", "**NEEDS FIX**", ""] + ([f"- {x}" for x in fixes] or ["- tidak ada"])
    path = outdir / "review_report.md"
    path.write_text("\n".join(rep) + "\n", encoding="utf-8")
    ok(f"Review: {path.relative_to(ROOT)} · {sheet.name if sheet else '-'} · {len(fixes)} NEEDS FIX, "
       f"{len(warns)} peringatan")
    return path


def review(ep: Episode, manifest: Path | None = None) -> Path:
    if manifest is None:
        cands = sorted(ep.cache.glob("render*.json"), key=lambda p: p.stat().st_mtime)
        if not cands:
            raise PipelineError(f"Belum ada render untuk direview. Jalankan dulu: build {ep.slug} {ep.ep}")
        manifest = cands[-1]
    m = json.loads(manifest.read_text(encoding="utf-8"))
    if m.get("kind") == "vertical_parts":
        return review_parts(ep, m)
    out = Path(m["output"])
    if not out.exists():
        raise PipelineError(f"Video tidak ada: {out}")
    step(f"Review {out.name}")
    passes, fixes, warns = [], [], []

    L = loudness(out)
    l_ok = abs(L["I"] - LUFS_TARGET) <= LUFS_TOL
    tp_ok = L["TP"] is not None and L["TP"] <= TP_MAX
    (passes if l_ok else fixes).append(f"Loudness {L['I']:.1f} LUFS (target {LUFS_TARGET:.0f} ±{LUFS_TOL:.0f})")
    (passes if tp_ok else fixes).append(f"True peak {L['TP']:.1f} dBTP (maks {TP_MAX:.0f})")

    B = bed_gap(m)
    if B:
        b_ok = BED_MIN_GAP <= B["gap"] <= BED_MAX_GAP
        (passes if b_ok else fixes).append(f"Bed di jeda {B['gap']:.1f} dB di bawah suara (batas {BED_MIN_GAP:.0f}–{BED_MAX_GAP:.0f})")

    W_ = wpm_by_part(ep, m)
    for w in W_:
        ok_ = WPM_LOW <= w["wpm"] <= WPM_HIGH
        (passes if ok_ else fixes).append(f"Tempo part {w['n']}: {w['wpm']:.0f} wpm ({w['words']} kata / "
                                          f"{fmt_ts(w['dur'])}; batas {WPM_LOW}–{WPM_HIGH})")
        if w["dur"] > PART_MAX_S + 0.05:
            fixes.append(f"Part {w['n']} {fmt_ts(w['dur'])} > 2:55 (batas YouTube Shorts)")

    LS = long_shots(m)
    if LS:
        warns.append(f"{len(LS)} shot gambar > {SHOT_WARN:.0f} s (peringatan saja)")
    else:
        passes.append(f"Tidak ada shot gambar > {SHOT_WARN:.0f} s")

    S = silences(m, out)
    bad_sil = [x for x in S if not x["why"]]
    (fixes if bad_sil else passes).append(f"Hening > {SILENCE_MIN:.0f} s tak disengaja: {len(bad_sil)}")

    V = video_gaps(m, out)
    bad_black = [x for x in V["black"] if not x["why"]]
    bad_freeze = [x for x in V["freeze"] if not x["why"]]
    (fixes if bad_black else passes).append(f"Layar hitam tak disengaja: {len(bad_black)}")
    (fixes if bad_freeze else passes).append(f"Gambar beku tak disengaja: {len(bad_freeze)}")

    T = subtitles(m)
    (fixes if T["issues"] else passes).append(f"Subtitle: {T['cues']} cue, {len(T['issues'])} masalah")
    vertical = bool(m.get("vertical"))
    C = chapters(ep, m) if not vertical else {"file": None, "stamps": [], "issues": []}
    if not vertical:
        (fixes if C["issues"] else passes).append(f"Chapter YouTube: {len(C['stamps'])} timestamp")
    parts = m.get("parts") or []
    PC = parts_check(m) if vertical and parts else []
    if PC:
        bad = [r for r in PC if r["issues"]]
        (fixes if bad else passes).append(f"Part IG/FB: {len(PC) - len(bad)}/{len(PC)} lolos cek "
                                          "(durasi ≤ 3 menit, loudness, true peak, hening, layar hitam)")
    TB = thumbs_check(ep)
    (fixes if TB else passes).append("Thumbnail 16x9 (1280x720, < 2 MB) + 9x16 (1080x1920): "
                                     + ("ada" if not TB else "; ".join(TB)))

    TH = threads_check(ep)
    if TH is not None:
        (fixes if TH["issues"] else passes).append(f"Threads: {TH['n']} thread, {len(TH['issues'])} masalah")

    info("Membuat contact sheet (1 frame / 4 s, subtitle ikut dibakar)")
    sheets = contact_sheets(m, ep)
    crop_sheets = crop_maps(m) if vertical else []

    r = [f"# Review — {out.name}", "",
         f"{dt.datetime.now():%Y-%m-%d %H:%M} · durasi {fmt_ts(m['total'])} · "
         f"{len(m['segments'])} segmen · {len(m['shots'])} shot", ""]
    r += ["## Loudness", "",
          f"- Integrated: **{L['I']:.1f} LUFS** (target {LUFS_TARGET:.0f} ±{LUFS_TOL:.0f}) — {'OK' if l_ok else 'PERLU DIPERBAIKI'}",
          f"- True peak: **{L['TP']:.1f} dBTP** (≤ {TP_MAX:.0f}) — {'OK' if tp_ok else 'PERLU DIPERBAIKI'}",
          f"- LRA: {L['LRA']:.1f} LU", ""]
    r += ["## Bed (musik + ambience)", ""]
    if B:
        r += [f"- Suara saat bicara: {B['voice']:.1f} LUFS (momentary, rata-rata energi)",
              f"- Musik+ambience di jeda: {B['bed']:.1f} LUFS ({B['pause_s']:.0f} s jeda diukur)",
              *([f"- Musik+ambience saat bicara (sesudah ducking, sebelum batas 6 dB): "
                 f"{B['under']:.1f} LUFS = {B['under'] - B['voice']:+.1f} dB dari suara"] if B.get("under") else []),
              f"- Jarak: **{B['gap']:.1f} dB** di bawah suara (batas {BED_MIN_GAP:.0f}–{BED_MAX_GAP:.0f} dB) — "
              f"{'OK' if BED_MIN_GAP <= B['gap'] <= BED_MAX_GAP else ('terlalu pelan' if B['gap'] > BED_MAX_GAP else 'terlalu keras')}", ""]
    else:
        r += ["- Tidak bisa diukur (stem musik/ambience tidak ada — render tanpa sound.yaml?)", ""]
    r += [f"## Shot gambar > {SHOT_WARN:.0f} s (peringatan, tidak diubah otomatis)", ""]
    r += [f"- {fmt_ts(s['start'])} · {s['src']} · {s['slot']:.1f} s"
          + (f" (dibagi {s['n']} shot/crop)" if s["n"] > 1 else "") for s in LS] or ["- tidak ada"]
    r += ["", f"## Hening > {SILENCE_MIN:.0f} s (di bawah {SILENCE_DB:.0f} dB)", ""]
    r += [f"- {fmt_ts(x['a'])}–{fmt_ts(x['b'])} ({x['b'] - x['a']:.1f} s): "
          + (f"disengaja — {x['why']}" if x["why"] else "**TIDAK DISENGAJA**") for x in S] or ["- tidak ada"]
    r += ["", "## Layar hitam / gambar beku", ""]
    rows = [("hitam", x) for x in V["black"]] + [("beku", x) for x in V["freeze"]]
    r += [f"- {k} {fmt_ts(x['a'])}–{fmt_ts(x['b'])} ({x['b'] - x['a']:.1f} s): "
          + (f"disengaja — {x['why']}" if x["why"] else "**TIDAK DISENGAJA**") for k, x in rows] or ["- tidak ada"]
    r += ["", "## Subtitle", "", f"- {T['cues']} cue di {Path(m['srt']).name}"]
    r += [f"- {i}" for i in T["issues"]] or ["- tidak ada tumpang tindih / cue terlalu cepat; tagline tidak ada di subtitle"]
    if not vertical:
        r += ["", "## Chapter YouTube", "", f"- dari {C['file']}:" if C["file"] else "- (tidak ada deskripsi)"]
        r += [f"  - {a} {b}" for a, b in C["stamps"]] + [f"- {i}" for i in C["issues"]]
    if parts:
        r += ["", "## Part Instagram/Facebook", ""]
        pc = {x["n"]: x for x in PC}
        for p in parts:
            c = pc.get(p["n"], {})
            r.append(f"- Part {p['n']}: **{fmt_ts(c.get('dur', p['dur']))}** ({fmt_ts(p['a'])}–{fmt_ts(p['b'])} dari "
                     f"video penuh) · " + (f"potong setelah {p['after']} ({p['why']})" if not p["last"] else "diakhiri outro")
                     + (f" · {c['I']:.1f} LUFS / {c['TP']:.1f} dBTP" if c.get("I") is not None else "")
                     + (" · cover ✓" if c.get("cover") else " · cover ✗")
                     + (" · **" + "; ".join(c["issues"]) + "**" if c.get("issues") else " · OK"))
    r += ["", "## Thumbnail", ""]
    from . import thumbs as _t
    for rr in _t.SIZES:
        tp = _t.path(ep, rr)
        if tp.exists():
            with Image.open(tp) as im:
                r.append(f"- thumbnail/{tp.name}: {im.size[0]}x{im.size[1]}, {tp.stat().st_size / 1e6:.2f} MB")
        else:
            r.append(f"- thumbnail/thumbnail_{rr}.jpg: **tidak ada**")
    if TH is not None:
        r += ["", "## Threads", ""]
        r += [f"- {t['bab']}: {len(t['posts'])} post, terpanjang {max(t['posts'])} karakter, {len(t['images'])} gambar"
              for t in TH["threads"]]
        r += [f"- **{i}**" for i in TH["issues"]]
    r += ["", "## Contact sheet (1 frame / 4 s, subtitle seperti tampil di video)", ""]
    r += [f"- {p.name}" for p in sheets]
    if crop_sheets:
        r += ["", "## Peta crop 9:16 (kuning = posisi awal, biru = akhir pan)", ""]
        r += [f"- {p.name}" for p in crop_sheets]
    # visual findings are written by a person/agent into review_visual.md next to the video and kept
    notes = out.parent / f"review_visual_{out.stem}.md"
    r += ["", "### Cek visual", ""]
    r += (notes.read_text(encoding="utf-8").strip().splitlines() if notes.exists()
          else [f"- (belum dicek — tulis temuan di {notes.name})"])
    r += [""]
    r += ["## Hasil", "", "**PASS**", ""] + [f"- {x}" for x in passes]
    r += ["", "**PERINGATAN**", ""] + ([f"- {x}" for x in warns] or ["- tidak ada"])
    r += ["", "**NEEDS FIX**", ""] + ([f"- {x}" for x in fixes] or ["- tidak ada"])
    path = out.parent / "review_report.md"
    path.write_text("\n".join(r) + "\n", encoding="utf-8")
    ok(f"Review: {path.relative_to(ROOT)} · {len(sheets)} contact sheet · "
       f"{len(fixes)} NEEDS FIX, {len(warns)} peringatan")
    return path


def cmd_review(ep: Episode, args) -> None:
    review(ep)
