"""`tts` command: edge-tts per beat + ffmpeg voice effects + SRT."""
from __future__ import annotations

import asyncio
import json
import math
import os
import struct
import wave

from .common import (ROOT, SAMPLE_RATE, Episode, PipelineError, atomic_out, info, ok, require_ffmpeg,
                     run, sha, step, warn)
from .timeline import build_timeline, total_duration, write_description, write_srt

FX_VERSION = 2
FINAL_FMT = f"aresample={SAMPLE_RATE},aformat=sample_fmts=s16:channel_layouts=mono"
EFFECT_FILTERS = {
    "none": "",
    # telephone: narrow band + compression + slight grit
    "phone": "highpass=f=350,lowpass=f=3200,acompressor=threshold=0.08:ratio=6:attack=5:release=80,"
             "volume=1.6,alimiter=limit=0.9",
    # cavernous echo; pad first so the tail is not cut off
    "echo": "apad=pad_dur=0.9,aecho=0.8:0.85:80|160|260:0.35|0.22|0.12",
    # whisper: thin and quiet
    "whisper": "highpass=f=650,treble=g=3,volume=0.55",
}


def _jobs(ep: Episode):
    jobs = []
    if ep.recap:
        jobs.append(("recap", ep.recap, ep.speaker("narrator"), None))
    for b in ep.beats:
        if b.text:
            jobs.append((b.key, b.text, ep.speaker(b), b.effect))
    out = []
    for key, text, ch, eff in jobs:
        effect = eff or ch.effect or "none"
        params = {"text": text, "voice": ch.voice, "rate": ch.rate, "pitch": ch.pitch,
                  "volume": ch.volume, "effect": effect, "fx": FX_VERSION}
        out.append({"key": key, "params": params, "hash": sha(params)})
    return out


async def _synth(params: dict, mp3_path, proxy=None, retries: int = 4) -> None:
    import edge_tts  # imported lazily so other commands work without it

    last = None
    for attempt in range(retries):
        try:
            tmp = atomic_out(mp3_path)
            comm = edge_tts.Communicate(params["text"], params["voice"], rate=params["rate"],
                                        pitch=params["pitch"], volume=params["volume"], proxy=proxy)
            await comm.save(str(tmp))
            if tmp.stat().st_size == 0:
                raise RuntimeError("edge-tts mengembalikan audio kosong")
            os.replace(tmp, mp3_path)
            return
        except Exception as e:  # network hiccups are common, back off and retry
            last = e
            await asyncio.sleep(1.5 * (attempt + 1))
    raise PipelineError(f"edge-tts gagal untuk teks: {params['text'][:60]}…\n  {type(last).__name__}: {last}")


def _dummy_audio(params: dict, path) -> None:
    """Offline stand-in: a quiet tone whose length approximates real speech (~14 chars/s)."""
    dur = max(1.0, len(params["text"]) / 14.0)
    n = int(dur * SAMPLE_RATE)
    freq = 140 + (len(params["text"]) % 6) * 20
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        frames = bytearray()
        for i in range(n):
            env = 0.5 * (1 - math.cos(math.pi * min(1, i / (0.3 * SAMPLE_RATE))))
            syl = 0.6 + 0.4 * math.sin(2 * math.pi * 4 * i / SAMPLE_RATE)
            v = int(7000 * env * syl * math.sin(2 * math.pi * freq * i / SAMPLE_RATE))
            frames += struct.pack("<h", v)
        w.writeframes(bytes(frames))


def _apply_effect(src, dst, effect: str) -> None:
    af = ",".join(f for f in (EFFECT_FILTERS.get(effect, ""), FINAL_FMT) if f)
    tmp = atomic_out(dst)
    run(["ffmpeg", "-y", "-i", src, "-af", af, "-ac", "1", "-c:a", "pcm_s16le", tmp],
        f"efek audio ({effect})")
    os.replace(tmp, dst)


def _beat_filter(ep: Episode, spec: str | None):
    if not spec:
        return None
    from .common import beat_key
    keys = {beat_key(s.strip()) for s in spec.split(",") if s.strip()}
    known = {b.key for b in ep.beats} | {"recap"}
    unknown = sorted(keys - known)
    if unknown:
        raise PipelineError(f"Beat tidak ada di script.yaml: {', '.join(unknown)}")
    return keys


def _gemini_jobs(ep: Episode, only):
    jobs = []
    if ep.recap:
        jobs.append(("recap", ep.recap, "narrator", None))
    for b in ep.beats:
        if b.text:
            jobs.append((b.key, b.text, b.speaker, b.effect))
    return [{"key": k, "text": t, "speaker": s, "effect": eff or ep.speaker(s).effect or "none"}
            for k, t, s, eff in jobs if only is None or k in only]


def cmd_tts(ep: Episode, args) -> None:
    require_ffmpeg()
    only = _beat_filter(ep, getattr(args, "beats", None))
    if ep.tts_engine == "gemini":
        if args.dummy:
            raise PipelineError("--dummy hanya untuk edge-tts (pakai --engine edge --dummy)")
        from . import gemini_tts
        from . import channel
        step(f"TTS {ep.slug} {ep.ep}  [Gemini]")
        try:
            ch = channel.for_episode(ep)
            if ch and ch.missing() and not getattr(args, "plan", False):  # once per channel; --force never redoes them
                channel.generate(ep, ch)
            gemini_tts.run(ep, _gemini_jobs(ep, only), args, _apply_effect, FX_VERSION)
        except ModuleNotFoundError as e:
            raise PipelineError(f"Modul belum terpasang ({e.name}): pip install -r requirements.txt")
        if only is None and not getattr(args, "plan", False):
            _finish(ep)
        return
    step(f"TTS {ep.slug} {ep.ep}" + ("  [MODE DUMMY — bukan suara asli]" if args.dummy else ""))
    raw_dir = ep.audio / "raw"
    raw_dir.mkdir(exist_ok=True)
    manifest_path = ep.audio / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}

    todo = []
    for job in _jobs(ep):
        if only is not None and job["key"] not in only:
            continue
        wav = ep.audio_path(job["key"])
        if not args.force and wav.exists() and manifest.get(job["key"]) == job["hash"]:
            continue
        if wav.exists() and not args.force:
            info(f"{job['key']}: teks/suara berubah → dibuat ulang")
        todo.append(job)
    total_jobs = len(_jobs(ep))
    info(f"{total_jobs - len(todo)} sudah ada, {len(todo)} akan dibuat")

    proxy = args.proxy or os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") or None

    async def worker(job, sem, idx):
        async with sem:
            key, params = job["key"], job["params"]
            if args.dummy:
                raw = raw_dir / f"{key}.dummy.wav"
                _dummy_audio(params, raw)
            else:
                raw = raw_dir / f"{key}.mp3"
                await _synth(params, raw, proxy)
            await asyncio.to_thread(_apply_effect, raw, ep.audio_path(key), params["effect"])
            # dummy audio is marked so that a later real run regenerates it
            manifest[key] = "dummy" if args.dummy else job["hash"]
            print(f"  [{idx}/{len(todo)}] {key}  ({params['voice']} {params['pitch']} {params['rate']}"
                  f"{'' if params['effect'] == 'none' else ', ' + params['effect']})", flush=True)

    async def main():
        sem = asyncio.Semaphore(max(1, args.workers))
        tasks = [asyncio.create_task(worker(j, sem, i + 1)) for i, j in enumerate(todo)]
        try:
            await asyncio.gather(*tasks)
        finally:
            manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    if todo:
        try:
            asyncio.run(main())
        except ModuleNotFoundError:
            raise PipelineError("Modul edge-tts belum terpasang: pip install -r requirements.txt")
    if only is None:
        _finish(ep)


def _finish(ep: Episode) -> None:
    segs = build_timeline(ep)
    srt = ep.output / f"{ep.ep}.srt"
    write_srt(segs, srt)
    write_description(ep, segs, ep.output / "description.txt")
    total = total_duration(segs)
    ok(f"Audio lengkap. Perkiraan durasi cerita: {int(total // 60)}m {int(total % 60)}s")
    ok(f"Subtitle: {srt.relative_to(ROOT)}")
    from .common import PART_MAX_S, WPM_HIGH, WPM_LOW, fmt_ts
    rows = {}
    for sg in segs:
        if sg.kind == "beat" and not sg.beat.long_only:
            r = rows.setdefault(sg.chapter, [sg.start, 0.0, 0])
            r[1] = sg.start + sg.slot
            r[2] += len(sg.text.split()) if sg.text else 0
    for ci, (a, b, w) in sorted(rows.items()):
        d = b - a
        wpm = w / (d / 60) if d else 0
        line = f"Part {ci + 1}: {fmt_ts(d)} · {w} kata · {wpm:.0f} wpm"
        if d > PART_MAX_S or not WPM_LOW <= wpm <= WPM_HIGH:
            warn(line + ("  > 2:55!" if d > PART_MAX_S else "") + ("" if WPM_LOW <= wpm <= WPM_HIGH
                                                                 else f"  (batas {WPM_LOW}–{WPM_HIGH} wpm)"))
        else:
            info(line)
