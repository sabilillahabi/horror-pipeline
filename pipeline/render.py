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
KB_VERSION = 5   # bump when the motion/still logic changes: it is part of every shot's cache key


def _even(x: float) -> int:
    return max(2, int(round(x / 2)) * 2)


def kb_filter(direction: str, dur: float, amount: float, w: int, h: int) -> str:
    """Ken Burns with crop/scale on a still that is already kb_scale (1.5x) the output size.

    zoom: the still is scaled per frame to (1+z(t))·output and the centre cut out; pan: scaled once to
    (1+amount)·output and the crop window slides. Easing: smoothstep over the clip."""
    p = f"min(1,t/{max(0.04, dur):.3f})"
    e = f"({p}*{p}*(3-2*{p}))"
    if direction in ("zoom_in", "zoom_out", "subtle"):
        a = amount * (0.35 if direction == "subtle" else 1.0)
        z = f"(1+{a}*{e})" if direction != "zoom_out" else f"(1+{a}*(1-{e}))"
        return (f"scale=w='2*trunc({w}*{z}/2)':h='2*trunc({h}*{z}/2)':eval=frame:flags=bicubic,"
                f"crop={w}:{h}:x='(iw-{w})/2':y='(ih-{h})/2'")
    if direction in ("pan_right", "pan_left", "pan_up", "pan_down"):
        zw, zh = _even(w * (1 + amount)), _even(h * (1 + amount))
        fx = {"pan_right": e, "pan_left": f"(1-{e})"}.get(direction, "0.5")
        fy = {"pan_down": e, "pan_up": f"(1-{e})"}.get(direction, "0.5")
        return f"scale={zw}:{zh}:flags=bicubic,crop={w}:{h}:x='(iw-{w})*{fx}':y='(ih-{h})*{fy}'"
    return f"scale={w}:{h}:flags=bicubic"


def render_clip(still: Path | None, out: Path, dur: float, direction: str, r: dict,
                w: int, h: int, zoom: float | None = None, fade: float = 0.0,
                slot: float | None = None) -> None:
    """Render one shot. `fade` > 0: fade in from black at the start and out to black by `slot`
    (the crossfade tail after `slot` then stays black)."""
    from .encode import clip_args
    fps = int(r["fps"])
    n = max(1, round(dur * fps))
    post = ""
    if fade > 0:
        slot = dur if slot is None else slot
        f = min(fade, slot / 3)
        post += f",fade=t=in:st=0:d={f:.3f},fade=t=out:st={max(0.0, slot - f):.3f}:d={f:.3f}"
    post += ",format=yuv420p"  # grain is added once, in the final join pass
    tmp = atomic_out(out)
    common_out = ["-frames:v", n, "-r", fps, *clip_args(), "-an", tmp]
    if still is None:  # plain black
        run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=black:s={w}x{h}:r={fps}",
             "-vf", post.lstrip(","), *common_out], "render klip hitam")
    else:
        vf = kb_filter(direction, n / fps, r["zoom"] if zoom is None else zoom, w, h) + post
        run(["ffmpeg", "-y", "-loop", "1", "-framerate", fps, "-i", still, "-vf", vf, *common_out],
            f"render klip {out.name}")
    os.replace(tmp, out)


def save_still(img, path: Path, w: int, h: int, scale: float = 1.5) -> Path:
    """Each source is scaled once, to `scale` (kb_scale, 1.5x) times the output size; motion is done by
    ffmpeg crop/scale from there."""
    if not path.exists():
        img = V.cover(img, _even(w * scale), _even(h * scale))
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.stem + ".part.jpg")
        img.save(tmp, quality=92)
        os.replace(tmp, path)
    return path


_HASHES: dict = {}


def content_hash(p: Path | None) -> str | None:
    """sha256 of an image file (memoised on path+size+mtime): shot caches follow the image, not its name."""
    if not p or not Path(p).exists():
        return None
    import hashlib
    st = Path(p).stat()
    k = (str(p), st.st_size, st.st_mtime_ns)
    if k not in _HASHES:
        h = hashlib.sha256()
        with open(p, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        _HASHES[k] = h.hexdigest()[:16]
    return _HASHES[k]


def run_parallel(jobs: list, label: str) -> None:
    """Run callables on cores-1 workers (each is an ffmpeg process); first error wins."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from .encode import workers
    if not jobs:
        return
    n = min(workers(), len(jobs))
    done = 0
    with ThreadPoolExecutor(max_workers=n) as ex:
        futs = [ex.submit(j) for j in jobs]
        for f in as_completed(futs):
            f.result()
            done += 1
            if done == len(jobs) or done % 10 == 0:
                print(f"  {label}: {done}/{len(jobs)}", flush=True)


# ---------------------------------------------------------------- crossfade join
def xfade_join(clips: list[Path], slots: list[float], out: Path, r: dict, work: Path,
               final: bool, force: bool = False, post: str | None = None, cwd: Path | None = None) -> None:
    """Join clips (each `slot + crossfade` long) so clip k starts exactly at sum(slots[:k]).

    final=True: film grain + `post` filter (e.g. burned-in subtitles) + the final encoder
    (pipeline/encode.py), trimmed to sum(slots). Otherwise a near-lossless intermediate."""
    from .encode import clip_args, video_args
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
        return xfade_join(groups, gslots, out, r, work, final, force, post, cwd)

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
    if final and (grain or post):
        parts[-1] = parts[-1][: parts[-1].rindex("[out]")] + "[pre]"
        last = "pre"
        if grain:
            # coarse film grain: noise at half resolution, upscaled and overlay-blended.
            w, h = r["_size"]
            parts.append(f"color=c=gray:s={w // 2}x{h // 2}:r={fps},noise=alls=30:allf=t,"
                         f"scale={w}:{h},format=yuv420p[grain]")
            parts.append(f"[pre][grain]blend=all_mode=overlay:all_opacity={min(1.0, grain / 25):.3f}"
                         ":shortest=1,format=yuv420p[g]")
            last = "g"
        parts.append(f"[{last}]{post + ',' if post else ''}format=yuv420p[out]")
    enc = video_args() + ["-r", str(fps), "-t", f"{sum(slots):.4f}"] if final else clip_args(threads=0)
    tmp = atomic_out(out)
    cmd = ["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(parts), "-map", "[out]", *enc, "-an", tmp]
    if cwd is None:
        run(cmd, "crossfade/join video")
    else:
        import subprocess
        p = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", *map(str, cmd[1:])],
                           cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                           encoding="utf-8", errors="replace")
        if p.returncode:
            raise PipelineError(f"crossfade/join video gagal:\n{p.stderr[-1200:]}")
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
    from .encode import AUDIO, FASTSTART
    run(["ffmpeg", "-y", "-i", video, "-i", audio, "-map", "0:v", "-map", "1:a", "-c:v", "copy",
         *AUDIO, "-t", f"{total:.3f}", *FASTSTART, tmp], "mux final")
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
    """Render every shot clip in parallel (cores-1). Cache key = image content hash + motion + duration
    + resolution + layout version, so renaming/re-importing an identical image reuses the clip."""
    r = ep.render
    D = float(r["crossfade"])
    scale = float(r.get("kb_scale", 1.5))
    clip_dir = ep.cache / "clips"
    still_dir = ep.cache / "stills"
    clip_dir.mkdir(parents=True, exist_ok=True)
    paths, jobs = [], []
    for i, sh in enumerate(shots):
        dur = sh["slot"] + D
        sig = {k: v for k, v in sh.items() if k not in ("src", "slot")}
        sig.update(img=content_hash(sh.get("src")), dur=round(dur, 4), w=w, h=h, zoom=zoom, fps=r["fps"],
                   comp=bool(composite), kb=KB_VERSION, scale=scale, font=V.find_font(ep.story),
                   serif=V.find_serif_font(ep.story))
        h_ = sha(sig)
        out = clip_dir / f"{label}_{h_}.mp4"
        paths.append(out)
        if out.exists() and not force:
            continue

        def job(sh=sh, out=out, h_=h_, dur=dur):
            still = None
            if sh["kind"] != "black":
                still_path = still_dir / f"{h_}.jpg"
                if force and still_path.exists():
                    still_path.unlink()
                if not still_path.exists():
                    if sh["kind"] == "image":
                        img = V.crop_region(V.load_rgb(sh["src"]), sh["crop"], sh["focus"], sh["shift"])
                    elif sh["kind"] == "card":
                        img = V.chapter_card(ep.story, sh["top"], sh["title"], int(w * scale), int(h * scale))
                    elif sh["kind"] == "channel":
                        img = C.card_image(sh["card"], int(w * scale), int(h * scale))
                    else:
                        img = V.text_card(ep.story, sh["text"], int(w * scale), int(h * scale))
                    if composite and sh["kind"] == "image":
                        img = composite(img)
                    save_still(img, still_path, w, h, scale)
                still = still_path
            render_clip(still, out, dur, sh.get("dir", "subtle"), r, w, h, zoom,
                        fade=sh.get("fade", 0.0), slot=sh.get("fade_slot", sh["slot"]))
        jobs.append(job)
    info(f"{len(jobs)} klip dirender, {len(shots) - len(jobs)} dari cache")
    run_parallel(jobs, label)
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


def story_mix(ep: Episode, segs: list[Segment], args, tag: str = "") -> tuple[Path, Path, float]:
    """The episode's one audio mix (narration + music/ambience/SFX, before the channel outro), shared by
    the long video and every vertical part. Recomputed only when the timeline, clips or sound.yaml change."""
    import json
    total = total_duration(segs)
    narration = ep.cache / f"narration{tag}.wav"
    mix = ep.cache / f"mix_story{tag}.wav"
    meta = mix.with_suffix(".json")
    cfgp = ep.dir / "sound.yaml"
    use_sound = not getattr(args, "no_sound", False) and sound.load_config(ep) is not None
    key = sha({"segs": [(s.kind, s.beat.key if s.beat else "", round(s.slot, 4), round(s.lead, 4),
                         file_sig(s.audio)) for s in segs],
               "sound": cfgp.read_text(encoding="utf-8") if use_sound and cfgp.exists() else None,
               "bgm": None if use_sound else str(pick_bgm(ep, args)), "v": 2})
    if mix.exists() and narration.exists() and meta.exists() and \
            json.loads(meta.read_text(encoding="utf-8")).get("key") == key and not getattr(args, "force_mix", False):
        info(f"Mix audio episode dipakai ulang ({mix.name})")
        return narration, mix, total
    write_narration(segs, narration)
    if use_sound:
        sound.mix(ep, segs, narration, mix, total)  # music + ambience + sfx from sound.yaml
    else:
        bgm = pick_bgm(ep, args)
        info(f"Musik: {bgm.name if bgm else '(tanpa musik)'}")
        mix_audio(narration, bgm, mix, total, ep.render)
    meta.write_text(json.dumps({"key": key, "total": total}), encoding="utf-8")
    return narration, mix, total


def cmd_build(ep: Episode, args) -> None:
    import time
    t0 = time.time()
    require_ffmpeg()
    r = ep.render
    sel = ep.parse_beat_range(args.beats) if getattr(args, "beats", None) else None
    keys = {b.key for b in sel} if sel else None
    vertical = getattr(args, "vertical", False)
    step(f"Build {ep.slug} {ep.ep}" + (" [vertikal]" if vertical else "")
         + (f"  [preview {sel[0].key}–{sel[-1].key}]" if sel else ""))
    missing = [b for b in ep.missing_images() if keys is None or b.key in keys]
    if missing:
        raise PipelineError("Gambar belum lengkap: " + ", ".join(b.key for b in missing) +
                            f"\n  Cek dengan: check {ep.slug} {ep.ep}")
    segs = build_timeline(ep) if sel is None else _preview_timeline(ep, keys)
    lay = structure(ep)
    fps = int(r["fps"])
    if float(lay["cold_open"] or 0) > 0 and segs and segs[0].kind != "recap" and \
            (sel is None or sel[0] is ep.beats[0]):
        # a moment of black (ambience fading in) so the first line doesn't start on frame 1 (long video;
        # the vertical parts start after it)
        segs.insert(0, Segment("lead", quantize(float(lay["cold_open"]), fps)))
        t = 0.0
        for s in segs:
            s.start = t
            t += s.slot

    step("Audio")
    tag = "_preview" if sel else ""
    narration, mix, story_total = story_mix(ep, segs, args, tag)

    if vertical:  # 9:16 parts from the same timeline + the same mix; no channel outro
        from .vertical import build_vertical
        build_vertical(ep, args, sel, segs, mix, narration, story_total)
        info(f"Waktu render: {fmt_ts(time.time() - t0)}")
        return

    # channel intro/outro wrap the story (long video only); the story's sound layer never reaches them
    ch = C.for_episode(ep)
    intro = ch.segment("intro", fps) if ch and lay["intro"] else None
    outro = ch.segment("outro", fps) if ch else None
    all_segs = [x for x in (intro, *segs, outro) if x is not None]
    total = total_duration(all_segs)
    info(f"Durasi: {fmt_ts(total)} · {len(all_segs)} segmen"
         + (f" (intro {intro.slot:.1f}s + " if intro else " (") + f"cerita {fmt_ts(story_total)}"
         + (f" + outro {outro.slot:.1f}s)" if outro else ")"))
    if ch:
        wrapped = ep.cache / f"mix_channel{tag}.wav"
        C.wrap_audio(mix, intro, outro, wrapped)
        mix = wrapped
        info(f"Outro channel '{ch.slug}' ditambahkan (hanya video panjang)")
    story_starts = [s.start for s in all_segs]  # mix/stems timebase (story from 0)
    t = 0.0  # story segments were timed from 0 for the mix; shift them behind the intro
    for s in all_segs:
        s.start = t
        t += s.slot
    segs = all_segs

    shots = plan_shots(ep, all_segs)
    clips = render_shots(ep, shots, int(r["width"]), int(r["height"]), args.force)
    step("Crossfade & gabung video")
    from .encode import encoder
    slots = [s["slot"] for s in shots]
    video = ep.cache / f"video_{sha([str(c) for c in clips] + slots + [r['crossfade'], r['grain'], encoder()])}.mp4"
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
        ok(f"Selesai: {out.relative_to(ROOT)}  ({fmt_ts(total)}, {out.stat().st_size / 1e6:.0f} MB)")
        ok(f"Subtitle: {srt.relative_to(ROOT)} · deskripsi+chapter: output/description.txt")
        if args.clean:
            shutil.rmtree(ep.cache / "groups", ignore_errors=True)
    elapsed = time.time() - t0
    info(f"Waktu render: {fmt_ts(elapsed)}")
    manifest = _write_manifest(ep, out, srt, tag, total, segs, story_starts, shots, narration, ch,
                               render_seconds=round(elapsed, 1))
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
                     "pause_after": getattr(b, "pause_after", None), "text": bool(s.text),
                     "words": len(s.text.split()) if s.text else 0})
    m = {"output": str(out), "srt": str(srt), "total": total, "segments": rows, "shots": shot_rows,
         "narration": str(narration), "stems": {k: str(ep.cache / f"stem_{k}.wav") for k in ("music", "amb", "sfx")},
         "max_shot": float(ep.render["max_shot"]), "channel": ch.slug if ch else None,
         "mute_on_beats": [str(x) for x in ((sound.load_config(ep) or {}).get("music") or {}).get("mute_on_beats") or []],
         **extra}
    p = ep.cache / f"render{tag}.json"
    p.write_text(json.dumps(m, indent=2, ensure_ascii=False), encoding="utf-8")
    return p
