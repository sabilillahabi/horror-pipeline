"""Push the media that .gitignore keeps off main to the `muse-assets` branch (Muse/cloud restores it).

    python scripts/push_assets.py                 # default set below, commit + push
    python scripts/push_assets.py --dry-run       # list what would go up, sizes, skips
    python scripts/push_assets.py --story juru-kunci --ep ep02   # a new episode's assets

`muse-assets` holds ONLY asset files (no code, no yaml), so restoring it can never overwrite scripts:
    git fetch origin muse-assets && git checkout origin/muse-assets -- stories assets

How: files are hashed straight into git objects with a private index (`git hash-object` /
`update-index` / `write-tree` / `commit-tree`) and the new commit is pushed to refs/heads/muse-assets.
The working tree, the current branch and .gitignore are never touched. Never included: .env, .venv,
cache/, output/, Windows system fonts, anything over 95 MB (listed as skipped).
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAX_BYTES = 95 * 1024 * 1024
BRANCH = "muse-assets"
NEVER = {".env", ".venv", "venv", "cache", "output", "__pycache__", "_backup", "_orig"}
# Microsoft / Windows system fonts may not be redistributed; open fonts (Oswald, Liberation, DejaVu,
# Noto, Inter, Anton, Bebas, Lora, ...) are fine.
SYSTEM_FONTS = ("arial", "ariblk", "impact", "georgia", "times", "segoe", "seg", "bahnschrift", "calibri",
                "cambria", "candara", "consola", "constan", "corbel", "verdana", "tahoma", "trebuc", "comic",
                "cour", "lucon", "pala", "framd", "gadugi", "malgun", "micross", "msyh", "simsun", "sylfaen",
                "symbol", "webdings", "wingding", "marlett", "javatext", "mvboli", "ebrima", "nirmala", "leelaw",
                "himalaya", "taile", "mmrtext", "monbaiti", "ntailu", "phagspa", "yu", "meiryo", "msgothic",
                "gabriola", "holomdl2", "inkfree", "sitka", "franklin", "garamond", "bookos", "century", "gil",
                "tw", "rock", "lato-hairline-ms")


def git(*args, env=None, input=None) -> str:
    p = subprocess.run(["git", *args], cwd=ROOT, env=env, input=input, stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
    if p.returncode:
        raise SystemExit(f"git {' '.join(args[:3])} gagal:\n{p.stderr.strip()[-800:]}")
    return p.stdout.strip()


def is_system_font(p: Path) -> bool:
    n = p.name.lower()
    return any(n.startswith(s) for s in SYSTEM_FONTS)


def collect(stories: list[tuple[str, str]]) -> tuple[list[Path], list[tuple[Path, str]]]:
    roots = []
    for story, ep in stories:
        e = ROOT / "stories" / story / "episodes" / ep
        roots += [e / "images", e / "audio" / "gemini", e / "thumbnail"]
    roots += [ROOT / "assets" / "sound", ROOT / "assets" / "fonts"]
    files, skipped = [], []
    for r in roots:
        if not r.exists():
            skipped.append((r, "folder tidak ada"))
            continue
        for p in sorted(r.rglob("*")):
            if not p.is_file():
                continue
            rel = p.relative_to(ROOT)
            if NEVER & set(rel.parts) or p.name.startswith(".") and p.name != ".import_manifest.json":
                continue
            if p.suffix.lower() in (".tmp", ".part") or ".part." in p.name:
                continue
            if r.name == "fonts" and p.suffix.lower() in (".ttf", ".otf", ".ttc") and is_system_font(p):
                skipped.append((rel, "font sistem Windows (tidak boleh dibagikan)"))
                continue
            if p.stat().st_size > MAX_BYTES:
                skipped.append((rel, f"{p.stat().st_size / 1e6:.0f} MB > 95 MB"))
                continue
            files.append(p)
    return files, skipped


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--story", action="append", help="slug (default juru-kunci)")
    ap.add_argument("--ep", action="append", help="episode folder, e.g. ep01 (default ep01)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--remote", default="origin")
    a = ap.parse_args()
    stories = list(zip(a.story or ["juru-kunci"], a.ep or ["ep01"]))
    files, skipped = collect(stories)
    total = sum(p.stat().st_size for p in files)
    for rel, why in skipped:
        print(f"  dilewati: {rel}  ({why})")
    print(f"{len(files)} file, {total / 1e6:.1f} MB")
    if a.dry_run or not files:
        return 0

    subprocess.run(["git", "fetch", a.remote, BRANCH], cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    parent = subprocess.run(["git", "rev-parse", "--verify", "-q", f"{a.remote}/{BRANCH}"], cwd=ROOT,
                            stdout=subprocess.PIPE, text=True).stdout.strip()
    with tempfile.TemporaryDirectory() as tmp:
        env = {**os.environ, "GIT_INDEX_FILE": str(Path(tmp) / "index")}
        if parent:  # keep earlier episodes' assets: start from the branch's current tree
            git("read-tree", parent, env=env)
        for i, p in enumerate(files, 1):
            sha = git("hash-object", "-w", str(p))
            git("update-index", "--add", "--cacheinfo", f"100644,{sha},{p.relative_to(ROOT).as_posix()}", env=env)
            if i % 100 == 0:
                print(f"  {i}/{len(files)}")
        tree = git("write-tree", env=env)
    if parent and git("rev-parse", f"{parent}^{{tree}}") == tree:
        print(f"{BRANCH} sudah sama, tidak ada yang di-push.")
        return 0
    msg = f"Assets: {', '.join(f'{s}/{e}' for s, e in stories)} + assets/sound + assets/fonts ({len(files)} file)"
    commit = git("commit-tree", tree, *(["-p", parent] if parent else []), "-m", msg)
    print(f"push {commit[:8]} → {a.remote}/{BRANCH} ...")
    p = subprocess.run(["git", "push", a.remote, f"{commit}:refs/heads/{BRANCH}"], cwd=ROOT)
    if p.returncode:
        return p.returncode
    print(f"OK: {len(files)} file, {total / 1e6:.1f} MB di {BRANCH}")
    print(f"Pulihkan: git fetch {a.remote} {BRANCH} && git checkout {a.remote}/{BRANCH} -- stories assets")
    return 0


if __name__ == "__main__":
    sys.exit(main())
