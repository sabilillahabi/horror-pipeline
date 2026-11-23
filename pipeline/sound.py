"""Sound design layer: asset import (`sound-import`) and the music/ambience/sfx mix used by `build`.

stories/<slug>/sound_assets.yaml  → which source file becomes assets/sound/<key>.mp3
stories/<slug>/episodes/epXX/sound.yaml → where each sound plays in the episode
"""
from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
from pathlib import Path

import yaml

from .common import (ASSETS, AUDIO_EXTS, Episode, PipelineError, atomic_out, filter_script_flag, info, ok, run,
                     step, warn)

SOUND_DIR = ASSETS / "sound"
FMT = "aformat=sample_rates=48000:sample_fmts=fltp:channel_layouts=stereo"
XFADE = 1.5            # ambience crossfade between segments (s)
DUCK_ATTACK = 0.25     # music ramps down this long before a line starts
DUCK_RELEASE = 0.7     # ...and back up this long after it ends
MUTE_RAMP = 0.3
TARGET_LUFS = -14.0
TARGET_TP = -1.5      # dBTP (ceiling asked for: -1)
HEADROOM = 6.0        # music+ambience stay at least this many dB under the voice

# Per-asset processing at import time (beyond plain conversion). Ambience is always looped.
KENTONGAN_HITS = [0.0, 0.6, 1.2, 2.4, 3.0, 3.6]   # 3 hits 0.6 s apart, 1.2 s gap, 3 hits
SPECIAL = {
    "sfx_kentongan": "kentongan",
    "sfx_humming_female": "behind_door",
}


def _load_yaml(p: Path) -> dict:
    try:
        return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        raise PipelineError(f"YAML tidak valid di {p}:\n{e}")


def _duration(p: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                          str(p)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        return float(out.stdout.strip())
    except ValueError:
        raise PipelineError(f"Tidak bisa membaca durasi {p}: {out.stderr.strip()[:200]}")


# ================================================================== import
def _find_source(value: str, files: list[Path]) -> Path | None:
    value = str(value).strip()
    m = re.search(r"(\d+)\s*$", value)
    if m:  # Pixabay slug: match the trailing numeric id
        rid = re.compile(rf"(^|[^0-9]){m.group(1)}$")
        hits = [f for f in files if rid.search(f.stem)]
    else:  # a title, e.g. "EBB - Density & Time": file name starts with it (or its first word)
        v = value.lower()
        hits = [f for f in files if f.stem.lower().startswith(v)]
        if not hits:
            first = re.split(r"\s|-", v)[0]
            hits = [f for f in files if first and f.stem.lower().startswith(first)]
    return max(hits, key=lambda f: f.stat().st_mtime) if hits else None


def _process(src: Path, dst: Path, recipe: str | None) -> None:
    enc = ["-ar", "48000", "-c:a", "libmp3lame", "-q:a", "2"]
    tmp = atomic_out(dst)
    if recipe is None:
        if src.suffix.lower() == ".mp3":
            shutil.copy2(src, tmp)
        else:
            run(["ffmpeg", "-y", "-i", src, *enc, tmp], f"konversi {src.name}")
    elif recipe == "loop":
        d = _duration(src)
        xf = round(min(2.0, d * 0.1), 3)
        # body = [xf, end]; its last xf seconds crossfade into the head [0, xf], so the end flows
        # straight back into the start (position xf) when the file repeats
        fc = (f"[0:a]{FMT},asplit[a][b];[a]atrim=start={xf},asetpts=PTS-STARTPTS[body];"
              f"[b]atrim=end={xf},asetpts=PTS-STARTPTS[head];"
              f"[body][head]acrossfade=d={xf}:c1=qsin:c2=qsin[out]")
        run(["ffmpeg", "-y", "-i", src, "-filter_complex", fc, "-map", "[out]", *enc, tmp],
            f"loop {src.name}")
    elif recipe == "kentongan":
        n = len(KENTONGAN_HITS)
        hits = "".join(f"[h{i}]" for i in range(n))
        fc = (f"[0:a]{FMT},silenceremove=start_periods=1:start_threshold=-50dB,asplit={n}{hits};"
              + ";".join(f"[h{i}]adelay={int(t * 1000)}:all=1[d{i}]" for i, t in enumerate(KENTONGAN_HITS))
              + ";" + "".join(f"[d{i}]" for i in range(n))
              + f"amix=inputs={n}:normalize=0:duration=longest,"
              "aecho=0.8:0.6:45|90:0.22|0.12,alimiter=limit=0.95[out]")
        run(["ffmpeg", "-y", "-i", src, "-filter_complex", fc, "-map", "[out]", *enc, tmp],
            "pola kentongan")
    elif recipe == "behind_door":
        # -2 semitones (tempo kept), roomy reverb, then low-pass so it sounds muffled through a door
        af = (f"{FMT},rubberband=pitch={2 ** (-2 / 12):.5f},apad=pad_dur=0.6,"
              "aecho=0.8:0.6:55|120:0.32|0.2,lowpass=f=2600,alimiter=limit=0.95")
        run(["ffmpeg", "-y", "-i", src, "-af", af, *enc, tmp], "humming di balik pintu")
    else:
        raise PipelineError(f"Resep tidak dikenal: {recipe}")
    os.replace(tmp, dst)


def cmd_sound_import(ep: Episode, args) -> int:
    path = ep.story_dir / "sound_assets.yaml"
    if not path.exists():
        raise PipelineError(f"Tidak ada {path}")
    src_dir = Path(args.source).expanduser() if args.source else Path.home() / "Downloads"
    if not src_dir.is_dir():
        raise PipelineError(f"Folder sumber tidak ada: {src_dir}")
    step(f"Import aset suara → assets/sound  (sumber: {src_dir})")
    files = [f for f in src_dir.rglob("*") if f.is_file() and f.suffix.lower() in AUDIO_EXTS]
    SOUND_DIR.mkdir(parents=True, exist_ok=True)
    missing, done, kept = [], 0, 0
    for cat, entries in _load_yaml(path).items():
        for key, value in (entries or {}).items():
            dst = SOUND_DIR / f"{key}.mp3"
            src = _find_source(value, files)
            if src is None:
                missing.append((key, value))
                continue
            if dst.exists() and not args.force and dst.stat().st_mtime >= src.stat().st_mtime:
                kept += 1
                continue
            recipe = SPECIAL.get(key) or ("loop" if cat == "ambience" else None)
            _process(src, dst, recipe)
            done += 1
            print(f"  {src.name}  →  assets/sound/{dst.name}" + (f"  [{recipe}]" if recipe else ""))
    ok(f"{done} aset diproses, {kept} sudah ada")
    if missing:
        warn(f"{len(missing)} aset tidak ditemukan di {src_dir}:")
        for key, value in missing:
            print(f"    {key:<22} {value}")
    return 0


# ================================================================== mix
def load_config(ep: Episode) -> dict | None:
    p = ep.dir / "sound.yaml"
    return _load_yaml(p) if p.exists() else None


def _asset(name: str, missing: set) -> Path | None:
    p = SOUND_DIR / f"{name}.mp3"
    if p.exists():
        return p
    missing.add(name)
    return None


def _merge(iv: list[tuple[float, float]], gap: float) -> list[tuple[float, float]]:
    out = []
    for a, b in sorted(iv):
        if out and a - out[-1][1] < gap:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def _env(iv, up: float, down: float) -> str:
    """Sum of trapezoids: 0 outside each interval, 1 inside, linear ramps of `up`/`down` seconds."""
    terms = [f"min(clip((t-{a - up:.3f})/{up},0,1),clip(({b + down:.3f}-t)/{down},0,1))" for a, b in iv]
    return "+".join(terms) or "0"


def _beat_index(ep: Episode, ref: str, where: str) -> int:
    b = ep.resolve_ref(str(ref))
    if b is None:
        raise PipelineError(f"sound.yaml ({where}): beat '{ref}' tidak ada di script.yaml")
    return next(i for i, x in enumerate(ep.beats) if x is b)


def _stems(ep: Episode, segs, cfg: dict, total: float, work: Path) -> dict:
    """Render music, ambience and sfx as separate float stems (stereo, `total` long)."""
    order = {b.key: i for i, b in enumerate(ep.beats)}
    beat_segs = {s.beat.key: s for s in segs if s.kind == "beat"}
    missing: set = set()
    inputs: list = []
    chains: list = []
    groups = {"music": [], "amb": [], "sfx": []}

    def new_input(path, loop=False):
        inputs.extend((["-stream_loop", "-1"] if loop else []) + ["-i", str(path)])
        return inputs.count("-i") - 1

    # ---- music bed: ducked under voice, muted on selected beats
    m = cfg.get("music") or {}
    if m.get("file") and (p := _asset(m["file"], missing)):
        voice_iv = _merge([(s.start, s.start + s.audio_dur) for s in segs if s.audio and s.audio_dur > 0],
                          DUCK_ATTACK + DUCK_RELEASE + 0.1)
        mute_iv = []
        for ref in m.get("mute_on_beats") or []:
            k = ep.beats[_beat_index(ep, ref, "music.mute_on_beats")].key
            if k in beat_segs:
                s = beat_segs[k]
                mute_iv.append((s.start, s.start + s.slot))
        mute_iv = _merge(mute_iv, 2 * MUTE_RAMP + 0.05)
        g = 10 ** (float(m.get("duck_under_voice", -8)) / 20)
        gain = (f"max(0,(1-{1 - g:.5f}*({_env(voice_iv, DUCK_ATTACK, DUCK_RELEASE)}))"
                f"*(1-({_env(mute_iv, MUTE_RAMP, MUTE_RAMP)})))")
        fi, fo = float(m.get("fade_in", 3)), float(m.get("fade_out", 4))
        i = new_input(p, loop=True)
        chains.append(f"[{i}:a]{FMT},atrim=0:{total:.3f},asetpts=PTS-STARTPTS,"
                      f"volume={float(m.get('vol', -24))}dB,volume=volume='{gain}':eval=frame,"
                      f"afade=t=in:d={fi},afade=t=out:st={max(0.0, total - fo):.3f}:d={fo}[music0]")
        groups["music"].append("[music0]")

    # ---- ambience beds over beat ranges, crossfaded
    for n, a in enumerate(cfg.get("ambience") or []):
        i0 = _beat_index(ep, a["from"], f"ambience #{n + 1}")
        i1 = _beat_index(ep, a["to"], f"ambience #{n + 1}")
        cover = [s for k, s in beat_segs.items() if i0 <= order[k] <= i1]
        if not cover or (p := _asset(a["file"], missing)) is None:
            continue
        start = max(0.0, min(s.start for s in cover) - XFADE / 2)
        end = min(total, max(s.start + s.slot for s in cover) + XFADE / 2)
        dur = end - start
        fades = []
        if start > 0 or (segs and segs[0].kind == "lead"):  # cold open: ambience fades in over the black
            fades.append(f"afade=t=in:d={min(XFADE, dur / 2):.3f}")
        if end < total:
            fades.append(f"afade=t=out:st={max(0.0, dur - XFADE):.3f}:d={min(XFADE, dur / 2):.3f}")
        i = new_input(p, loop=True)
        chains.append(f"[{i}:a]{FMT},atrim=0:{dur:.3f},asetpts=PTS-STARTPTS,volume={float(a.get('vol', -24))}dB,"
                      + "".join(f"{f}," for f in fades) + f"adelay={int(start * 1000)}:all=1[amb{n}]")
        groups["amb"].append(f"[amb{n}]")

    # ---- one-shot sfx
    for ref, sx in (cfg.get("sfx") or {}).items():
        k = ep.beats[_beat_index(ep, ref, "sfx")].key
        if k not in beat_segs or (p := _asset(sx["file"], missing)) is None:
            continue
        s = beat_segs[k]
        at = sx.get("at", "start")
        if at == "start":
            t = s.start
        elif at == "end":
            t = s.start + (s.audio_dur if s.audio_dur > 0 else s.slot)
        else:
            t = s.start + float(at)
        i = new_input(p)
        chains.append(f"[{i}:a]{FMT},volume={float(sx.get('vol', 0))}dB,adelay={int(t * 1000)}:all=1[sfx_{k}]")
        groups["sfx"].append(f"[sfx_{k}]")

    for name in sorted(missing):
        warn(f"Aset suara tidak ada: assets/sound/{name}.mp3 (dilewati; jalankan sound-import)")

    outs, maps = {}, []
    for name, labels in groups.items():
        if labels:
            chains.append("".join(labels) + f"amix=inputs={len(labels)}:duration=longest:normalize=0:"
                          f"dropout_transition=0,apad=whole_dur={total:.3f},atrim=0:{total:.3f}[{name}]")
        else:
            chains.append(f"aevalsrc=0|0:s=48000:d={total:.3f},{FMT}[{name}]")
        outs[name] = work / f"stem_{name}.wav"
        maps += ["-map", f"[{name}]", "-c:a", "pcm_f32le", str(outs[name])]
    script = work / "sound_graph.txt"
    script.write_text(";".join(chains), encoding="utf-8")
    run(["ffmpeg", "-y", *inputs, filter_script_flag(), script, *maps], "render stem suara")
    outs["tracks"] = sum(len(v) for v in groups.values())
    return outs


def _momentary(path: Path) -> list[tuple[float, float]]:
    """EBU R128 momentary loudness every 100 ms: [(t, LUFS)]."""
    p = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af",
                        "aformat=channel_layouts=stereo,ebur128", "-f", "null", "-"],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
                       errors="replace")
    pts = re.findall(r"t:\s*([\d.]+)\s+TARGET:.*?M:\s*(-?[\d.]+|-?inf|nan)", p.stderr)
    return [(float(t), float(v) if v[-1].isdigit() else -120.0) for t, v in pts]


def _emean(vals: list[float]) -> float:
    """Energy mean of dB values."""
    if not vals:
        return -120.0
    return 10 * math.log10(max(1e-12, sum(10 ** (v / 10) for v in vals) / len(vals)))


def _psum(*dbs: float) -> float:
    return 10 * math.log10(max(1e-12, sum(10 ** (d / 10) for d in dbs)))


def measure(segs, narration: Path, stems: dict) -> dict:
    """Per spoken line: voice, music and ambience loudness (energy mean of momentary LUFS)."""
    M = {k: _momentary(p) for k, p in (("voice", narration), ("music", stems["music"]), ("amb", stems["amb"]))}
    lines = []
    for s in segs:
        if s.kind != "beat" or not s.audio or s.audio_dur < 0.8:
            continue
        # momentary windows are 400 ms long: stay clear of the duck ramps at the edges
        a, b = s.start + 0.4 + DUCK_ATTACK, s.start + s.audio_dur - 0.1
        if b - a < 0.2:
            a, b = s.start + 0.4, s.start + s.audio_dur
        lv = {k: _emean([v for t, v in M[k] if a <= t <= b]) for k in M}
        lv["bed"] = _psum(lv["music"], lv["amb"])
        lines.append({"key": s.beat.key, "start": s.start, "end": s.start + s.audio_dur, "a": a, "b": b, **lv})
    overall = {k: _emean([v for t, v in M[k] if any(l["a"] <= t <= l["b"] for l in lines)]) for k in M}
    return {"lines": lines, "overall": overall}


def report(levels: dict, label: str) -> None:
    o, L = levels["overall"], levels["lines"]
    info(f"[{label}] relatif suara saat narasi: musik {o['music'] - o['voice']:+.1f} dB · ambience "
         f"{o['amb'] - o['voice']:+.1f} dB · musik+ambience {_psum(o['music'], o['amb']) - o['voice']:+.1f} dB")
    if L:
        w = max(L, key=lambda l: l["bed"] - l["voice"])
        info(f"[{label}] paling dekat ke suara: {w['key']} (musik {w['music'] - w['voice']:+.1f}, ambience "
             f"{w['amb'] - w['voice']:+.1f}, gabungan {w['bed'] - w['voice']:+.1f} dB)")


def headroom_env(levels: dict) -> tuple[str, list[str]]:
    """Volume expression for the bed: down wherever music+ambience come within HEADROOM dB of the voice."""
    terms, limited = [], []
    for l in levels["lines"]:
        over = l["bed"] - (l["voice"] - HEADROOM)
        if over > 0.05:
            g = 10 ** (-over / 20)
            limited.append(f"{l['key']} -{over:.1f}")
            a, b = l["start"], l["end"]
            terms.append(f"{1 - g:.5f}*min(clip((t-{a - 0.25:.3f})/0.25,0,1),clip(({b + 0.25:.3f}-t)/0.25,0,1))")
    return (f"max(0.05,1-({'+'.join(terms)}))" if terms else "1"), limited


def mix(ep: Episode, segs, narration: Path, out: Path, total: float) -> dict:
    cfg = load_config(ep) or {}
    work = out.parent
    stems = _stems(ep, segs, cfg, total, work)
    info(f"Lapisan suara: {stems['tracks']} track di bawah narasi")
    levels = measure(segs, narration, stems)
    report(levels, "sound.yaml")

    env, limited = headroom_env(levels)
    if limited:
        info(f"Musik+ambience dibatasi agar ≥{HEADROOM:.0f} dB di bawah suara di {len(limited)} beat: "
             + ", ".join(limited[:14]) + (" ..." if len(limited) > 14 else ""))
    else:
        info(f"Musik+ambience di semua beat sudah ≥{HEADROOM:.0f} dB di bawah suara")

    pre = work / "sound_premix.wav"
    graph = (f"[0:a]{FMT}[v];[1:a][2:a]amix=inputs=2:normalize=0,volume=volume='{env}':eval=frame[bed];"
             f"[v][bed][3:a]amix=inputs=3:duration=first:normalize=0:dropout_transition=0[mix]")
    script = work / "sound_graph_final.txt"
    script.write_text(graph, encoding="utf-8")
    tmp = atomic_out(pre)
    run(["ffmpeg", "-y", "-i", narration, "-i", stems["music"], "-i", stems["amb"], "-i", stems["sfx"],
         filter_script_flag(), script, "-map", "[mix]", "-t", f"{total:.3f}", "-c:a", "pcm_f32le", tmp],
        "mix lapisan suara")
    os.replace(tmp, pre)
    if limited:  # report the bed as it ends up in the mix
        bed_env = work / "stem_check.wav"
        for name in ("music", "amb"):
            run(["ffmpeg", "-y", "-i", stems[name], "-af", f"volume=volume='{env}':eval=frame",
                 "-c:a", "pcm_f32le", bed_env.with_name(f"stem_{name}_lim.wav")], "cek stem")
        levels = measure(segs, narration, {"music": bed_env.with_name("stem_music_lim.wav"),
                                           "amb": bed_env.with_name("stem_amb_lim.wav")})
        report(levels, "setelah batas")
    _loudnorm(pre, out)
    return levels


def _loudnorm(src: Path, out: Path) -> None:
    ln = f"loudnorm=I={TARGET_LUFS}:TP={TARGET_TP}:LRA=11"
    p = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(src), "-af", f"{ln}:print_format=json",
                        "-f", "null", "-"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                       encoding="utf-8", errors="replace")
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", p.stderr)
    if p.returncode or not m:
        raise PipelineError(f"loudnorm (ukur) gagal:\n{p.stderr[-800:]}")
    d = json.loads(m.group(0))
    af = (f"{ln}:measured_I={d['input_i']}:measured_TP={d['input_tp']}:measured_LRA={d['input_lra']}"
          f":measured_thresh={d['input_thresh']}:offset={d['target_offset']}:linear=true,"
          "aresample=48000")
    tmp = atomic_out(out)
    run(["ffmpeg", "-y", "-i", src, "-af", af, "-ac", "2", "-c:a", "pcm_s16le", tmp], "normalisasi loudness")
    os.replace(tmp, out)
    info(f"Loudness: {float(d['input_i']):.1f} → {TARGET_LUFS} LUFS")
