"""`threads` command: one Threads thread per chapter from script.yaml (no new images, no TTS).

Output in output/threads/: bab<N>.md (numbered posts, character counts, image per post), images/ with
the episode thumbnail on post 1 (thumbnail_16x9.jpg as is), at most 2 scene images per thread as
1080x1350 (4:5) crops, and threads.json (read by `review`). --thumb-only: thumbnail only.

Optional overrides in episodes/epXX/threads.yaml:
    bab1:
      hook: "Jangan menerima apa pun dari perempuan di gerbang makam. Tapi malam itu, dia menoleh."
      images: [b013, b021]            # scene images (max 2; post 1 always gets the thumbnail)
      key_image: b008                 # post 1 only if thumbnail_16x9.jpg is missing
Per beat in script.yaml: `threads_dialogue: true|false` forces a narrator line to be (or not be) dialogue.
"""
from __future__ import annotations

import json
import random
import re
import shutil
from pathlib import Path

from PIL import Image

from .common import ROOT, Episode, PipelineError, info, ok, step, warn
from . import visuals as V

LIMIT, HARD_LIMIT, MAX_POSTS = 480, 500, 15
MAX_SCENE_IMAGES = 2                  # 4:5 scene images per thread (post 1 always gets the thumbnail)
W, H = 1080, 1350
TOPIC_TAG = "#KemenyanMalam"          # Threads allows one topic tag per post
LINK = "[LINK YOUTUBE]"
TENSE_SFX = ("hit", "knock", "impact", "boom", "whoosh", "humming", "kentongan")
VOCATIVES = ("dek", "mbah", "mas", "le", "nduk", "pak", "bu", "sekar", "kang", "lik")
SCARY = ("makam", "gerbang", "jangan", "tersenyum", "menoleh", "mati", "meninggal", "kunci", "mengetuk",
         "darah", "bisik", "sendirian", "aneh", "sujud", "kemenyan", "nggak ada", "tiga kali", "juru kunci")


def tlen(s: str) -> int:
    """Threads-safe length: emoji / pictographs count as their UTF-8 byte length, everything else as 1."""
    n = 0
    for ch in s:
        o = ord(ch)
        emoji = o >= 0x1F000 or 0x2600 <= o <= 0x27BF or 0x2B00 <= o <= 0x2BFF or o in (0xFE0F, 0x200D)
        n += len(ch.encode("utf-8")) if emoji else 1
    return n


def _sentences(t: str) -> list[str]:
    return [x for x in re.split(r"(?<=[.!?…])\s+(?=[A-Z0-9\"“'(])", " ".join(t.split())) if x]


def _is_dialogue(ep: Episode, b) -> bool:
    raw = b.raw or {}
    if "threads_dialogue" in raw:
        return bool(raw["threads_dialogue"])
    if b.speaker != "narrator":
        return True
    first = re.split(r"[ ,.!?]", (b.text or "").strip().lower(), 1)[0]
    return first in VOCATIVES and "," in (b.text or "")[:12]


# ------------------------------------------------------------------ prose units
def units(ep: Episode, beats) -> list[dict]:
    """Reading units: narration sentences (grouped per paragraph) and dialogue lines in quotes."""
    out = []
    for b in beats:
        t = (b.text or "").strip()
        if not t:
            continue
        if b.visual == "text_card":           # scene break like "Tiga minggu sebelumnya."
            out.append({"kind": "break", "text": t, "beat": b.key})
            continue
        if _is_dialogue(ep, b):
            out.append({"kind": "dialogue", "text": f"“{t}”", "beat": b.key})
            continue
        para = b.visual == "black" or (out and out[-1]["kind"] != "narr")
        for i, s in enumerate(_sentences(t)):
            out.append({"kind": "narr", "text": s, "beat": b.key, "para": para and i == 0})
    return out


def _render(us: list[dict]) -> str:
    """Join units: narration flows in paragraphs, dialogue and scene breaks on their own lines."""
    parts = []
    for u in us:
        if u["kind"] == "narr" and parts and parts[-1][0] == "narr" and not u.get("para"):
            parts[-1] = ("narr", parts[-1][1] + " " + u["text"])
        else:
            parts.append((u["kind"], u["text"]))
    return "\n\n".join(t for _, t in parts)


# ------------------------------------------------------------------ scoring
def _sfx_map(ep: Episode) -> dict:
    from .sound import load_config
    m = {}
    for k, v in ((load_config(ep) or {}).get("sfx") or {}).items():
        b = ep.resolve_ref(str(k))
        if b:
            m[b.key] = str(v.get("file", ""))
    return m


def _beat_score(ep: Episode, b, sfx: dict, nxt=None) -> int:
    t = (b.text or "").lower()
    s = 0
    if any(k in sfx.get(b.key, "") for k in TENSE_SFX):
        s += 3
    if nxt is not None and nxt.visual == "black":
        s += 2
    if t.rstrip().endswith(("...", "…", "?")):
        s += 1
    s += min(3, sum(1 for w in SCARY if w in t))
    if b.crop in ("closeup_face", "detail"):
        s += 1
    return s


def _unit_tension(u: dict, nxt: dict | None, sfx: dict, beat_by_key: dict) -> int:
    t = u["text"].rstrip("”\"")
    s = 0
    if t.endswith(("...", "…", "?")):
        s += 2
    if len(t) <= 45:
        s += 1
    b = beat_by_key.get(u["beat"])
    if b is not None and any(k in sfx.get(b.key, "") for k in TENSE_SFX) and (nxt is None or nxt["beat"] != u["beat"]):
        s += 2
    if nxt is not None and (nxt["kind"] == "dialogue" or (beat_by_key.get(nxt["beat"]) and
                                                           beat_by_key[nxt["beat"]].visual == "black")):
        s += 1
    return s


# ------------------------------------------------------------------ splitting
def split_posts(us: list[dict], sfx: dict, beat_by_key: dict, room_last: int) -> list[list[dict]]:
    """Pack units into posts ≤ LIMIT; end each post on its tensest sentence boundary (≥ 55% full).
    The last post keeps `room_last` characters free for the closing lines."""
    posts, i = [], 0
    while i < len(us):
        j, best, best_sc = i, None, -99
        while j < len(us):
            cand = _render(us[i:j + 1])
            if tlen(cand) > LIMIT:
                break
            if j == len(us) - 1:  # the rest fits: last post (if the closing lines fit too)
                if tlen(cand) + room_last <= LIMIT:
                    best, best_sc = j, 99
                break
            if tlen(cand) >= 0.55 * LIMIT:
                sc = _unit_tension(us[j], us[j + 1], sfx, beat_by_key) + tlen(cand) / LIMIT
                if sc >= best_sc:
                    best, best_sc = j, sc
            j += 1
        if best is None:  # nothing reached 55%: take as much as fits
            best = max(i, j - 1)
            if j == len(us) and tlen(_render(us[i:])) + room_last > LIMIT and best == len(us) - 1 and best > i:
                best -= 1  # leave the cliffhanger for a last post with the closing lines
        posts.append(us[i:best + 1])
        i = best + 1
    # the chapter's final beat (the cliffhanger) stays whole in the last post
    if len(posts) >= 2:
        last_beat = us[-1]["beat"]
        while posts[-2] and posts[-2][-1]["beat"] == last_beat:
            moved = posts[-2][-1:]
            if tlen(_render(moved + posts[-1])) + room_last > LIMIT:
                break
            posts[-1] = moved + posts[-1]
            posts[-2] = posts[-2][:-1]
        if not posts[-2]:
            posts.pop(-2)
    return posts


# ------------------------------------------------------------------ images
def crop_45(ep: Episode, b, out: Path) -> None:
    """1080x1350 crop centred like the vertical output (characters / speaker), static."""
    from .vertical import crop_plan
    src = ep.image_for(b)
    cp = crop_plan(ep, b, src, 6.0, random.Random(b.key), aspect=4 / 5)
    img = V.load_rgb(src).crop(tuple(int(round(v)) for v in cp["box"]))
    x = (cp["x0"] + cp["x1"]) / 2 if cp["mode"] == "pan" else cp["x0"]
    ww = img.height * 4 / 5
    x0 = min(max(0, x * img.width - ww / 2), img.width - ww)
    img = img.crop((int(x0), 0, int(x0 + ww), img.height)).resize((W, H), Image.LANCZOS)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "JPEG", quality=90, optimize=True)


def _part_video(ep: Episode, chapter: int) -> str | None:
    """A vertical IG/FB part (< 5 min) whose beats belong to this chapter."""
    for mf in sorted(ep.cache.glob("render_vertical*.json"), key=lambda p: -p.stat().st_mtime):
        m = json.loads(mf.read_text(encoding="utf-8"))
        outdir = Path(m["output"]).parent
        for p in m.get("parts") or []:
            chs = {s["chapter"] for s in m["segments"] if s["kind"] == "beat" and p["a"] <= s["start"] < p["b"]}
            f = outdir / p.get("file", "")
            if chapter in chs and p["dur"] < 300 and f.is_file():
                return f"{f.relative_to(ep.output).as_posix()} ({int(p['dur'] // 60)}:{int(p['dur'] % 60):02d})"
    return None


# ------------------------------------------------------------------ command
def build_chapter(ep: Episode, ci: int, cfg: dict, outdir: Path, sfx: dict, thumb_only: bool = False) -> dict:
    beats = [b for b in ep.beats if b.chapter == ci]
    beat_by_key = {b.key: b for b in beats}
    title = ep.story.get("title", ep.slug)
    label = f"{title} · Eps {ep.number} · Bab {ci + 1}"
    n_bab = f"bab{ci + 1}"
    over = cfg.get(n_bab) or {}

    # hook: best line from the first 80% (no ending spoilers), plus the line before it if it fits
    cut = max(1, int(len(beats) * 0.8))
    scored = [(_beat_score(ep, b, sfx, beats[i + 1] if i + 1 < len(beats) else None), -i, b)
              for i, b in enumerate(beats[:cut]) if b.text and b.visual != "text_card"]
    top = max(scored)[2] if scored else beats[0]
    if over.get("hook"):
        hook = str(over["hook"]).strip()
    else:
        k = beats.index(top)
        prev = beats[k - 1] if k > 0 and beats[k - 1].text and beats[k - 1].visual != "text_card" else None
        hook = top.text.strip()
        if prev and not _is_dialogue(ep, prev) and tlen(prev.text + " " + hook) <= 260:
            hook = prev.text.strip() + " " + hook
        if _is_dialogue(ep, top):
            hook = f"“{top.text.strip()}”"
    post1 = f"{hook}\n\n🧵 {label}"

    # closing: cliffhanger = the chapter's last spoken lines (they end the last post)
    closing = (f"\n\nBersambung...\n\n🎧 Versi lengkapnya ada di YouTube, dengan narasi suara, musik, "
               f"dan efek: {LINK}\n{TOPIC_TAG}")
    us = units(ep, beats)
    posts_u = split_posts(us, sfx, beat_by_key, tlen(closing))
    texts = [post1] + [_render(p) for p in posts_u]
    texts[-1] += closing
    if tlen(texts[-1]) > LIMIT:  # should not happen; keep the closing in its own post
        texts[-1] = texts[-1][: -len(closing)]
        texts.append(closing.strip())

    # images: post 1 = episode thumbnail; plus up to MAX_SCENE_IMAGES strongest moments (one per post)
    img_beats = [b for b in beats if b.visual == "image" and ep.image_for(b)]
    key_b = beat_by_key.get(str(over.get("key_image") or "")) or \
        (beat_by_key.get((ep.script.get("thumbnail") or {}).get("beat", "")) if ci == 0 else None) or \
        (top if top in img_beats else (img_beats[0] if img_beats else None))
    post_of = {}
    for pi, p in enumerate(posts_u, start=2):
        for u in p:
            post_of.setdefault(u["beat"], pi)
    if over.get("images"):
        extra = [beat_by_key[str(x)] for x in over["images"] if str(x) in beat_by_key][:MAX_SCENE_IMAGES]
    else:
        ranked = sorted(((_beat_score(ep, b, sfx, beats[beats.index(b) + 1] if beats.index(b) + 1 < len(beats) else None),
                          b) for b in img_beats if b is not key_b), key=lambda x: -x[0])
        extra, used_posts = [], set()
        for sc, b in ranked:
            pi = post_of.get(b.key)
            if pi is None or pi in used_posts or b.image_from:
                continue
            extra.append(b)
            used_posts.add(pi)
            if len(extra) >= MAX_SCENE_IMAGES:
                break
    if thumb_only:
        extra = []
    media = {}
    for b in extra[:MAX_SCENE_IMAGES]:
        pi = post_of.get(b.key)
        if pi and pi != 1 and pi not in media:
            media[pi] = b
    img_dir = outdir / "images"
    img_dir.mkdir(parents=True, exist_ok=True)
    for old in img_dir.glob(f"{n_bab}_post*.jpg"):
        old.unlink()
    files = {}
    # post 1: the episode thumbnail, as is (fallback: the key image cropped to 4:5)
    from . import thumbs
    thumb = thumbs.path(ep, "16x9")
    f1 = img_dir / f"{n_bab}_post01.jpg"
    if thumb.exists():
        shutil.copy2(thumb, f1)
        files[1] = (f1.name, "thumbnail_16x9")
    elif key_b:
        warn(f"{n_bab}: thumbnail/thumbnail_16x9.jpg belum ada — post 1 pakai gambar {key_b.key}")
        crop_45(ep, key_b, f1)
        files[1] = (f1.name, key_b.key)
    for pi, b in sorted(media.items()):
        f = img_dir / f"{n_bab}_post{pi:02d}.jpg"
        crop_45(ep, b, f)
        files[pi] = (f.name, b.key)

    video = _part_video(ep, ci)
    chap = ep.chapters[ci]["title"]
    md = [f"# {label}: {chap} — Threads", "",
          f"{len(texts)} post · batas {HARD_LIMIT} karakter (target ≤ {LIMIT}) · post 1 = thumbnail 16:9, "
          f"gambar adegan 1080x1350 (4:5) di images/", ""]
    if video:
        md += [f"Video opsional untuk post 1: `{video}`", ""]
    for i, t in enumerate(texts, 1):
        img = files.get(i)
        md += [f"## Post {i}/{len(texts)} · {tlen(t)} karakter", "",
               f"Gambar: `images/{img[0]}` ({img[1]})" if img else "Gambar: -", "", "```", t, "```", ""]
    (outdir / f"{n_bab}.md").write_text("\n".join(md), encoding="utf-8")
    return {"bab": n_bab, "label": label, "posts": [tlen(t) for t in texts],
            "images": {str(k): v[0] for k, v in files.items()}, "video": video}


def cmd_threads(ep: Episode, args) -> None:
    step(f"Threads {ep.slug} {ep.ep}")
    outdir = ep.output / "threads"
    outdir.mkdir(parents=True, exist_ok=True)
    cfg_path = ep.dir / "threads.yaml"
    cfg = {}
    if cfg_path.exists():
        import yaml
        cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    sfx = _sfx_map(ep)
    summary = []
    for ci in range(len(ep.chapters)):
        r = build_chapter(ep, ci, cfg, outdir, sfx, thumb_only=getattr(args, "thumb_only", False))
        summary.append(r)
        flag = "" if max(r["posts"]) <= HARD_LIMIT and len(r["posts"]) <= MAX_POSTS else "  ⚠"
        info(f"{r['bab']}.md: {len(r['posts'])} post (terpanjang {max(r['posts'])}), {len(r['images'])} gambar{flag}")
    (outdir / "threads.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    ok(f"Threads di {outdir.relative_to(ROOT)}")
