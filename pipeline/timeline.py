"""Timeline (segment timings), padded narration track and SRT generation."""
from __future__ import annotations

import re
import wave
from dataclasses import dataclass
from pathlib import Path

from .common import (SAMPLE_RATE, Beat, Episode, PipelineError, fmt_ts, probe_duration,
                     quantize, roman)


@dataclass
class Segment:
    kind: str                 # recap | card | beat | intro | outro
    slot: float               # seconds this segment occupies on the timeline
    audio: Path | None = None
    audio_dur: float = 0.0
    beat: Beat | None = None
    text: str = ""            # spoken text (for subtitles)
    card: dict | None = None  # chapter card info
    start: float = 0.0
    chapter: int | None = None
    lead: float = 0.0         # silence before the audio starts within the slot


STRUCTURE_DEFAULTS = {"intro": True, "chapter_cards": True, "cold_open": 0.0}


def structure(ep: Episode) -> dict:
    """Episode layout: built-in defaults ← channels/<slug>.yaml `structure:` ← story.yaml `structure:`."""
    out = dict(STRUCTURE_DEFAULTS)
    slug = ep.story.get("channel")
    if slug:
        from .channel import Channel
        out.update(Channel(str(slug)).cfg.get("structure") or {})
    out.update(ep.story.get("structure") or {})
    return out


def build_timeline(ep: Episode, beats: list[Beat] | None = None, recap: bool = True,
                   cards: bool = True, final_hold: float | None = None,
                   require_audio: bool = True) -> list[Segment]:
    r = ep.render
    fps = int(r["fps"])
    segs: list[Segment] = []
    missing = []
    cards = cards and structure(ep)["chapter_cards"]

    def audio_of(key: str, text: str):
        if not text:
            return None, 0.0
        p = ep.audio_path(key)
        if not p.exists():
            missing.append(key)
            return None, 0.0
        return p, probe_duration(p)

    full = beats is None
    if full and recap and ep.recap:
        p, d = audio_of("recap", ep.recap)
        segs.append(Segment("recap", quantize(d + r["recap_pause"], fps), p, d, text=ep.recap))

    beat_list = ep.beats if full else beats
    last_in_chapter = {}
    for b in ep.beats:
        last_in_chapter[b.chapter] = b.key
    current_ch = None
    for i, b in enumerate(beat_list):
        if full and cards and b.chapter != current_ch:
            ch = ep.chapters[b.chapter]
            segs.append(Segment("card", quantize(r["chapter_card"], fps), chapter=b.chapter, card={
                "top": f"EPISODE {ep.number}  ·  BAB {roman(b.chapter + 1)}",
                "title": ch["title"],
            }))
        current_ch = b.chapter
        p, d = audio_of(b.key, b.text)
        if b.pause_after is not None:
            pause = b.pause_after
        elif full and last_in_chapter.get(b.chapter) == b.key:
            pause = r["chapter_end_pause"]
        else:
            pause = r["pause_after"]
        if not full and final_hold is not None and i == len(beat_list) - 1:
            pause = max(pause, final_hold)
        slot = max(d + pause, b.min_duration or 0.0, 0.5)
        segs.append(Segment("beat", quantize(slot, fps), p, d, beat=b, text=b.text,
                            chapter=b.chapter))

    if missing and require_audio:
        shown = ", ".join(missing[:8]) + (" ..." if len(missing) > 8 else "")
        raise PipelineError(f"Audio belum ada untuk: {shown}\n  Jalankan dulu: tts {ep.slug} {ep.ep}")
    t = 0.0
    for s in segs:
        s.start = t
        t += s.slot
    return segs


def total_duration(segs: list[Segment]) -> float:
    return sum(s.slot for s in segs)


# ---------------------------------------------------------------- narration track
def write_narration(segs: list[Segment], out: Path) -> None:
    """Concatenate per-segment audio padded with silence to each slot (sample exact)."""
    out.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        for s in segs:
            n_slot = int(round(s.slot * SAMPLE_RATE))
            data = b"\x00\x00" * int(round(s.lead * SAMPLE_RATE))
            if s.audio:
                with wave.open(str(s.audio), "rb") as a:
                    if (a.getnchannels(), a.getsampwidth(), a.getframerate()) != (1, 2, SAMPLE_RATE):
                        raise PipelineError(f"Format audio tak terduga: {s.audio} (jalankan tts --force)")
                    data += a.readframes(max(0, min(a.getnframes(), n_slot - len(data) // 2)))
            w.writeframes(data + b"\x00\x00" * (n_slot - len(data) // 2))


# ---------------------------------------------------------------- subtitles
def chunk_text(text: str, max_chars: int = 84) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    pieces = []
    for sent in re.split(r"(?<=[.!?…])\s+", text):
        if len(sent) <= max_chars:
            pieces.append(sent)
            continue
        for part in re.split(r"(?<=[,;:—])\s+", sent):
            if len(part) <= max_chars:
                pieces.append(part)
                continue
            cur = ""
            for word in part.split(" "):
                if cur and len(cur) + 1 + len(word) > max_chars:
                    pieces.append(cur)
                    cur = word
                else:
                    cur = f"{cur} {word}".strip()
            if cur:
                pieces.append(cur)
    merged: list[str] = []
    for p in pieces:
        if merged and len(merged[-1]) + 1 + len(p) <= max_chars * 0.75:
            merged[-1] = f"{merged[-1]} {p}"
        else:
            merged.append(p)
    return merged


def wrap_lines(text: str, width: int = 42) -> str:
    if len(text) <= width:
        return text
    words = text.split(" ")
    best, best_diff = text, 10**9
    for i in range(1, len(words)):
        a, b = " ".join(words[:i]), " ".join(words[i:])
        diff = abs(len(a) - len(b))
        if diff < best_diff:
            best, best_diff = f"{a}\n{b}", diff
    return best


def subtitle_cues(segs: list[Segment], max_chars: int = 84) -> list[tuple[float, float, str]]:
    cues = []
    for s in segs:
        if not s.text or not s.audio_dur:
            continue
        chunks = chunk_text(s.text, max_chars)
        total = sum(len(c) for c in chunks) or 1
        t = s.start + s.lead
        for c in chunks:
            d = s.audio_dur * len(c) / total
            cues.append((t, t + d, c))
            t += d
    return cues


def write_srt(segs: list[Segment], out: Path) -> None:
    lines = []
    for i, (a, b, text) in enumerate(subtitle_cues(segs), 1):
        lines += [str(i), f"{fmt_ts(a, True)} --> {fmt_ts(b, True)}", wrap_lines(text), ""]
    out.write_text("\n".join(lines), encoding="utf-8")


def write_description(ep: Episode, segs: list[Segment], out: Path) -> None:
    """YouTube description draft with chapter timestamps (first must be 00:00)."""
    lines = [f"{ep.story.get('title', ep.slug)} — Episode {ep.number}: {ep.title}", ""]
    stamps = []
    if any(s.kind == "recap" for s in segs):
        stamps.append((0.0, "Sebelumnya..."))
    # chapter starts come from the data (first beat of each chapter), with or without title cards
    seen = set()
    for s in segs:
        if s.kind in ("card", "beat") and s.chapter is not None and s.chapter not in seen:
            seen.add(s.chapter)
            stamps.append((s.start, f"Bab {roman(s.chapter + 1)}: {ep.chapters[s.chapter]['title']}"))
    if stamps:
        stamps[0] = (0.0, stamps[0][1])
        lines += [f"{fmt_ts(t)} {name}" for t, name in stamps]
    tag = ep.story.get("hashtag")
    if tag:
        lines += ["", " ".join(t if t.startswith("#") else f"#{t}" for t in str(tag).split())]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
