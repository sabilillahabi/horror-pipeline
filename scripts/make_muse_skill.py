"""Assemble the Muse AI skill package: SKILL.md + references + pipeline code + story configs (no secrets, no media).

    python scripts/make_muse_skill.py              # → dist/horror-serial/ and dist/horror-serial-muse-skill.zip
    python scripts/make_muse_skill.py --out ~/Downloads
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAME = "horror-serial"

INCLUDE = [
    "horror.py", "requirements.txt", "README.md", ".gitignore",
    "pipeline/*.py", "scripts/auto_tts.py", "scripts/make_muse_skill.py",
    "channels/*.yaml", "channels/*/audio/*.wav", "channels/*/audio/raw/*.json",
    "assets/fonts/README.txt",
    "stories/*/story.yaml", "stories/*/sound_assets.yaml",
    "stories/*/episodes/*/script.yaml", "stories/*/episodes/*/styles.yaml",
    "stories/*/episodes/*/sound.yaml", "stories/*/episodes/*/covers.yaml",
    "stories/*/episodes/*/threads.yaml",
]
SECRET = re.compile(r"AIza[0-9A-Za-z_\-]{30,}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "dist"))
    a = ap.parse_args()
    out = Path(a.out).expanduser()
    stage = ROOT / "dist" / NAME
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)

    # skill docs at the package root
    shutil.copy2(ROOT / "SKILL.md", stage / "SKILL.md")
    shutil.copytree(ROOT / "references", stage / "references")
    files = sorted({p for pat in INCLUDE for p in ROOT.glob(pat) if p.is_file()})
    for p in files:
        rel = p.relative_to(ROOT)
        if rel.name == ".env" or "__pycache__" in rel.parts:
            continue
        dst = stage / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, dst)

    leaks = [str(p.relative_to(stage)) for p in stage.rglob("*")
             if p.is_file() and p.suffix in (".py", ".md", ".yaml", ".txt", ".json")
             and SECRET.search(p.read_text(encoding="utf-8", errors="ignore"))]
    if leaks:
        print(f"✗ API key ditemukan di: {', '.join(leaks)} — paket dibatalkan", file=sys.stderr)
        shutil.rmtree(stage)
        return 1

    out.mkdir(parents=True, exist_ok=True)
    zpath = out / f"{NAME}-muse-skill.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(stage.rglob("*")):
            if p.is_file():
                z.write(p, Path(NAME) / p.relative_to(stage))
    n = sum(1 for p in stage.rglob("*") if p.is_file())
    print(f"✔ {n} file → {zpath} ({zpath.stat().st_size / 1e6:.1f} MB); folder: {stage}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
