"""`repace`: speed up existing TTS clips without new TTS requests (pitch-preserving atempo).

Works from the raw model output (audio/gemini/raw/<key>.wav), so the effects (phone/echo/whisper) are
re-applied after the tempo change and an echo tail is not sped up. Leading/trailing silence of each
clip is trimmed (keeps 60 ms / 120 ms) because Gemini pads every clip, and pauses *inside* a clip longer
than --max-gap (0.5 s, before the tempo change) are shortened to it — the old slow styles ("jeda panjang")
left 1-2 s gaps mid-line. The originals are never touched:
the first run copies the effect-applied clips to audio/gemini/_orig/ as a backup.

    python horror.py repace juru-kunci 1 --tempo 1.2 --max-gap 0.8   # all beats (ep01 final setting)
    python horror.py repace juru-kunci 1 --tempo 1.2 --beats b041,b042
    python horror.py repace juru-kunci 1 --tempo 1.25 --sample b008   # one clip → output/repace_sample_*.wav

Afterwards script.yaml gets `tts: {locked: true}` so `tts` never regenerates these clips (which would
spend Gemini quota because the default style changed).
"""
from __future__ import annotations

import json
import os
import shutil

from .common import ROOT, Episode, PipelineError, atomic_out, info, ok, probe_duration, run, step, warn

TRIM = ("silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.06,"
        "areverse,silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.12,areverse")


def tempo_filter(tempo: float) -> str:
    if not 0.5 <= tempo <= 2.0:
        raise PipelineError("--tempo harus 0.5–2.0 (setelan ep01 final: 1.2)")
    return f"atempo={tempo:.4f}"


def cmd_repace(ep: Episode, args) -> None:
    from .tts import EFFECT_FILTERS, FINAL_FMT
    tempo = float(args.tempo)
    step(f"Re-pace {ep.slug} {ep.ep} · atempo {tempo} (pitch tetap) + potong hening awal/akhir")
    raw_dir = ep.audio_dir / "raw"
    orig_dir = ep.audio_dir / "_orig"
    keys = [b.key for b in ep.beats if b.text]
    if ep.recap:
        keys.insert(0, "recap")
    if args.beats:
        want = {ep.get_beat(x.strip()).key for x in args.beats.split(",") if x.strip()}
        keys = [k for k in keys if k in want]
    if args.sample:
        keys = [ep.get_beat(args.sample).key]
    effects = {"recap": ep.speaker("narrator").effect}
    effects.update({b.key: b.effect or ep.speaker(b).effect or "none" for b in ep.beats})
    done, before, after, missing = 0, 0.0, 0.0, []
    log_path = ep.audio_dir / "repace.json"
    log = json.loads(log_path.read_text(encoding="utf-8")) if log_path.exists() else {}
    for k in keys:
        raw = raw_dir / f"{k}.wav"
        clip = ep.audio_path(k)
        src = raw if raw.exists() else (orig_dir / f"{k}.wav" if (orig_dir / f"{k}.wav").exists() else clip)
        if not src.exists():
            missing.append(k)
            continue
        if not args.sample and clip.exists() and not (orig_dir / f"{k}.wav").exists():
            orig_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(clip, orig_dir / f"{k}.wav")        # one-time backup of the original clip
        ref = orig_dir / f"{k}.wav" if (orig_dir / f"{k}.wav").exists() else clip
        before += probe_duration(ref) if ref.exists() else 0.0
        fx = effects.get(k, "none") if src == raw else "none"   # non-raw sources already carry the effect
        gap = float(getattr(args, "max_gap", 0.5) or 0)
        squeeze = f"silenceremove=stop_periods=-1:stop_duration={gap:.2f}:stop_threshold=-42dB" if gap > 0 else ""
        chain = ",".join(x for x in (TRIM, squeeze, tempo_filter(tempo), EFFECT_FILTERS.get(fx, ""), FINAL_FMT)
                         if x)
        dst = (ep.output / f"repace_sample_{k}_{tempo:g}.wav") if args.sample else clip
        tmp = atomic_out(dst)
        run(["ffmpeg", "-y", "-i", src, "-af", chain, "-ac", "1", "-c:a", "pcm_s16le", tmp], f"repace {k}")
        os.replace(tmp, dst)
        after += probe_duration(dst)
        if not args.sample:
            log[k] = {"tempo": tempo, "max_gap": gap, "source": src.name if src == raw else f"{src.parent.name}/{src.name}"}
        done += 1
    if missing:
        warn(f"Tidak ada klip untuk: {', '.join(missing[:10])}{' ...' if len(missing) > 10 else ''}")
    if args.sample:
        ok(f"Contoh: output/repace_sample_{keys[0]}_{tempo:g}.wav — dengarkan dulu sebelum semua klip")
        return
    log_path.write_text(json.dumps(log, indent=2), encoding="utf-8")
    _lock(ep)
    ok(f"{done} klip: {before:.0f}s → {after:.0f}s ({(1 - after / before) * 100 if before else 0:.0f}% lebih pendek)"
       f" · cadangan asli di {orig_dir.relative_to(ROOT)}")
    info("script.yaml: tts.locked = true (tts tidak akan membuat ulang klip ini)")


def _lock(ep: Episode) -> None:
    p = ep.dir / "script.yaml"
    text = p.read_text(encoding="utf-8")
    if ep.tts_locked:
        return
    line = "tts:\n  locked: true   # clips re-paced with `repace`; tts must not regenerate them\n"
    lines = text.splitlines(keepends=True)
    for i, ln in enumerate(lines):  # insert after the `episode:` line to keep the header readable
        if ln.startswith("episode:"):
            lines.insert(i + 1, line)
            break
    else:
        lines.insert(0, line)
    p.write_text("".join(lines), encoding="utf-8")
