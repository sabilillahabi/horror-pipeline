"""Pre-render vertical clips for the full episode up to the first beat that still lacks audio.

Clip cache keys depend on slot length and the shot plan order, so only shots before the first missing
beat are guaranteed to match the later full `build --vertical`.

    python scripts/warm_vertical.py juru-kunci 1
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline.common import Episode, info, quantize  # noqa: E402
from pipeline.timeline import Segment, build_timeline, structure  # noqa: E402
from pipeline import vertical as Vt  # noqa: E402


def main() -> int:
    ep = Episode(sys.argv[1], sys.argv[2])
    ep.tts_engine = "gemini"
    segs = build_timeline(ep, require_audio=False)
    lay = structure(ep)
    if float(lay["cold_open"] or 0) > 0:
        segs.insert(0, Segment("lead", quantize(float(lay["cold_open"]), int(ep.render["fps"]))))
    stop = next((i for i, s in enumerate(segs) if s.kind == "beat" and s.text and not s.audio), len(segs))
    shots = Vt.plan(ep, segs[:stop])
    info(f"{len(shots)} shot vertikal sebelum beat tanpa audio pertama "
         f"({segs[stop].beat.key if stop < len(segs) else '-'})")
    Vt.render(ep, shots, force=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
