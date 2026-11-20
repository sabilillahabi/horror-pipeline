"""`import-flow` command: copy Google Flow downloads named "[b018a] ..." into images/<id>.png."""
from __future__ import annotations

import re
import shutil
import tempfile
import zipfile
from pathlib import Path

from .common import IMAGE_EXTS, ROOT, Episode, PipelineError, info, ok, step, warn
from . import visuals as V

ID_RE = re.compile(r"\[([^\[\]]+)\]")


def _find_source(arg: str | None, ep: Episode) -> Path:
    if arg:
        p = Path(arg).expanduser()
        if not p.exists():
            raise PipelineError(f"Tidak ditemukan: {p}")
        return p
    # default: newest zip/folder in ~/Downloads whose name contains the story title or slug
    dl = Path.home() / "Downloads"
    if not dl.exists():
        raise PipelineError("Folder ~/Downloads tidak ada; berikan path zip/folder secara eksplisit.")
    words = {ep.slug.replace("-", " ").lower(), str(ep.story.get("title", "")).lower()}
    cands = [p for p in dl.iterdir() if (p.is_dir() or p.suffix.lower() == ".zip")
             and any(w and w in p.name.lower().replace("-", " ") for w in words)]
    if not cands:
        raise PipelineError(f"Tidak ada zip/folder di {dl} yang namanya mengandung '{ep.slug}'. "
                            "Berikan path-nya: import-flow <story> <ep> <path>")
    src = max(cands, key=lambda p: p.stat().st_mtime)
    info(f"Sumber: {src}")
    return src


def cmd_import(ep: Episode, args) -> int:
    step(f"Import gambar Flow → {ep.slug} {ep.ep}")
    src = _find_source(args.source, ep)
    with tempfile.TemporaryDirectory(prefix="flow_") as tmp:
        root = src
        if src.is_file():  # the zip is only read, never modified or deleted
            base = Path(tmp).resolve()
            with zipfile.ZipFile(src) as z:
                for m in z.infolist():
                    if not (base / m.filename).resolve().is_relative_to(base):
                        raise PipelineError(f"Zip berisi path tidak aman: {m.filename}")
                z.extractall(base)
            root = base
        files = [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_EXTS
                 and not p.name.startswith("._") and "__MACOSX" not in p.parts]
        picked: dict[str, Path] = {}
        skipped_old, no_id = [], []
        for p in sorted(files):
            m = ID_RE.search(p.stem)
            if not m:
                no_id.append(p.name)
                continue
            bid = m.group(1).strip()
            if bid.lower().endswith("-old"):
                skipped_old.append(p.name)
                continue
            beat = ep.resolve_ref(bid)
            key = beat.key if beat else bid
            if beat is None:
                warn(f"{p.name}: id '{bid}' tidak ada di script.yaml (tetap disalin sebagai {key}.png)")
            if key in picked:  # several takes for one beat: keep the newest
                keep = max(picked[key], p, key=lambda f: f.stat().st_mtime)
                warn(f"Dua file untuk {key}: '{picked[key].name}' dan '{p.name}' → pakai '{keep.name}'")
                p = keep
            picked[key] = p
        ep.images.mkdir(parents=True, exist_ok=True)
        for key, p in sorted(picked.items()):
            dst = ep.images / f"{key}.png"
            for ext in IMAGE_EXTS:  # an older .jpg/.webp copy would otherwise shadow the new PNG
                other = ep.images / f"{key}{ext}"
                if ext != ".png" and other.exists():
                    other.unlink()
            if p.suffix.lower() == ".png":
                shutil.copy2(p, dst)
            else:
                V.load_rgb(p).save(dst)
            print(f"  {p.name}  →  images/{dst.name}")
    ok(f"{len(picked)} gambar disalin ke {ep.images.relative_to(ROOT)}")
    if skipped_old:
        info(f"Dilewati (-old): {', '.join(skipped_old)}")
    if no_id:
        info(f"Tanpa [id] di nama, dilewati: {', '.join(no_id)}")
    return 0
