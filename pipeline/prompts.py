"""`prompts` and `check` commands."""
from __future__ import annotations

from .common import ROOT, Episode, info, ok, outline_issues, step, warn

POSITION_PHRASES = {
    "left": "on the left side of the frame",
    "right": "on the right side of the frame",
    "center": "in the center of the frame",
    "centre": "in the center of the frame",
    "middle": "in the center of the frame",
    "foreground": "in the foreground",
    "background": "in the background",
    "front": "in the foreground",
    "back": "in the background",
    "far": "far in the distance",
}


# Added to every Flow prompt (story.yaml `composition_block` overrides it; "" turns it off): one 16:9 image
# must work both as the landscape frame and as the ~1/3-wide 9:16 window cut from its centre.
COMPOSITION_DEFAULT = ("Main subject centered in the middle third of the frame, important details away from the "
                       "left and right edges, atmospheric empty space on both sides, headroom above.")
NEAR_CENTER = {"center-left": "just left of center", "centre-left": "just left of center",
               "center-right": "just right of center", "centre-right": "just right of center"}


def composition(ep: Episode) -> str:
    v = ep.story.get("composition_block")
    return COMPOSITION_DEFAULT if v is None else " ".join(str(v).split())


def far_apart(beat) -> bool:
    """Two+ characters placed at opposite edges (plain left + right): the 9:16 window can't hold both."""
    sides = {t for _, p, _ in beat.chars for t in p.lower().replace(",", " ").split() if t in ("left", "right")}
    return len(beat.chars) >= 2 and sides == {"left", "right"}


def position_phrase(pos: str) -> str:
    key = pos.strip().lower()
    for k, v in NEAR_CENTER.items():
        if key.startswith(k):
            rest = position_phrase(key[len(k):])
            return f"{v}" + (f", {rest}" if rest else "")
    tokens = [t for t in pos.replace(",", " ").replace("-", " ").lower().split() if t]
    if not tokens:
        return ""
    phrases = [POSITION_PHRASES.get(t, t) for t in tokens]
    return ", ".join(phrases)


def view_phrase(view: str) -> str:
    v = " ".join(view.split())
    return f"seen {v}" if v.lower().startswith("from ") else v


def build_prompt(ep: Episode, beat) -> str:
    parts = []
    for name, pos, view in beat.chars:
        c = ep.characters.get(name.lower())
        block = c.block if c else ""
        name = c.name if c else name
        if not block:
            block = name
        elif name.lower() not in block.lower():
            block = f"{name}, {block}"
        where = ", ".join(x for x in (position_phrase(pos), view_phrase(view)) if x)
        text = f"{where[0].upper()}{where[1:]}: {block}" if where else block
        parts.append(text.rstrip(". ") + ".")
    scene = " ".join(beat.scene.split())
    if scene and scene[-1] not in ".!?":
        scene += "."
    if scene:
        parts.append(scene)
    if len(beat.chars) >= 2:
        parts.append("The characters stand close together near the center of the frame.")
    comp = composition(ep)
    if comp:
        parts.append(comp)
    style = " ".join(str(ep.story.get("style_block", "") or "").split())
    if style:
        parts.append(style)
    suffix = " ".join(str(ep.story.get("prompt_suffix", "") or "").split())
    if suffix:
        parts.append(suffix)
    return " ".join(p.replace("..", ".") for p in parts)


def _ref_label(ep: Episode, name: str) -> tuple[str, bool]:
    p = ep.reference_image(name)
    rel = p.relative_to(ep.story_dir).as_posix() if p.is_relative_to(ep.story_dir) else str(p)
    return rel, p.exists()


def cmd_prompts(ep: Episode, args) -> None:
    step(f"Menyusun prompt Flow untuk {ep.slug} {ep.ep}")
    out = ep.output / "flow_prompts.md"
    story_title = ep.story.get("title", ep.slug)
    body, reused, nonimg = [], [], []
    ref_use: dict[str, list[str]] = {}
    n = 0
    for b in ep.beats:
        if b.visual != "image":
            nonimg.append(b)
            continue
        if b.image_from:
            reused.append(b)
            continue
        if args.missing_only and ep.find_image(b.key):
            continue
        n += 1
        refs = []
        for name in dict.fromkeys(nm for nm, _, _ in b.chars):  # unique, keep order
            rel, exists = _ref_label(ep, name)
            ref_use.setdefault(rel, []).append(b.key)
            refs.append(f"`{rel}`" + ("" if exists else " ⚠ (belum ada)"))
        status = " ✅ sudah ada" if ep.find_image(b.key) else ""
        body += [
            f"## {n}. {b.key}{status}",
            f"Simpan sebagai: `images/{b.key}.png` · Bab {b.chapter + 1} · {b.speaker}",
            f"Lampirkan referensi: {', '.join(refs) if refs else '— (tanpa karakter)'}",
            "",
            "```text",
            build_prompt(ep, b),
            "```",
        ]
        if b.text:
            body.append(f"> {b.text[:160]}{'…' if len(b.text) > 160 else ''}")
        body.append("")

    head = [
        f"# Flow prompts — {story_title} · Episode {ep.number}: {ep.title}",
        "",
        "Rasio: **16:9 (landscape)**. Simpan tiap hasil ke folder `images/` dengan nama file yang tertera.",
        "",
        "## Ringkasan",
        "",
        f"- Gambar baru untuk dibuat: **{n}**",
        f"- Memakai ulang gambar lain (reuse + crop): {len(reused)}",
        f"- Tanpa gambar (text_card / black): {len(nonimg)}",
        "",
        "Referensi karakter yang dilampirkan:",
        "",
    ]
    if ref_use:
        for rel, keys in sorted(ref_use.items(), key=lambda kv: -len(kv[1])):
            exists = (ep.story_dir / rel).exists()
            head.append(f"- `{rel}` — {len(keys)} prompt{'' if exists else '  ⚠ file belum ada'}")
    else:
        head.append("- (tidak ada)")
    head += ["", "---", ""]
    tail = []
    if reused:
        tail += ["---", "## Tidak perlu generate (reuse gambar beat lain)", ""]
        tail += [f"- {b.key} → pakai `{b.image_from}` (crop: {b.crop})" for b in reused]
        tail.append("")
    if nonimg:
        tail += ["## Tanpa gambar", ""]
        tail += [f"- {b.key} → {b.visual}" + (f": “{b.card_text}”" if b.card_text else "") for b in nonimg]
        tail.append("")
    out.write_text("\n".join(head + body + tail), encoding="utf-8")
    ok(f"{n} prompt ditulis ke {out.relative_to(ROOT)}")
    total_new = sum(1 for b in ep.beats if ep.needs_own_image(b))
    info(f"Gambar baru (Flow, 16:9) episode ini: {total_new} · target {IMG_MIN}–{IMG_MAX}; sisanya reuse + crop")
    if total_new > IMG_MAX:
        warn(f"{total_new} gambar baru > {IMG_MAX}: ganti beberapa beat dengan `reuse: <beat>` + "
             "`crop: wide|closeup_face|detail`")
    for rel, keys in ref_use.items():
        if not (ep.story_dir / rel).exists():
            warn(f"Referensi belum ada: {rel} (dipakai {len(keys)} prompt)")


IMG_MIN, IMG_MAX = 25, 30   # new Flow images per episode


def format_issues(ep: Episode) -> list[str]:
    """Episode-format rules (parts, length, pace) — warnings, the build clamps what it can."""
    from .common import (MAX_SLOW_PER_PART, PARTS_MAX, PARTS_MIN, WORDS_MAX, WORDS_MIN, is_slow_style)
    from .timeline import cliffhanger
    out = []
    if not getattr(ep, "uses_parts", False):
        out.append("script.yaml masih memakai `chapters:` — ganti jadi `parts:` (3–4 part, masing-masing ≤ 2:55)")
    n = len(ep.parts)
    if not PARTS_MIN <= n <= PARTS_MAX:
        out.append(f"{n} part (harus {PARTS_MIN}–{PARTS_MAX})")
    words = sum(len(b.text.split()) for b in ep.beats if not b.long_only)
    if not WORDS_MIN <= words <= WORDS_MAX:
        out.append(f"{words} kata (target {WORDS_MIN}–{WORDS_MAX} per episode)")
    r = ep.render
    for pi, part in enumerate(ep.parts):
        bs = ep.part_beats(pi)
        cb = cliffhanger(ep, pi)
        slow = [b.key for b in bs if is_slow_style(ep.beat_styles.get(b.key, ""))]
        if len(slow) > MAX_SLOW_PER_PART:
            out.append(f"Part {pi + 1}: {len(slow)} baris bergaya pelan di styles.yaml (maks {MAX_SLOW_PER_PART}): "
                       + ", ".join(slow))
        for b in bs:
            cap = float(r["cliff_pause"]) if cb is not None and b.key == cb.key else float(r["max_pause"])
            if b.pause_after is not None and b.pause_after > cap + 1e-6:
                out.append(f"{b.key}: pause_after {b.pause_after} > {cap} (dipotong otomatis)")
        for b in bs:
            if ep.needs_own_image(b) and far_apart(b):
                out.append(f"{b.key}: tokoh di kiri dan kanan berjauhan — di vertikal cuma pembicara yang kelihatan; "
                           "pakai position center-left / center-right")
        for b in bs:
            if b.visual in ("black", "text_card") and not b.long_only and b is not bs[0]:
                out.append(f"Part {pi + 1}: {b.key} = {b.visual} di tengah part (bikin swipe di Shorts/TikTok); "
                           "beri gambar (reuse/crop), atau jadikan long_only kalau cuma untuk video panjang")
        if bs and bs[0].visual in ("black", "text_card"):
            out.append(f"Part {pi + 1} mulai dengan {bs[0].visual} ({bs[0].key}): di vertikal diganti gambar "
                       "terdekat; lebih baik mulai dengan hook bergambar")
    return out


def pose_issues(ep: Episode) -> list[str]:
    """Poses (references/12-A): errors returned, short-pose warnings printed."""
    from .common import MAX_POSES, MIN_POSE_SEC, probe_duration
    errs = []
    posed = [b for b in ep.beats if b.poses]
    if not posed:
        return errs
    print(f"  Pose  : {len(posed)} beat berpose · {sum(len(b.poses) for b in posed)} gambar pose")
    wpm = 115.0
    for b in posed:
        if b.visual != "image":
            errs.append(f"{b.key}: poses hanya untuk beat bergambar (visual: {b.visual})")
            continue
        if len(b.poses) > MAX_POSES:
            errs.append(f"{b.key}: {len(b.poses)} pose (maks {MAX_POSES} gambar per beat termasuk gambar dasar)")
        for k in b.poses:
            if not ep.find_image(k):
                errs.append(f"{b.key}: gambar pose images/{k}.png belum ada")
        a = ep.audio_path(b.key)
        dur = probe_duration(a) if b.text and a.exists() else len(b.text.split()) / wpm * 60
        dur = max(dur, b.min_duration or 0.0)
        n = min(len(b.poses), MAX_POSES)
        if n and dur / n < MIN_POSE_SEC:
            warn(f"{b.key}: {n} pose dalam ±{dur:.1f} s (< {MIN_POSE_SEC} s per pose) — "
                 f"hanya {max(1, int(dur // MIN_POSE_SEC))} pose yang tampil")
    return errs


def cmd_check(ep: Episode, args) -> int:
    step(f"Cek aset {ep.slug} {ep.ep}")
    need = [b for b in ep.beats if ep.needs_own_image(b)]
    missing = ep.missing_images()
    reused = [b for b in ep.beats if b.visual == "image" and b.image_from]
    print(f"  Beat  : {len(ep.beats)} total · {len(need)} gambar baru · {len(reused)} reuse · "
          f"{len(ep.beats) - len(need) - len(reused)} text_card/black")
    print(f"  Gambar: {len(need) - len(missing)}/{len(need)} ada")
    for b in missing:
        print(f"    ✗ images/{b.key}.png   ({b.scene[:70]})")
    rimg = ep.script.get("recap_image")
    if rimg and not ep.recap_image():
        print(f"    ✗ recap_image: {rimg}")
    expected = {b.key for b in need} | {k for b in ep.beats for k in b.poses}
    extra = sorted(p.name for p in ep.images.iterdir()
                   if p.is_file() and p.stem not in expected and not p.name.startswith("."))
    if extra:
        warn(f"File di images/ yang tidak dipakai: {', '.join(extra)}")

    keys = (["recap"] if ep.recap else []) + [b.key for b in ep.beats if b.text]
    have_audio = [k for k in keys if ep.audio_path(k).exists()]
    print(f"  Audio : {len(have_audio)}/{len(keys)} ada")
    names = dict.fromkeys(nm for b in need for nm, _, _ in b.chars)
    for name in names:
        rel, exists = _ref_label(ep, name)
        if not exists:
            warn(f"Referensi karakter belum ada: {rel}")
    from . import thumbs
    have_t = thumbs.existing(ep)
    print(f"  Thumb : {', '.join(f'thumbnail/{p.name}' for p in have_t.values()) or '-'}")
    for r in thumbs.SIZES:
        if r not in have_t:
            warn(f"Thumbnail {r} belum ada (download Flow 'thumb_ep{ep.number:02d}_{r}' lalu import-flow)"
                 + (" — pakai fallback `thumbnail:` di script.yaml" if r == "16x9" and ep.script.get("thumbnail") else ""))
    if len(need) > IMG_MAX:
        warn(f"{len(need)} gambar baru > {IMG_MAX} (target {IMG_MIN}–{IMG_MAX}); pakai reuse + crop")
    pose_err = pose_issues(ep)
    for x in format_issues(ep):
        warn(x)
    o_err, o_warn = outline_issues(ep.slug, ep.number)
    for x in o_warn:
        warn(x)
    for x in o_err:
        print(f"  ✗ {x}")
    for x in pose_err:
        print(f"  ✗ {x}")
    if o_err or pose_err:
        return 1
    if missing:
        print(f"\n  {len(missing)} gambar belum ada.")
        return 1
    ok("Semua gambar lengkap.")
    return 0
