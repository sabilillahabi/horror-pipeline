"""Shared helpers: paths, YAML loading, beat normalisation, ffmpeg wrappers, fonts."""
from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
import subprocess
import wave
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
STORIES = ROOT / "stories"
ASSETS = ROOT / "assets"
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")
AUDIO_EXTS = (".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac")
CROPS = ("wide", "closeup_face", "detail")
VISUALS = ("image", "black", "text_card")
EFFECTS = ("none", "phone", "echo", "whisper")
SAMPLE_RATE = 48000

DEFAULT_RENDER = {
    "width": 1920,
    "height": 1080,
    "fps": 30,
    "max_shot": 12.0,          # max seconds a single image/crop stays on screen
    "crossfade": 0.5,          # seconds
    "pause_after": 0.35,       # default silence after each beat
    "max_pause": 0.6,          # hard cap on pause_after (pace rule: 130-150 wpm)
    "cliff_pause": 1.0,        # pause after a part's last (cliffhanger) beat; also its cap
    "max_black": 1.5,          # a black beat lasts at most this long (unless its line is longer)
    "recap_pause": 0.8,
    "chapter_card": 3.0,       # seconds
    "zoom": 0.12,              # Ken Burns zoom amount (0.12 = 12%)
    "grain": 2,                # film grain strength (0 = off); 2 keeps parts ~35 MB, 5+ hits the 6M cap
    "bgm_volume": 0.16,
    "duck": True,              # lower music while someone is speaking
    "crf": 22,                 # see pipeline/encode.py (hardware encoder or libx264 veryfast)
    "preset": "veryfast",
    "clip_preset": "veryfast", # per-shot intermediate encode preset
    "chunk_size": 48,          # shots per crossfade batch
    "kb_scale": 1.5,           # sources are scaled once to this multiple of the output size
}

# Words in a styles.yaml direction that make Gemini read slowly; at most MAX_SLOW_PER_PART lines per part.
SLOW_WORDS = ("pelan", "lambat", "jeda panjang", "jeda dramatis", "berhenti sejenak", "diseret", "sangat serius",
              "ditekan", "berat")
MAX_SLOW_PER_PART = 3
DEFAULT_PACE = "Tempo sedang, mengalir, tidak diseret."
WORDS_MIN, WORDS_MAX = 1100, 1300       # words per episode
PARTS_MIN, PARTS_MAX = 3, 4             # parts per episode
PART_MAX_S, PART_TARGET = 175.0, (150.0, 170.0)   # <= 2:55 (YouTube Shorts), target 2:30-2:50
WPM_LOW, WPM_HIGH, WPM_TARGET = 120, 165, (130, 150)


def is_slow_style(text: str) -> bool:
    t = (text or "").lower()
    return any(w in t for w in SLOW_WORDS)


class PipelineError(Exception):
    """User-facing error (printed without a traceback)."""


# ---------------------------------------------------------------- printing
def info(msg: str) -> None:
    print(f"  {msg}", flush=True)


def ok(msg: str) -> None:
    print(f"✔ {msg}", flush=True)


def warn(msg: str) -> None:
    print(f"⚠ {msg}", flush=True)


def step(msg: str) -> None:
    print(f"\n▶ {msg}", flush=True)


# ---------------------------------------------------------------- utils
def sha(obj) -> str:
    return hashlib.sha1(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:12]


def file_sig(p: Path | None):
    if not p or not p.exists():
        return None
    st = p.stat()
    return [str(p), st.st_size, int(st.st_mtime)]


def fmt_ts(sec: float, srt: bool = False) -> str:
    ms = int(round(sec * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    if srt:
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
    return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def quantize(sec: float, fps: int) -> float:
    """Round a duration up to a whole number of video frames."""
    return math.ceil(sec * fps - 1e-6) / fps


def norm_ep(ep: str) -> str:
    m = re.fullmatch(r"(?:ep)?0*(\d+)", str(ep).strip().lower())
    if not m:
        raise PipelineError(f"Format episode tidak dikenal: '{ep}' (contoh: ep01 atau 1)")
    return f"ep{int(m.group(1)):02d}"


def roman(n: int) -> str:
    vals = [(10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]
    out = ""
    for v, s in vals:
        while n >= v:
            out += s
            n -= v
    return out


# ---------------------------------------------------------------- ffmpeg
def require_ffmpeg() -> None:
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            raise PipelineError(
                f"'{tool}' tidak ditemukan. Install ffmpeg dan pastikan ada di PATH "
                "(Windows: winget install ffmpeg, macOS: brew install ffmpeg)."
            )


def run(cmd: list, desc: str = "ffmpeg") -> None:
    cmd = [str(c) for c in cmd]
    if cmd[0] == "ffmpeg":
        cmd[1:1] = ["-hide_banner", "-loglevel", "error", "-nostdin"]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                          encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.strip().splitlines()[-15:])
        raise PipelineError(f"{desc} gagal (kode {proc.returncode}):\n{tail}")


_FFV: list = []


def filter_script_flag() -> str:
    """ffmpeg 7+: `-/filter_complex <file>`; ffmpeg 6 (e.g. Linux distro builds): `-filter_complex_script`."""
    if not _FFV:
        out = subprocess.run(["ffmpeg", "-hide_banner", "-version"], stdout=subprocess.PIPE, text=True).stdout
        m = re.search(r"ffmpeg version n?(\d+)", out)
        _FFV.append(int(m.group(1)) if m else 7)
    return "-/filter_complex" if _FFV[0] >= 7 else "-filter_complex_script"


def probe_duration(path: Path) -> float:
    if path.suffix.lower() == ".wav":
        try:
            with wave.open(str(path), "rb") as w:
                return w.getnframes() / float(w.getframerate())
        except wave.Error:
            pass
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
         "default=nw=1:nk=1", str(path)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    ).stdout.strip()
    try:
        return float(out)
    except ValueError:
        raise PipelineError(f"Tidak bisa membaca durasi: {path}")


def atomic_out(path: Path) -> Path:
    """Temp path next to `path` (same extension so ffmpeg picks the muxer)."""
    return path.with_name(path.stem + ".part" + path.suffix)


# ---------------------------------------------------------------- fonts
_FONT_CANDIDATES = [
    # Windows
    "C:/Windows/Fonts/impact.ttf", "C:/Windows/Fonts/seguibl.ttf", "C:/Windows/Fonts/arialbd.ttf",
    # macOS
    "/System/Library/Fonts/Supplemental/Impact.ttf", "/Library/Fonts/Impact.ttf",
    "/System/Library/Fonts/Supplemental/Arial Black.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    # Linux
    "/usr/share/fonts/truetype/msttcorefonts/Impact.ttf",
    "/usr/share/fonts/opentype/inter/Inter-Black.otf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
]


_SERIF_CANDIDATES = [
    "C:/Windows/Fonts/georgia.ttf", "C:/Windows/Fonts/times.ttf",
    "/System/Library/Fonts/Supplemental/Georgia.ttf", "/Library/Fonts/Georgia.ttf",
    "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
    "/usr/share/fonts/truetype/noto/NotoSerif-Regular.ttf",
]


def find_serif_font(story_cfg: dict | None = None) -> str | None:
    """Serif font for text cards: story.yaml `card_font` → assets/fonts/serif/* → system serif."""
    if story_cfg and story_cfg.get("card_font"):
        p = Path(story_cfg["card_font"])
        for cand in (p, ROOT / p, ASSETS / "fonts" / p):
            if cand.exists():
                return str(cand)
        warn(f"Font '{story_cfg['card_font']}' tidak ditemukan, pakai serif sistem.")
    d = ASSETS / "fonts" / "serif"
    if d.exists():
        files = sorted(f for f in d.iterdir() if f.suffix.lower() in (".ttf", ".otf"))
        if files:
            return str(files[0])
    for c in _SERIF_CANDIDATES:
        if Path(c).exists():
            return c
    from . import fonts
    return fonts.path("serif_regular") or find_font(story_cfg)


def find_font(story_cfg: dict | None = None, key: str = "font") -> str | None:
    """Font priority: story.yaml `font`/`subtitle_font` → assets/fonts/* → system bold fonts."""
    if story_cfg and story_cfg.get(key):
        p = Path(story_cfg[key])
        for cand in (p, ROOT / p, ASSETS / "fonts" / p):
            if cand.exists():
                return str(cand)
        warn(f"Font '{story_cfg[key]}' tidak ditemukan, pakai font cadangan.")
    fonts_dir = ASSETS / "fonts"
    if fonts_dir.exists():
        files = sorted(f for f in fonts_dir.iterdir() if f.suffix.lower() in (".ttf", ".otf"))
        if files:
            return str(files[0])
    for c in _FONT_CANDIDATES:
        if Path(c).exists():
            return c
    from . import fonts
    return fonts.path("impact") or fonts.path("sans_bold")


# ---------------------------------------------------------------- data model
@dataclass
class Character:
    name: str
    block: str = ""
    voice: str = "id-ID-ArdiNeural"
    pitch: str = "+0Hz"
    rate: str = "+0%"
    volume: str = "+0%"
    effect: str = "none"
    reference: str | None = None


@dataclass
class Beat:
    id: object
    key: str
    chapter: int            # 0-based
    speaker: str
    text: str
    scene: str
    chars: list             # [(name, position, view)]
    visual: str = "image"
    image_from: str | None = None   # key of beat whose image is reused
    crop: str = "wide"
    focus: tuple | None = None
    min_duration: float | None = None
    pause_after: float | None = None
    effect: str | None = None
    card_text: str | None = None
    raw: dict = field(default_factory=dict)

    @property
    def long_only(self) -> bool:
        """`long_only: true` (e.g. a "Bersambung" card): in the long video only, never in a vertical part."""
        return bool(self.raw.get("long_only"))

    @property
    def num(self) -> int | None:
        """Numeric part of the id: 18 for `18`, `b018` and `b018a`."""
        return id_number(self.id)


def id_number(bid) -> int | None:
    if isinstance(bid, int):
        return bid
    m = re.search(r"\d+", str(bid))
    return int(m.group()) if m else None


def beat_key(bid) -> str:
    """File stem for a beat. Numeric ids → beat_001; text ids are used as-is (b018a → b018a)."""
    if isinstance(bid, int) or (isinstance(bid, str) and bid.strip().isdigit()):
        return f"beat_{int(bid):03d}"
    s = re.sub(r"[^\w\-]+", "_", str(bid).strip())
    if not s:
        raise PipelineError(f"ID beat tidak valid: {bid!r}")
    return s


def _parse_chars(raw) -> list:
    """characters_in_scene → [(name, position, view)].

    Accepts {name, position, view}, {Dimas: left} and "Dimas:left" forms."""
    out = []
    for item in raw or []:
        if isinstance(item, str):
            name, _, pos = item.partition(":")
            out.append((name.strip(), pos.strip(), ""))
        elif isinstance(item, dict):
            if "name" in item:
                out.append((str(item["name"]).strip(), str(item.get("position", "") or "").strip(),
                            str(item.get("view", "") or "").strip()))
            else:  # {Dimas: left}
                for k, v in item.items():
                    out.append((str(k).strip(), str(v or "").strip(), ""))
    return out


def _parse_focus(v):
    if v is None:
        return None
    if isinstance(v, (list, tuple)) and len(v) == 2:
        return (float(v[0]), float(v[1]))
    raise PipelineError(f"focus harus [x, y] dengan nilai 0..1, dapat: {v}")


class Episode:
    def __init__(self, story: str, ep: str):
        self.slug = story
        self.ep = norm_ep(ep)
        self.story_dir = STORIES / story
        self.dir = self.story_dir / "episodes" / self.ep
        if not (self.story_dir / "story.yaml").exists():
            raise PipelineError(f"Tidak ada {self.story_dir / 'story.yaml'}")
        if not (self.dir / "script.yaml").exists():
            raise PipelineError(f"Tidak ada {self.dir / 'script.yaml'}")
        self.images = self.dir / "images"
        self.audio = self.dir / "audio"
        self.output = self.dir / "output"
        self.cache = self.dir / "cache"
        for d in (self.images, self.audio, self.output, self.cache):
            d.mkdir(parents=True, exist_ok=True)

        self.story = self._load(self.story_dir / "story.yaml")
        self.script = self._load(self.dir / "script.yaml")
        self.render = {**DEFAULT_RENDER, **(self.story.get("render") or {}),
                       **(self.script.get("render") or {})}
        self.characters = self._load_characters()
        # TTS engine: story.yaml `tts_engine` (edge | gemini); `--engine` on the CLI overrides it
        self.tts_engine = str(self.story.get("tts_engine") or "edge").strip().lower()
        styles = self.dir / "styles.yaml"
        self.beat_styles = ({beat_key(k): str(v or "") for k, v in self._load(styles).items()}
                            if styles.exists() else {})
        self.chapters = []          # = parts (the old `chapters:` key is still read)
        self.beats: list[Beat] = []
        self._load_beats()

    @property
    def parts(self) -> list[dict]:
        return self.chapters

    def part_beats(self, i: int) -> list[Beat]:
        return [b for b in self.beats if b.chapter == i]

    @property
    def tts_locked(self) -> bool:
        """script.yaml `tts: {locked: true}`: existing clips are never regenerated (e.g. re-paced ep01)."""
        return bool((self.script.get("tts") or {}).get("locked"))

    # ---------------------------------------------------------------- loading
    @staticmethod
    def _load(path: Path) -> dict:
        try:
            with open(path, encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            raise PipelineError(f"YAML tidak valid di {path}:\n{e}")

    def _load_characters(self) -> dict:
        chars = {}
        raw = self.story.get("characters") or []
        if isinstance(raw, dict):  # also allow {name: {...}}
            raw = [{"name": k, **(v or {})} for k, v in raw.items()]
        # characters without their own voice settings (visual-only, e.g. `bayu`) inherit the
        # narrator's; `voice: narrator` does the same explicitly
        narr = next((c for c in raw if str(c.get("name", "")).strip().lower() == "narrator"), {})
        voice_keys = ("voice", "pitch", "rate", "volume")
        for c in raw:
            if "name" not in c:
                raise PipelineError(f"Karakter tanpa 'name' di story.yaml: {c}")
            name = str(c["name"]).strip()
            if str(c.get("voice", "")).strip().lower() == "narrator" or "voice" not in c:
                c = {**{k: narr[k] for k in voice_keys if k in narr},
                     **{k: v for k, v in c.items() if k != "voice" or str(v).lower() != "narrator"}}
            effect = str(c.get("effect", "none") or "none").lower()
            if effect not in EFFECTS:
                raise PipelineError(f"Efek '{effect}' untuk {name} tidak dikenal. Pilihan: {EFFECTS}")
            block = next((c[k] for k in ("character_block", "block", "description", "visual")
                          if c.get(k)), "")
            chars[name.lower()] = Character(
                name=name,
                block=" ".join(str(block).split()),
                voice=c.get("voice", "id-ID-ArdiNeural"),
                pitch=_signed(c.get("pitch", "+0Hz"), "Hz"),
                rate=_signed(c.get("rate", "+0%"), "%"),
                volume=_signed(c.get("volume", "+0%"), "%"),
                effect=effect,
                reference=c.get("reference"),
            )
        if "narrator" not in chars:
            warn("story.yaml belum punya karakter 'narrator' — memakai id-ID-ArdiNeural default.")
            chars["narrator"] = Character(name="narrator")
        return chars

    def _load_beats(self) -> None:
        chapters = self.script.get("parts") or self.script.get("chapters") or []
        if not chapters:
            raise PipelineError("script.yaml tidak punya 'parts:' (atau 'chapters:' versi lama).")
        self.uses_parts = bool(self.script.get("parts"))
        seen = {}
        for ci, ch in enumerate(chapters):
            self.chapters.append({"title": str(ch.get("title", f"Part {ci + 1}")), "index": ci,
                                  # part-level default pause between beats (still capped by max_pause)
                                  "pause_after": _opt_float(ch.get("pause_after"))})
            for b in ch.get("beats") or []:
                if "id" not in b:
                    raise PipelineError(f"Ada beat tanpa 'id' di part {ci + 1}.")
                key = beat_key(b["id"])
                if key in seen:
                    raise PipelineError(f"ID beat dobel: {b['id']}")
                visual = str(b.get("visual", "image") or "image").lower()
                if visual not in VISUALS:
                    raise PipelineError(f"Beat {b['id']}: visual '{visual}' tidak dikenal {VISUALS}")
                speaker = str(b.get("speaker", "narrator") or "narrator").strip()
                if speaker.lower() not in self.characters:
                    raise PipelineError(f"Beat {b['id']}: speaker '{speaker}' tidak ada di story.yaml")
                effect = b.get("effect")
                if effect is not None and str(effect).lower() not in EFFECTS:
                    raise PipelineError(f"Beat {b['id']}: efek '{effect}' tidak dikenal {EFFECTS}")
                crop, focus = str(b.get("crop", "wide") or "wide"), b.get("focus")
                ref = b.get("reuse")  # `reuse: b018` + `crop:` (preferred form)
                img = b.get("image")
                if isinstance(img, dict):
                    ref = img.get("beat", img.get("from", img.get("reuse", ref)))
                    crop = str(img.get("crop", crop))
                    focus = img.get("focus", focus)
                elif isinstance(img, (str, int)) and str(img).strip():
                    s = str(img).strip()
                    if s in CROPS:
                        crop = s
                    else:
                        src, _, c = s.partition(":")
                        ref = src.strip()
                        if c:
                            crop = c.strip()
                crop = crop.strip().lower()
                if crop not in CROPS:
                    raise PipelineError(f"Beat {b['id']}: crop '{crop}' tidak dikenal {CROPS}")
                beat = Beat(
                    id=b["id"], key=key, chapter=ci, speaker=speaker,
                    text=str(b.get("text", "") or "").strip(),
                    scene=str(b.get("scene", "") or "").strip(),
                    chars=_parse_chars(b.get("characters_in_scene")),
                    visual=visual, image_from=None if ref is None or str(ref).strip() == "" else str(ref),
                    crop=crop, focus=_parse_focus(focus),
                    min_duration=_opt_float(b.get("min_duration")),
                    pause_after=_opt_float(b.get("pause_after")),
                    effect=str(effect).lower() if effect else None,
                    card_text=b.get("card_text"), raw=b,
                )
                for name, _, _ in beat.chars:
                    if name.lower() not in self.characters:
                        warn(f"Beat {b['id']}: karakter '{name}' tidak ada di story.yaml")
                if not beat.text and not beat.min_duration:
                    if visual == "text_card" and beat.card_text:
                        beat.min_duration = 3.0  # silent title-style card
                    else:
                        raise PipelineError(f"Beat {b['id']}: tanpa text wajib punya min_duration.")
                seen[key] = beat
                self.beats.append(beat)
        self.by_key = seen
        # resolve `reuse` references (may point forward, or be written as 18 / b018 / beat_018)
        for b in self.beats:
            if b.image_from:
                src = self.resolve_ref(b.image_from)
                if src is None:
                    raise PipelineError(f"Beat {b.id}: reuse merujuk '{b.image_from}' yang tidak ada.")
                b.image_from = None if src.key == b.key else src.key
        for b in self.beats:
            if b.image_from:
                src, hops = seen[b.image_from], 0
                while src.image_from:  # follow chains (reuse of a reuse)
                    src = seen[src.image_from]
                    hops += 1
                    if hops > 50:
                        raise PipelineError(f"Beat {b.id}: rujukan reuse melingkar.")
                if src.visual != "image":
                    raise PipelineError(f"Beat {b.id}: reuse '{src.id}' bukan beat bergambar ({src.visual}).")
                b.image_from = src.key

    def resolve_ref(self, ref) -> Beat | None:
        """Find a beat by id: exact id/key first, then by number (18 → b018 if unambiguous)."""
        s = str(ref).strip()
        for cand in (s, beat_key(s) if s else ""):
            if cand in self.by_key:
                return self.by_key[cand]
        for b in self.beats:
            if str(b.id).strip().lower() == s.lower():
                return b
        n = id_number(s)
        if n is not None and re.fullmatch(r"\D*\d+", s):
            matches = [b for b in self.beats if b.num == n and re.fullmatch(r"\D*\d+", str(b.id))]
            if len(matches) == 1:
                return matches[0]
        return None

    # ---------------------------------------------------------------- queries
    @property
    def number(self) -> int:
        return int(self.script.get("episode", int(self.ep[2:])))

    @property
    def title(self) -> str:
        return str(self.script.get("title", ""))

    @property
    def recap(self) -> str:
        return str(self.script.get("recap", "") or "").strip()

    def speaker(self, beat_or_name) -> Character:
        name = beat_or_name.speaker if isinstance(beat_or_name, Beat) else beat_or_name
        return self.characters[name.lower()]

    def needs_own_image(self, b: Beat) -> bool:
        return b.visual == "image" and not b.image_from

    def find_image(self, key: str) -> Path | None:
        for ext in IMAGE_EXTS:
            for e in (ext, ext.upper()):
                p = self.images / f"{key}{e}"
                if p.exists():
                    return p
        return None

    def image_for(self, b: Beat) -> Path | None:
        return self.find_image(b.image_from or b.key)

    def missing_images(self) -> list[Beat]:
        return [b for b in self.beats if self.needs_own_image(b) and not self.find_image(b.key)]

    @property
    def audio_dir(self) -> Path:
        """edge-tts clips live in audio/, Gemini clips in audio/gemini/ so neither overwrites the other."""
        return self.audio / "gemini" if self.tts_engine == "gemini" else self.audio

    def audio_path(self, key: str) -> Path:
        return self.audio_dir / f"{key}.wav"

    def recap_image(self) -> Path | None:
        r = self.script.get("recap_image")
        if not r:
            return None
        if isinstance(r, int) or (isinstance(r, str) and not Path(r).suffix):
            b = self.resolve_ref(r)
            return self.image_for(b) if b else None
        p = self.dir / r
        return p if p.exists() else None

    def reference_image(self, name: str) -> Path:
        c = self.characters.get(name.lower())
        if c and c.reference:
            return self.story_dir / c.reference
        d = self.story_dir / "characters"
        for ext in IMAGE_EXTS:
            for n in (name.lower(), name):
                p = d / f"{n}{ext}"
                if p.exists():
                    return p
        return d / f"{name.lower()}.png"

    def parse_beat_range(self, spec: str) -> list[Beat]:
        """`12-18`, `b012-b018a` (inclusive, script order) or a list `b003,b005`.

        A numeric end includes its suffixed beats: 12-18 also takes b018a, b018b."""
        spec = str(spec).strip()
        m = re.fullmatch(r"([\w]+?)\s*-\s*([\w]+)", spec)
        if m:
            a, b = m.group(1), m.group(2)
            start = self.resolve_ref(a)
            if start is None:
                na = id_number(a)
                start = next((bt for bt in self.beats if bt.num is not None and na is not None
                              and bt.num >= na), None)
            pre = lambda x: re.match(r"\D*", str(x)).group().lower()  # noqa: E731  ("b" in b018a)
            idx = [i for i, bt in enumerate(self.beats)
                   if bt is self.resolve_ref(b) or (re.fullmatch(r"\D*\d+", b) and bt.num == id_number(b)
                                                    and (pre(b) == "" or pre(bt.id) == pre(b)))]
            if start is None or not idx:
                raise PipelineError(f"Rentang beat '{spec}' tidak ditemukan.")
            i0, i1 = self.beats.index(start), max(idx)
            sel = self.beats[i0:i1 + 1]
        else:
            sel = [bt for x in spec.split(",") if x.strip() for bt in [self.resolve_ref(x.strip())] if bt]
        if not sel:
            raise PipelineError(f"Tidak ada beat yang cocok dengan '{spec}'.")
        return sel

    def get_beat(self, spec) -> Beat:
        b = self.resolve_ref(spec)
        if b is None:
            raise PipelineError(f"Beat '{spec}' tidak ditemukan.")
        return b


def _signed(v, unit: str) -> str:
    s = str(v).strip().replace(" ", "")
    if not s:
        return f"+0{unit}"
    if not s.endswith(unit):
        s += unit
    if s[0] not in "+-":
        s = "+" + s
    return s


def _opt_float(v):
    return None if v is None or v == "" else float(v)
