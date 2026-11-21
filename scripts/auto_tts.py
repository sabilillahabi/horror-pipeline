"""Hourly unattended Gemini TTS retry for one episode (run by Windows Task Scheduler).

Each run: resume `tts` (it re-reads .env and tries every key once; a key over its daily quota
costs one quick request), log a one-line summary, and once every beat has audio: render the
chapter preview (if missing) + the full build, write the summary, and delete its own scheduled task.

    python scripts/auto_tts.py juru-kunci 1 --task-name HorrorPipeline-JuruKunci-TTS --preview b001-b027
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline.common import Episode, fmt_ts, probe_duration  # noqa: E402
from pipeline import gemini_tts as G  # noqa: E402

PY = sys.executable
LOCK_STALE = 6 * 3600  # a lock older than this is from a crashed run


def now() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M")


def scrub(text: str) -> str:
    try:
        keys = G.api_keys()
    except Exception:
        keys = []
    for k in keys:
        text = text.replace(k, "***")
    # belt and braces: anything shaped like a Google API key
    return re.sub(r"AIza[0-9A-Za-z_\-]{30,}", "***", text)


def status(slug: str, ep_no: str):
    ep = Episode(slug, ep_no)
    ep.tts_engine = "gemini"
    beats = [b for b in ep.beats if b.text]
    missing = [b.key for b in beats if not ep.audio_path(b.key).exists()]
    if ep.recap and not ep.audio_path("recap").exists():
        missing.insert(0, "recap")
    total = len(beats) + (1 if ep.recap else 0)
    from pipeline import channel  # intro/outro whispers count as two more clips
    ch = channel.for_episode(ep)
    if ch:
        missing = [f"channel:{r}" for r in ch.missing()] + missing
        total += len(channel.ROLES)
    return ep, total, missing


def run(args_list: list[str], log: Path) -> int:
    p = subprocess.run([PY, "-u", "horror.py", *args_list], cwd=ROOT, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                       env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    with open(log, "a", encoding="utf-8") as f:
        f.write(f"\n===== {now()}  horror.py {' '.join(args_list)}  (exit {p.returncode})\n")
        f.write(scrub(p.stdout))
    return p.returncode


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("story")
    ap.add_argument("ep")
    ap.add_argument("--task-name", required=True)
    ap.add_argument("--preview", help="beat range for the preview, e.g. b001-b027")
    a = ap.parse_args()

    ep, total, missing = status(a.story, a.ep)
    out = ep.output
    summary = out / "tts_log.txt"            # short, human-readable
    detail = ep.cache / "auto_tts_detail.log"  # full command output (keys scrubbed)
    lock = ep.cache / "auto_tts.lock"

    def note(line: str) -> None:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(f"{now()}  {scrub(line)}\n")

    if lock.exists() and time.time() - lock.stat().st_mtime < LOCK_STALE:
        note("percobaan dilewati: run sebelumnya masih berjalan")
        return 0
    lock.write_text(str(os.getpid()))
    try:
        if missing:
            before = len(missing)
            run(["tts", a.story, a.ep, "--engine", "gemini"], detail)
            ep, total, missing = status(a.story, a.ep)
            made = before - len(missing)
            tail = ""
            if missing:
                last = detail.read_text(encoding="utf-8", errors="replace").strip().splitlines()[-6:]
                why = next((l for l in reversed(last) if "Kuota" in l or "gagal" in l or "✗" in l), "")
                tail = f" · {why.strip()[:160]}" if why else ""
            note(f"TTS: +{made} klip · selesai {total - len(missing)}/{total}, sisa {len(missing)}{tail}")
        if missing:
            return 0  # next hourly run continues

        # ---- all audio present: preview (if needed) + full build, then remove the schedule
        if a.preview:
            first, last = a.preview.split("-")
            prev = out / f"preview_{first}-{last}.mp4"
            if not prev.exists():
                rc = run(["build", a.story, a.ep, "--engine", "gemini", "--beats", a.preview], detail)
                note(f"Preview {a.preview}: {'OK ' + str(prev) if rc == 0 else 'GAGAL (lihat cache/auto_tts_detail.log)'}")
        rc = run(["build", a.story, a.ep, "--engine", "gemini"], detail)
        final = out / f"{ep.ep}.mp4"
        if rc == 0 and final.exists():
            note(f"SELESAI: semua {total} beat punya audio Gemini. Video: {final} "
                 f"({fmt_ts(probe_duration(final))}), lapisan suara aktif.")
            subprocess.run(["schtasks", "/Delete", "/TN", a.task_name, "/F"], capture_output=True,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            note(f"Jadwal '{a.task_name}' dihapus.")
        else:
            note("Build penuh GAGAL (lihat cache/auto_tts_detail.log); dicoba lagi jam berikutnya.")
        return 0
    finally:
        lock.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
