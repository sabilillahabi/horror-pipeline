"""`prompts` and `check` commands."""
from __future__ import annotations

from .common import ROOT, Episode, ok, step, warn

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


def position_phrase(pos: str) -> str:
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
    for rel, keys in ref_use.items():
        if not (ep.story_dir / rel).exists():
            warn(f"Referensi belum ada: {rel} (dipakai {len(keys)} prompt)")


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
    expected = {b.key for b in need}
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
    if missing:
        print(f"\n  {len(missing)} gambar belum ada.")
        return 1
    ok("Semua gambar lengkap.")
    return 0
