"""`shorts` command: vertical 1080x1920 cut of a beat range with burned-in subtitles."""
from __future__ import annotations

import os
import random

from .common import ROOT, Episode, PipelineError, atomic_out, info, ok, require_ffmpeg, run, sha, step, warn
from .render import TEXT_CARD_FADE, mix_audio, pick_bgm, render_shots, xfade_join
from .timeline import build_timeline, chunk_text, total_duration, write_narration
from . import visuals as V

W, H = 1080, 1920
MAX_LEN = 59.0


def cmd_shorts(ep: Episode, args) -> None:
    require_ffmpeg()
    r = {**ep.render, "crossfade": min(0.3, float(ep.render["crossfade"]))}
    beats = ep.parse_beat_range(args.beats)
    step(f"Short {ep.slug} {ep.ep} · beat {beats[0].id}–{beats[-1].id}")
    for b in beats:
        if b.visual == "image" and not ep.image_for(b):
            raise PipelineError(f"Gambar {b.image_from or b.key} belum ada.")

    hold = float(args.hold)
    segs = build_timeline(ep, beats=beats, final_hold=hold)
    total = total_duration(segs)
    if total > MAX_LEN:
        if not args.auto_trim:
            detail = "\n".join(f"    {s.beat.key}: {s.slot:.1f}s" for s in segs)
            raise PipelineError(f"Durasi {total:.1f}s > {MAX_LEN:.0f}s.\n{detail}\n"
                                "  Persempit --beats, atau tambah --auto-trim (buang beat dari awal).")
        while total > MAX_LEN and len(beats) > 1:
            beats = beats[1:]
            segs = build_timeline(ep, beats=beats, final_hold=hold)
            total = total_duration(segs)
        warn(f"Auto-trim: mulai dari beat {beats[0].id}")
        if total > MAX_LEN:
            raise PipelineError(f"Beat terakhir saja sudah {total:.1f}s — terlalu panjang untuk short.")
    info(f"Durasi short: {total:.1f}s, {len(segs)} beat (berakhir di beat {beats[-1].id})")

    # one shot per beat (beats in a short are short), subtle motion
    rnd = random.Random(f"short-{ep.slug}-{ep.ep}-{args.beats}")
    shots, last = [], None
    for s in segs:
        b = s.beat
        if b.visual == "black":
            shots.append({"kind": "black", "slot": s.slot})
        elif b.visual == "text_card":
            shots.append({"kind": "text", "slot": s.slot, "text": b.card_text or b.text,
                          "dir": "static", "fade": TEXT_CARD_FADE})
        else:
            d = rnd.choice([x for x in ("zoom_in", "zoom_out", "zoom_in") if x != last] or ["zoom_in"])
            last = d
            shots.append({"kind": "image", "slot": s.slot, "src": ep.image_for(b), "crop": b.crop,
                          "focus": b.focus, "shift": 0.0, "dir": d, "fg": args.fg_scale})

    composite = lambda img: V.vertical_composite(img, W * 2, H * 2, args.fg_scale)
    saved = ep.render
    ep.render = r
    try:
        clips = render_shots(ep, shots, W, H, args.force, zoom=0.07, composite=composite, label="short")
        work = ep.cache / "groups"
        work.mkdir(exist_ok=True)
        slots = [s["slot"] for s in shots]
        video = ep.cache / f"short_video_{sha([str(c) for c in clips] + slots)}.mp4"
        if args.force or not video.exists():
            xfade_join(clips, slots, video, r, work, final=False, force=args.force)
    finally:
        ep.render = saved

    # audio
    narration = ep.cache / "short_narration.wav"
    write_narration(segs, narration)
    mix = ep.cache / "short_mix.wav"
    mix_audio(narration, pick_bgm(ep, args), mix, total, r, fade_out=1.5)

    # subtitle overlays (PNG per cue)
    sub_dir = ep.cache / "short_subs"
    sub_dir.mkdir(exist_ok=True)
    overlays = []  # (png, start, end)
    size = int(args.sub_size)
    for s in segs:
        if not s.text or not s.audio_dur:
            continue
        chunks = chunk_text(s.text, 42)
        tot = sum(len(c) for c in chunks) or 1
        t = s.start
        for c in chunks:
            d = s.audio_dur * len(c) / tot
            png = sub_dir / f"{sha([c, size, V.find_font(ep.story, 'subtitle_font')])}.png"
            if not png.exists():
                V.subtitle_png(ep.story, c, W, H, H * 0.75, size).save(png)
            overlays.append((png, t, t + d))
            t += d
    if args.title:
        png = sub_dir / f"title_{sha([args.title])}.png"
        V.subtitle_png(ep.story, args.title.upper(), W, H, H * 0.14, 78, color=(255, 230, 0)).save(png)
        overlays.append((png, 0.0, total))

    inputs = ["-i", video, "-i", mix]
    parts, prev = [], "0:v"
    for i, (png, a, b) in enumerate(overlays):
        inputs += ["-i", png]
        lbl = f"o{i}"
        parts.append(f"[{prev}][{i + 2}:v]overlay=0:0:enable='between(t,{a:.3f},{b:.3f})'[{lbl}]")
        prev = lbl
    fade_st = max(0.0, total - 0.6)
    parts.append(f"[{prev}]fade=t=out:st={fade_st:.3f}:d=0.6,format=yuv420p[v]")
    parts.append(f"[1:a]afade=t=out:st={fade_st:.3f}:d=0.6[a]")
    first, last_id = beats[0].num or beats[0].key, beats[-1].num or beats[-1].key
    out = ep.output / f"short_{ep.ep}_b{first}-{last_id}.mp4"
    tmp = atomic_out(out)
    run(["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(parts), "-map", "[v]", "-map", "[a]",
         "-c:v", "libx264", "-preset", ep.render["preset"], "-crf", "20", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "192k", "-t", f"{total:.3f}", "-movflags", "+faststart", tmp],
        "render short")
    os.replace(tmp, out)
    ok(f"Short selesai: {out.relative_to(ROOT)} ({total:.1f}s)")
