"""`import-flow` command: copy Google Flow downloads named "[b018a] ..." / "b018a_<hash>.jpg" into images/<id>.png.

Safety:
- No source given → the newest Flow download in ~/Downloads (a zip, a folder, or loose [bXXX]/bXXX_ image
  files), and the pick is printed.
- An existing images/<id> is never replaced by an older source file (source time = file mtime, or the
  entry date inside a zip, since extraction resets mtimes). A source identical to what was imported before
  (content hash, kept in images/.import_manifest.json) is skipped. --force overrides both.
- Every replaced file is backed up to images/_backup/<timestamp>/ first.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import shutil
import tempfile
import zipfile
from pathlib import Path

from .common import IMAGE_EXTS, ROOT, Episode, PipelineError, info, ok, step, warn
from . import thumbs
from . import visuals as V

ID_RE = re.compile(r"\[([^\[\]]+)\]")
LOOSE_RE = re.compile(r"^(b\d{2,3}[a-z]?)(?=$|[\s_\-.(])", re.I)   # b008_d3f570d4, b026a-2K, b021 (1)


def beat_id(stem: str) -> str | None:
    m = ID_RE.search(stem)
    if m:
        return m.group(1).strip()
    m = LOOSE_RE.match(stem)
    return m.group(1) if m else None


def _is_flow_image(name: str) -> bool:
    p = Path(name)
    return p.suffix.lower() in IMAGE_EXTS and not p.name.startswith("._") and beat_id(p.stem) is not None


def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ------------------------------------------------------------------ source selection
def _candidates(dl: Path) -> list[tuple[float, str, Path | list[Path]]]:
    """(time, label, source) for every Flow download in ~/Downloads."""
    out = []
    loose = [p for p in dl.iterdir() if p.is_file() and _is_flow_image(p.name)]
    if loose:
        t = max(p.stat().st_mtime for p in loose)
        out.append((t, f"{len(loose)} file gambar lepas di {dl}", loose))
    for p in dl.iterdir():
        try:
            if p.is_file() and p.suffix.lower() == ".zip":
                with zipfile.ZipFile(p) as z:
                    if any(_is_flow_image(n) for n in z.namelist()):
                        out.append((p.stat().st_mtime, f"zip {p.name}", p))
            elif p.is_dir() and not p.name.startswith("."):
                imgs = [f for f in p.rglob("*") if f.is_file() and _is_flow_image(f.name)]
                if imgs and len(imgs) < 2000:
                    out.append((max(f.stat().st_mtime for f in imgs), f"folder {p.name}", p))
        except (zipfile.BadZipFile, OSError, PermissionError):
            continue
    return out


def _pick_source(arg: str | None) -> tuple[str, Path | list[Path]]:
    if arg:
        p = Path(arg).expanduser()
        if not p.exists():
            raise PipelineError(f"Tidak ditemukan: {p}")
        return (f"zip {p.name}" if p.is_file() else f"folder {p}"), p
    dl = Path.home() / "Downloads"
    if not dl.exists():
        raise PipelineError("Folder ~/Downloads tidak ada; berikan path zip/folder secara eksplisit.")
    cands = _candidates(dl)
    if not cands:
        raise PipelineError(f"Tidak ada download Flow ([bXXX] / bXXX_...) di {dl}. Berikan path-nya.")
    t, label, src = max(cands, key=lambda c: c[0])
    return f"{label} (terbaru, {dt.datetime.fromtimestamp(t):%Y-%m-%d %H:%M})", src


# ------------------------------------------------------------------ command
def cmd_import(ep: Episode, args) -> int:
    step(f"Import gambar Flow → {ep.slug} {ep.ep}")
    label, src = _pick_source(args.source)
    info(f"Sumber: {label}")
    force = bool(getattr(args, "force", False))
    with tempfile.TemporaryDirectory(prefix="flow_") as tmp:
        mtimes: dict[Path, float] = {}
        if isinstance(src, list):
            files = src
        elif src.is_file():  # the zip is only read, never modified or deleted
            base = Path(tmp).resolve()
            with zipfile.ZipFile(src) as z:
                for m in z.infolist():
                    if not (base / m.filename).resolve().is_relative_to(base):
                        raise PipelineError(f"Zip berisi path tidak aman: {m.filename}")
                z.extractall(base)
                for m in z.infolist():  # extraction resets mtimes: use the zip entry's own date
                    mtimes[(base / m.filename).resolve()] = dt.datetime(*m.date_time).timestamp()
            files = [p for p in base.rglob("*") if p.is_file()]
        else:
            files = [p for p in src.rglob("*") if p.is_file()]
        files = [p for p in files if p.suffix.lower() in IMAGE_EXTS and not p.name.startswith("._")
                 and "__MACOSX" not in p.parts]
        src_time = lambda p: mtimes.get(p.resolve(), p.stat().st_mtime)  # noqa: E731

        # thumbnails: in the source, plus loose thumb_epXX_* files at the top of ~/Downloads
        dl = Path.home() / "Downloads"
        loose_t = [p for p in dl.iterdir() if p.is_file() and thumbs.match(p.stem)] if dl.exists() else []
        thumb_log = thumbs.import_from([p for p in files if thumbs.match(p.stem)] + loose_t, ep)
        files = [p for p in files if not thumbs.match(p.stem)]

        picked: dict[str, Path] = {}
        skipped_old, no_id = [], []
        for p in sorted(files):
            bid = beat_id(p.stem)
            if not bid:
                no_id.append(p.name)
                continue
            if bid.lower().endswith("-old"):
                skipped_old.append(p.name)
                continue
            beat = ep.resolve_ref(bid)
            key = beat.key if beat else bid
            if beat is None:
                warn(f"{p.name}: id '{bid}' tidak ada di script.yaml (tetap disalin sebagai {key}.png)")
            if key in picked:  # several takes for one beat: keep the newest
                keep = max(picked[key], p, key=src_time)
                warn(f"Dua file untuk {key}: '{picked[key].name}' dan '{p.name}' → pakai '{keep.name}'")
                p = keep
            picked[key] = p

        ep.images.mkdir(parents=True, exist_ok=True)
        man_path = ep.images / ".import_manifest.json"
        manifest = json.loads(man_path.read_text(encoding="utf-8")) if man_path.exists() else {}
        backup_dir = ep.images / "_backup" / dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        copied, kept, same, backed = [], [], [], 0
        for key, p in sorted(picked.items()):
            dst = ep.images / f"{key}.png"
            existing = [ep.images / f"{key}{ext}" for ext in IMAGE_EXTS if (ep.images / f"{key}{ext}").exists()]
            digest = _sha(p)
            t_src = src_time(p)
            if existing and not force:
                if manifest.get(key, {}).get("sha256") == digest:
                    same.append(key)
                    continue
                t_local = max(e.stat().st_mtime for e in existing)
                if t_src <= t_local:
                    kept.append((key, p.name, t_src, t_local))
                    continue
            for e in existing:  # back up everything this import replaces (incl. a shadowing .jpg)
                backup_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(e, backup_dir / e.name)
                backed += 1
                if e != dst:
                    e.unlink()
            if p.suffix.lower() == ".png":
                shutil.copy2(p, dst)
            else:
                V.load_rgb(p).save(dst)
            manifest[key] = {"sha256": digest, "source": p.name, "source_time": t_src,
                             "imported": dt.datetime.now().isoformat(timespec="seconds")}
            copied.append(key)
            print(f"  {p.name}  →  images/{dst.name}")
        man_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    ok(f"{len(copied)} gambar disalin ke {ep.images.relative_to(ROOT)}"
       + (f" · {backed} file lama dibackup ke {backup_dir.relative_to(ROOT)}" if backed else ""))
    if kept:
        warn(f"Dilewati, versi lokal lebih baru (kept newer local version) — pakai --force untuk menimpa:")
        for key, name, ts, tl in kept:
            print(f"    {key:<7} {name}  ({dt.datetime.fromtimestamp(ts):%Y-%m-%d %H:%M}) "
                  f"< lokal {dt.datetime.fromtimestamp(tl):%Y-%m-%d %H:%M}")
    if same:
        info(f"Sudah diimport sebelumnya (isi sama): {', '.join(same)}")
    for line in thumb_log:
        print(f"  {line}")
    if thumb_log:
        ok(f"{len(thumb_log)} thumbnail di {(ep.dir / 'thumbnail').relative_to(ROOT)}")
    missing_t = [r for r in thumbs.SIZES if not thumbs.path(ep, r).exists()]
    if missing_t:
        warn(f"Thumbnail belum ada: {', '.join(f'thumb_ep{ep.number:02d}_{r}' for r in missing_t)}")
    if skipped_old:
        info(f"Dilewati (-old): {', '.join(skipped_old)}")
    if no_id:
        info(f"Tanpa id beat di nama, dilewati: {', '.join(no_id[:10])}" + (" ..." if len(no_id) > 10 else ""))
    return 0
