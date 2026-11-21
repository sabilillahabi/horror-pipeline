"""`build` command: Ken Burns clips → crossfaded video → music ducking → final mux."""
from __future__ import annotations

import math
import os
import random
import shutil
from pathlib import Path

from .common import (ASSETS, AUDIO_EXTS, ROOT, Episode, PipelineError, atomic_out, file_sig, fmt_ts,
                     info, ok, require_ffmpeg, run, sha, step)
from .common import quantize
from .timeline import (Segment, build_timeline, structure, total_duration, write_description,
                       write_narration, write_srt)
from . import channel as C
from . import sound
from . import visuals as V

TEXT_CARD_FADE = 0.6  # seconds of fade in/out on text cards
DIRECTIONS = ["zoom_in", "pan_right", "zoom_out", "pan_left", "zoom_in", "pan_up", "zoom_out", "pan_down"]


# ---------------------------------------------------------------- Ken Burns
def kb_expr(direction: str, n: int, amount: float):
    """zoompan expressions. `on` = output frame index, p goes 0→1 across the shot."""
    p = f"(on/{max(1, n - 1)})"
    # smoothstep easing keeps starts/ends gentle
    e = f"({p}*{p}*(3-2*{p}))"
    a = amount
    cx, cy = "(iw-iw/zoom)/2", "(ih-ih/zoom)/2"
    if direction == "zoom_in":
        return f"1+{a}*{e}", cx, cy
    if direction == "zoom_out":
        return f"1+{a}*(1-{e})", cx, cy
    z = f"{1 + a}"
    if direction == "pan_right":
        return z, f"(iw-iw/zoom)*{e}", cy
    if direction == "pan_left":
        return z, f"(iw-iw/zoom)*(1-{e})", cy
    if direction == "pan_up":
        return z, cx, f"(ih-ih/zoom)*(1-{e})"
    if direction == "pan_down":
        return z, cx, f"(ih-ih/zoom)*{e}"
    if direction == "subtle":
        return f"1+{a * 0.35}*{e}", cx, cy
    return "1", "0", "0"


def render_clip(still: Path | None, out: Path, dur: float, direction: str, r: dict,
                w: int, h: int, zoom: float | None = None, fade: float = 0.0,
                slot: float | None = None) -> None:
    """Render one shot. `fade` > 0: fade in from black at the start and out to black by `slot`
    (the crossfade tail after `slot` then stays black)."""
    fps = int(r["fps"])
    n = max(1, round(dur * fps))
    post = ""
    if fade > 0:
        slot = dur if slot is None else slot
        f = min(fade, slot / 3)
        post += f",fade=t=in:st=0:d={f:.3f},fade=t=out:st={max(0.0, slot - f):.3f}:d={f:.3f}"
    post += ",format=yuv420p"  # grain is added once, in the final join pass
    tmp = atomic_out(out)
    common_out = ["-frames:v", n, "-r", fps, "-c:v", "libx264", "-preset", r["clip_preset"], "-crf", "18",
                  "-pix_fmt", "yuv420p", "-an", tmp]
    if still is None:  # plain black
        run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=black:s={w}x{h}:r={fps}",
             "-vf", post.lstrip(","), *common_out], "render klip hitam")
    else:
        z, x, y = kb_expr(direction, n, r["zoom"] if zoom is None else zoom)
        vf = f"zoompan=z='{z}':x='{x}':y='{y}':d={n}:s={w}x{h}:fps={fps}{post}"
        run(["ffmpeg", "-y", "-i", still, "-vf", vf, *common_out], f"render klip {out.name}")
    os.replace(tmp, out)


def save_still(img, path: Path, w: int, h: int, scale: int = 2) -> Path:
    """Stills are prepared at 2× output size so zoompan's integer rounding doesn't jitter."""
    if not path.exists():
        img = V.cover(img, w * scale, h * scale)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.stem + ".part.jpg")
        img.save(tmp, quality=93)
        os.replace(tmp, path)
    return path


# ---------------------------------------------------------------- crossfade join
def xfade_join(clips: list[Path], slots: list[float], out: Path, r: dict, work: Path,
               final: bool, force: bool = False) -> None:
    """Join clips (each `slot + crossfade` long) so clip k starts exactly at sum(slots[:k])."""
    D = float(r["crossfade"])
    fps = int(r["fps"])
    r.setdefault("_size", (int(r["width"]), int(r["height"])))
    chunk = max(2, int(r["chunk_size"]))
    if len(clips) > chunk:
        groups, gslots = [], []
        for i in range(0, len(clips), chunk):
            cs, ss = clips[i:i + chunk], slots[i:i + chunk]
            gp = work / f"group_{sha([str(c) for c in cs] + ss + [D])}.mp4"
            if force or not gp.exists():
                info(f"Menggabung grup {i // chunk + 1}/{math.ceil(len(clips) / chunk)}")
                xfade_join(cs, ss, gp, r, work, final=False, force=force)
            groups.append(gp)
            gslots.append(sum(ss))
        return xfade_join(groups, gslots, out, r, work, final, force)

    inputs, parts = [], []
    for i, c in enumerate(clips):
        inputs += ["-i", c]
        parts.append(f"[{i}:v]settb=AVTB,fps={fps},format=yuv420p[v{i}]")
    if len(clips) == 1:
        parts.append("[v0]null[out]")
    elif D <= 0:
        parts.append("".join(f"[v{i}]" for i in range(len(clips))) + f"concat=n={len(clips)}:v=1:a=0[out]")
    else:
        prev, offset = "v0", 0.0
        for i in range(1, len(clips)):
            offset += slots[i - 1]
            label = "out" if i == len(clips) - 1 else f"x{i}"
            parts.append(f"[{prev}][v{i}]xfade=transition=fade:duration={D}:offset={offset:.4f}[{label}]")
            prev = label
    grain = int(r.get("grain", 0) or 0)
    if final and grain:
        parts[-1] = parts[-1][: parts[-1].rindex("[out]")] + "[pre]"
        # coarse film grain: noise at half resolution, upscaled and overlay-blended.
        # Much cheaper to encode than per-pixel noise and looks more like film.
        w, h = r["_size"]
        parts.append(f"color=c=gray:s={w // 2}x{h // 2}:r={fps},noise=alls=30:allf=t,"
                     f"scale={w}:{h},format=yuv420p[grain]")
        parts.append(f"[pre][grain]blend=all_mode=overlay:all_opacity={min(1.0, grain / 25):.3f}"
                     ":shortest=1,format=yuv420p[out]")
    preset, crf = (r["preset"], r["crf"]) if final else (r["clip_preset"], 17)
    rate = ["-maxrate", r.get("maxrate", "12M"), "-bufsize", "24M"] if final else []
    if final:  # drop the trailing crossfade tail so video length == timeline length
        rate += ["-t", f"{sum(slots):.4f}"]
    tmp = atomic_out(out)
    run(["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(parts), "-map", "[out]",
         "-c:v", "libx264", "-preset", preset, "-crf", crf, *rate, "-pix_fmt", "yuv420p", "-an", tmp],
        "crossfade/join video")
    os.replace(tmp, out)


# ---------------------------------------------------------------- audio
def pick_bgm(ep: Episode, args) -> Path | None:
    if getattr(args, "no_bgm", False):
        return None
    bgm_dir = ASSETS / "bgm"
    name = getattr(args, "bgm", None) or ep.script.get("bgm") or ep.story.get("bgm")
    if name:
        for cand in (Path(name), bgm_dir / name, ROOT / name):
            if cand.exists():
                return cand
        raise PipelineError(f"File musik '{name}' tidak ditemukan (taruh di assets/bgm/).")
    if bgm_dir.exists():
        files = sorted(f for f in bgm_dir.iterdir() if f.suffix.lower() in AUDIO_EXTS)
        if files:
            return files[0]
    return None


def mix_audio(narration: Path, bgm: Path | None, out: Path, total: float, r: dict,
              fade_out: float = 4.0) -> None:
    tmp = atomic_out(out)
    if bgm is None:
        run(["ffmpeg", "-y", "-i", narration, "-af",
             "aformat=sample_rates=48000:channel_layouts=stereo", "-t", f"{total:.3f}",
             "-c:a", "pcm_s16le", tmp], "audio narasi")
    else:
        vol = float(r["bgm_volume"])
        fo = max(0.0, total - fade_out)
        bg = (f"[1:a]aformat=sample_rates=48000:channel_layouts=stereo,volume={vol},"
              f"atrim=0:{total:.3f},afade=t=in:d=2,afade=t=out:st={fo:.3f}:d={fade_out}")
        if r.get("duck", True):
            fc = (f"[0:a]aformat=sample_rates=48000:channel_layouts=stereo,asplit=2[voice][sc];"
                  f"{bg}[bg];"
                  "[bg][sc]sidechaincompress=threshold=0.015:ratio=12:attack=20:release=450[duck];"
                  "[voice][duck]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[a]")
        else:
            fc = (f"[0:a]aformat=sample_rates=48000:channel_layouts=stereo[voice];{bg}[bg];"
                  "[voice][bg]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[a]")
        run(["ffmpeg", "-y", "-i", narration, "-stream_loop", "-1", "-i", bgm, "-filter_complex", fc,
             "-map", "[a]", "-t", f"{total:.3f}", "-c:a", "pcm_s16le", tmp], "mix musik")
    os.replace(tmp, out)


def mux(video: Path, audio: Path, out: Path, total: float) -> None:
    tmp = atomic_out(out)
    run(["ffmpeg", "-y", "-i", video, "-i", audio, "-map", "0:v", "-map", "1:a", "-c:v", "copy",
         "-c:a", "aac", "-b:a", "192k", "-t", f"{total:.3f}", "-movflags", "+faststart", tmp],
        "mux final")
    os.replace(tmp, out)


# ---------------------------------------------------------------- shot planning
def split_slot(slot: float, k: int, fps: int) -> list[float]:
    frames = round(slot * fps)
    base = frames // k
    parts = [base] * k
    parts[-1] += frames - base * k
    return [p / fps for p in parts]


def plan_shots(ep: Episode, segs: list[Segment]) -> list[dict]:
    r = ep.render
    fps = int(r["fps"])
    rnd = random.Random(f"{ep.slug}-{ep.ep}")
    shots = []
    last_dir = None

    def next_dir():
        nonlocal last_dir
        d = rnd.choice([x for x in DIRECTIONS if x != last_dir])
        last_dir = d
        return d

    for s in segs:
        if s.kind in ("intro", "outro"):  # channel card: black, text fades in/out, no Ken Burns
            shots.append({"kind": "channel", "slot": s.slot, "card": s.card, "dir": "static",
                          "fade": C.FADE, "fade_slot": s.card["text_dur"]})
            continue
        if s.kind == "lead":  # cold-open black
            shots.append({"kind": "black", "slot": s.slot})
            continue
        if s.kind == "card":
            shots.append({"kind": "card", "slot": s.slot, "top": s.card["top"],
                          "title": s.card["title"], "dir": "subtle"})
            continue
        if s.kind == "recap":
            img = ep.recap_image()
            if img:
                src, crop, focus = img, "wide", None
            else:
                shots.append({"kind": "text", "slot": s.slot, "text": "SEBELUMNYA...", "dir": "subtle"})
                continue
        else:
            b = s.beat
            if b.visual == "black":
                shots.append({"kind": "black", "slot": s.slot})
                continue
            if b.visual == "text_card":
                shots.append({"kind": "text", "slot": s.slot, "text": b.card_text or b.text,
                              "dir": "static", "fade": TEXT_CARD_FADE})
                continue
            src, crop, focus = ep.image_for(b), b.crop, b.focus
            if src is None:
                raise PipelineError(f"Gambar untuk {b.key} tidak ada. Jalankan: check {ep.slug} {ep.ep}")
        k = max(1, math.ceil(s.slot / float(r["max_shot"]) - 1e-6))
        alt = "medium" if crop == "wide" else "wide"
        for j, part in enumerate(split_slot(s.slot, k, fps)):
            c = crop if j % 2 == 0 else alt
            shift = 0.0
            if c == "medium":  # alternate left/right so repeated crops differ
                shift = -0.1 if (j // 2) % 2 == 0 else 0.1
            shots.append({"kind": "image", "slot": part, "src": src, "crop": c, "focus": focus,
                          "shift": shift, "dir": next_dir()})
    return shots


def render_shots(ep: Episode, shots: list[dict], w: int, h: int, force: bool,
                 zoom: float | None = None, composite=None, label="klip") -> list[Path]:
    r = ep.render
    D = float(r["crossfade"])
    clip_dir = ep.cache / "clips"
    still_dir = ep.cache / "stills"
    clip_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    rendered = 0
    for i, sh in enumerate(shots):
        dur = sh["slot"] + D
        sig = {k: v for k, v in sh.items() if k != "src"}
        sig.update(src=file_sig(sh.get("src")), dur=dur, w=w, h=h, zoom=zoom,
                   fps=r["fps"], comp=bool(composite), font=V.find_font(ep.story),
                   serif=V.find_serif_font(ep.story), v=4)
        h_ = sha(sig)
        out = clip_dir / f"{label}_{h_}.mp4"
        paths.append(out)
        if out.exists() and not force:
            continue
        still = None
        if sh["kind"] != "black":
            still_path = still_dir / f"{h_}.jpg"
            if force and still_path.exists():
                still_path.unlink()
            if sh["kind"] == "image":
                img = V.crop_region(V.load_rgb(sh["src"]), sh["crop"], sh["focus"], sh["shift"])
            elif sh["kind"] == "card":
                img = V.chapter_card(ep.story, sh["top"], sh["title"], w * 2, h * 2)
            elif sh["kind"] == "channel":
                img = C.card_image(sh["card"], w * 2, h * 2)
            else:
                img = V.text_card(ep.story, sh["text"], w * 2, h * 2)
            if composite and sh["kind"] == "image":
                img = composite(img)
            still = save_still(img, still_path, w, h)
        print(f"  [{i + 1}/{len(shots)}] {label} {sh['kind']:<5} {dur:5.2f}s {sh.get('dir', '')}",
              flush=True)
        render_clip(still, out, dur, sh.get("dir", "subtle"), r, w, h, zoom,
                    fade=sh.get("fade", 0.0), slot=sh.get("fade_slot", sh["slot"]))
        rendered += 1
    info(f"{rendered} klip dirender, {len(shots) - rendered} dipakai dari cache")
    return paths


# ---------------------------------------------------------------- command
def _preview_timeline(ep: Episode, keys: set) -> list[Segment]:
    """The selected beats with the same timing as in the full episode (chapter card included,
    recap left out), so a preview sounds like the final cut."""
    first_of = {}
    for b in ep.beats:
        first_of.setdefault(b.chapter, b.key)
    segs = [s for s in build_timeline(ep, require_audio=False)
            if (s.kind == "beat" and s.beat.key in keys) or (s.kind == "card" and first_of[s.chapter] in keys)]
    lacking = [s.beat.key for s in segs if s.kind == "beat" and s.text and not s.audio]
    if lacking:
        raise PipelineError(f"Audio belum ada untuk: {', '.join(lacking[:8])}"
                            f"\n  Jalankan dulu: tts {ep.slug} {ep.ep}")
    t = 0.0
    for s in segs:
        s.start = t
        t += s.slot
    return segs


def cmd_build(ep: Episode, args) -> None:
    require_ffmpeg()
    r = ep.render
    sel = ep.parse_beat_range(args.beats) if getattr(args, "beats", None) else None
    keys = {b.key for b in sel} if sel else None
    step(f"Build {ep.slug} {ep.ep}" + (f"  [preview {sel[0].key}–{sel[-1].key}]" if sel else ""))
    missing = [b for b in ep.missing_images() if keys is None or b.key in keys]
    if missing:
        raise PipelineError("Gambar belum lengkap: " + ", ".join(b.key for b in missing) +
                            f"\n  Cek dengan: check {ep.slug} {ep.ep}")
    segs = build_timeline(ep) if sel is None else _preview_timeline(ep, keys)
    lay = structure(ep)
    fps = int(r["fps"])
    if float(lay["cold_open"] or 0) > 0 and segs and segs[0].kind != "recap" and \
            (sel is None or sel[0] is ep.beats[0]):
        # a moment of black (ambience fading in) so the first line doesn't start on frame 1
        segs.insert(0, Segment("lead", quantize(float(lay["cold_open"]), fps)))
        t = 0.0
        for s in segs:
            s.start = t
            t += s.slot
    story_total = total_duration(segs)
    # channel intro/outro wrap the story; the story's own sound layer never reaches them
    ch = C.for_episode(ep)
    intro = ch.segment("intro", fps) if ch and lay["intro"] else None
    outro = ch.segment("outro", fps) if ch else None
    all_segs = [x for x in (intro, *segs, outro) if x is not None]
    total = total_duration(all_segs)
    info(f"Durasi: {fmt_ts(total)} · {len(all_segs)} segmen"
         + (f" (intro {intro.slot:.1f}s + " if intro else " (") + f"cerita {fmt_ts(story_total)}"
         + (f" + outro {outro.slot:.1f}s)" if outro else ")"))

    step("Audio")
    # the vertical build keeps its own audio files, so both builds can run side by side
    tag = ("_preview" if sel else "") + ("_v" if getattr(args, "vertical", False) else "")
    narration = ep.cache / f"narration{tag}.wav"
    write_narration(segs, narration)
    mix = ep.cache / f"mix{tag}.wav"
    if not getattr(args, "no_sound", False) and sound.load_config(ep) is not None:
        sound.mix(ep, segs, narration, mix, story_total)  # music + ambience + sfx from sound.yaml
    else:
        bgm = pick_bgm(ep, args)
        info(f"Musik: {bgm.name if bgm else '(tanpa musik)'}")
        mix_audio(narration, bgm, mix, story_total, r)
    if ch:
        wrapped = ep.cache / f"mix_channel{tag}.wav"
        C.wrap_audio(mix, intro, outro, wrapped)
        mix = wrapped
        info(f"Intro/outro channel '{ch.slug}' ditambahkan")
    story_starts = [s.start for s in all_segs]  # mix/stems timebase (story from 0)
    t = 0.0  # story segments were timed from 0 for the mix; shift them behind the intro
    for s in all_segs:
        s.start = t
        t += s.slot
    segs = all_segs

    if getattr(args, "vertical", False):  # 9:16 from the same timeline + mix
        from .vertical import build_vertical
        return build_vertical(ep, args, sel, segs, story_starts, mix, narration, total, ch)

    shots = plan_shots(ep, all_segs)
    clips = render_shots(ep, shots, int(r["width"]), int(r["height"]), args.force)
    step("Crossfade & gabung video")
    slots = [s["slot"] for s in shots]
    video = ep.cache / f"video_{sha([str(c) for c in clips] + slots + [r['crossfade'], r['crf'], r['preset'], r['grain']])}.mp4"
    if args.force or not video.exists():
        work = ep.cache / "groups"
        work.mkdir(exist_ok=True)
        xfade_join(clips, slots, video, r, work, final=True, force=args.force)
    else:
        info("Video gabungan dipakai dari cache")

    if sel:
        out = ep.output / f"preview_{sel[0].key}-{sel[-1].key}.mp4"
        srt = out.with_suffix(".srt")
        mux(video, mix, out, total)
        write_srt(segs, srt)
        write_description(ep, segs, ep.output / f"description_{out.stem}.txt")
        ok(f"Preview: {out.relative_to(ROOT)}  ({fmt_ts(total)}) + {srt.name}")
    else:
        out = ep.output / f"{ep.ep}.mp4"
        srt = ep.output / f"{ep.ep}.srt"
        mux(video, mix, out, total)
        write_srt(segs, srt)
        write_description(ep, segs, ep.output / "description.txt")
        ok(f"Selesai: {out.relative_to(ROOT)}  ({fmt_ts(total)})")
        ok(f"Subtitle: {srt.relative_to(ROOT)} · deskripsi+chapter: output/description.txt")
        if args.clean:
            shutil.rmtree(ep.cache / "groups", ignore_errors=True)

    manifest = _write_manifest(ep, out, srt, tag, total, segs, story_starts, shots, narration, ch)
    if not getattr(args, "no_review", False):
        from .review import review
        review(ep, manifest)


def _write_manifest(ep, out, srt, tag, total, segs, story_starts, shots, narration, ch, **extra) -> Path:
    """What `review` needs to know about the render it checks."""
    import json
    t, shot_rows = 0.0, []
    for sh in shots:
        shot_rows.append({"kind": sh["kind"], "start": round(t, 3), "slot": round(sh["slot"], 3),
                          "src": Path(sh["src"]).name if sh.get("src") else None, "crop": sh.get("crop")})
        t += sh["slot"]
    rows = []
    for s, st in zip(segs, story_starts):
        b = s.beat
        rows.append({"kind": s.kind, "key": b.key if b else s.kind, "start": round(s.start, 3),
                     "story_start": round(st, 3), "slot": round(s.slot, 3), "audio_dur": round(s.audio_dur, 3),
                     "lead": s.lead, "chapter": s.chapter, "visual": getattr(b, "visual", None),
                     "pause_after": getattr(b, "pause_after", None), "text": bool(s.text)})
    m = {"output": str(out), "srt": str(srt), "total": total, "segments": rows, "shots": shot_rows,
         "narration": str(narration), "stems": {k: str(ep.cache / f"stem_{k}.wav") for k in ("music", "amb", "sfx")},
         "max_shot": float(ep.render["max_shot"]), "channel": ch.slug if ch else None,
         "mute_on_beats": [str(x) for x in ((sound.load_config(ep) or {}).get("music") or {}).get("mute_on_beats") or []],
         **extra}
    p = ep.cache / f"render{tag}.json"
    p.write_text(json.dumps(m, indent=2, ensure_ascii=False), encoding="utf-8")
    return p
