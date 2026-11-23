"""Gemini TTS engine for the `tts` command (used when story.yaml has `tts_engine: gemini`).

Clips go to audio/gemini/ (raw model output in audio/gemini/raw/), separate from the edge-tts clips.
Every voice is checked against the live voice catalog before anything is generated.
"""
from __future__ import annotations

import base64
import difflib
import json
import os
import re
import time
import urllib.error
import urllib.request
import wave

from .common import ROOT, Episode, PipelineError, atomic_out, info, ok, sha, step, warn

DEFAULT_MODEL = "gemini-3.8-flash-tts"
API_BASE = "https://generativelanguage.googleapis.com/v1beta"
PCM_RATE = 24000  # documented default output: 24 kHz mono s16le
GEMINI_VERSION = 1
REQUEST_TIMEOUT = 180.0  # seconds per clip request


# ------------------------------------------------------------------ config / key
def read_env_file() -> dict:
    """KEY=VALUE lines from ROOT/.env (BOM, quotes and `export ` tolerated)."""
    p = ROOT / ".env"
    out = {}
    if p.exists():
        for line in p.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            out[k.strip().removeprefix("export ").strip()] = v.strip().strip('"').strip("'")
    return out


def _split(v: str | None) -> list[str]:
    return [k.strip() for k in (v or "").split(",") if k.strip()]


def api_keys() -> list[str]:
    """Keys in priority order. .env wins over the environment: GEMINI_API_KEYS (comma list) and/or
    GEMINI_API_KEY from .env; only if .env has none, the same variables from the environment."""
    def collect(src) -> list[str]:
        keys = _split(src.get("GEMINI_API_KEYS")) + _split(src.get("GEMINI_API_KEY"))
        return list(dict.fromkeys(keys))  # dedupe, keep order
    keys = collect(read_env_file()) or collect(os.environ)
    if not keys:
        raise PipelineError(f"Tidak ada API key. Tulis di {ROOT / '.env'}: GEMINI_API_KEY=... "
                            "atau GEMINI_API_KEYS=key1,key2")
    return keys


def api_key() -> str:
    return api_keys()[0]


class KeyRing:
    """Rotates to the next key when one hits its daily quota. Keys are only ever shown as #n/N."""

    def __init__(self, keys: list[str]):
        self.keys, self.i = keys, 0

    @property
    def key(self) -> str:
        return self.keys[self.i]

    @property
    def label(self) -> str:
        return f"key #{self.i + 1}/{len(self.keys)}"

    def scrub(self, text: str) -> str:
        for k in self.keys:
            text = text.replace(k, "***")
        return text

    def next(self) -> bool:
        if self.i + 1 >= len(self.keys):
            return False
        self.i += 1
        return True


class DailyQuota(Exception):
    pass


def speaker_cfg(ep: Episode, name: str) -> dict:
    voices = {str(k).lower(): v or {} for k, v in (ep.story.get("gemini_voices") or {}).items()}
    cfg = voices.get(name.lower())
    if not cfg or not cfg.get("voice"):
        raise PipelineError(f"gemini_voices.{name}.voice belum diisi di story.yaml")
    return cfg


# ------------------------------------------------------------------ voice catalog
def fetch_voices(key: str, cache_path) -> list[dict]:
    voices, token = [], None
    while True:
        url = f"{API_BASE}/voices?pageSize=1000" + (f"&pageToken={token}" if token else "")
        req = urllib.request.Request(url, headers={"x-goog-api-key": key})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                data = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:500]
            raise PipelineError(f"Gagal mengambil daftar voice (HTTP {e.code}): {body}")
        voices += data.get("voices") or []
        token = data.get("nextPageToken") or data.get("next_page_token")
        if not token:
            break
    cache_path.write_text(json.dumps(voices, indent=2, ensure_ascii=False), encoding="utf-8")
    return voices


def _vname(v: dict) -> str:
    return str(v.get("displayName") or v.get("display_name") or v.get("id", "")).split("/")[-1]


def _vgender(v: dict) -> str:
    return str(v.get("gender") or "").lower().replace("gender_", "")


def _find_voice(name: str, voices: list[dict]) -> dict | None:
    n = name.strip().lower()
    for v in voices:
        cands = {_vname(v).lower(), str(v.get("id", "")).lower(), str(v.get("id", "")).split("/")[-1].lower()}
        if n in cands:
            return v
    return None


def _expected_gender(ep: Episode, name: str, cfg: dict) -> str | None:
    """`gemini_voices.<x>.gender` if given, else the gender of the character's edge-tts voice."""
    if cfg.get("gender"):
        return str(cfg["gender"]).lower()
    try:
        import asyncio
        import edge_tts
        edge = {v["ShortName"]: v["Gender"].lower() for v in asyncio.run(edge_tts.list_voices())}
        return edge.get(ep.speaker(name).voice)
    except Exception:
        return None


def verify_voices(ep: Episode, speakers: list[str], key: str) -> None:
    step("Cek voice Gemini")
    voices = fetch_voices(key, ep.cache / "gemini_voices.json")
    info(f"{len(voices)} voice di katalog (disimpan di cache/gemini_voices.json)")
    missing, mismatched = [], []
    for name in speakers:
        cfg = speaker_cfg(ep, name)
        want = str(cfg["voice"])
        v = _find_voice(want, voices)
        if v is None:
            missing.append((name, want, _expected_gender(ep, name, cfg)))
            continue
        exp, got = _expected_gender(ep, name, cfg), _vgender(v)
        desc = v.get("description") or ""
        if exp and got and exp != got:
            mismatched.append(f"{name}: {want} = {got}, karakter = {exp}")
        info(f"{name:<11} → {_vname(v)} ({got or '?'}{', ' + desc if desc else ''})")
    for m in mismatched:
        warn(f"Gender tidak cocok: {m}")
    if missing:
        lines = []
        names = [_vname(v) for v in voices]
        for name, want, exp in missing:
            close = difflib.get_close_matches(want, names, n=3, cutoff=0.5)
            same = [v for v in voices if not exp or _vgender(v) == exp]
            opts = [f"{_vname(v)} ({_vgender(v) or '?'}, {v.get('description') or '-'})"
                    for v in sorted(same, key=lambda v: _vname(v) not in close)][:8]
            lines.append(f"  {name}: voice '{want}' TIDAK ADA."
                         + (f" Mirip namanya: {', '.join(close)}." if close else "")
                         + f"\n    Pilihan ({exp or 'semua gender'}): " + "; ".join(opts))
        raise PipelineError("Voice tidak ditemukan, tidak ada audio yang dibuat:\n" + "\n".join(lines)
                            + "\n  Ganti di story.yaml (gemini_voices.<speaker>.voice) lalu jalankan lagi.")


# ------------------------------------------------------------------ synthesis
def _err_code(e) -> int | None:
    for a in ("code", "status_code"):
        c = getattr(e, a, None)
        if isinstance(c, int):
            return c
    m = re.search(r"\b(429|500|502|503|504)\b", str(e))
    return int(m.group(1)) if m else None


def _retry_delay(e) -> float | None:
    m = re.search(r"retry(?:Delay)?\D{0,12}?(\d+(?:\.\d+)?)\s*s", str(e), re.I)
    return float(m.group(1)) if m else None


def _audio_bytes(resp) -> bytes:
    """Pull the audio payload out of an Interaction, whichever shape it comes in."""
    def from_obj(o):
        if o is None:
            return None
        d = getattr(o, "data", None) if not isinstance(o, dict) else o.get("data")
        if isinstance(d, (bytes, bytearray)):
            return bytes(d)
        if isinstance(d, str) and d:
            return base64.b64decode(d)
        return None

    b = from_obj(getattr(resp, "output_audio", None))
    if b:
        return b
    for o in getattr(resp, "outputs", None) or []:
        t = getattr(o, "type", None) if not isinstance(o, dict) else o.get("type")
        if t == "audio" and (b := from_obj(o)):
            return b
    raise PipelineError(f"Respon Gemini tanpa audio: {str(resp)[:400]}")


def _to_wav(data: bytes, path) -> None:
    tmp = atomic_out(path)
    if data[:4] == b"RIFF":
        tmp.write_bytes(data)
    else:  # headerless PCM (audio/l16)
        with wave.open(str(tmp), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(PCM_RATE)
            w.writeframes(data)
    with wave.open(str(tmp), "rb") as w:
        if w.getnframes() == 0:
            raise PipelineError("Gemini mengembalikan audio kosong")
    os.replace(tmp, path)


def synth(client, params: dict, path, max_attempts: int = 8) -> None:
    # the API has no language field (it auto-detects from the text), so the language goes into the
    # delivery instruction; the beat text itself is sent verbatim
    sc = {"voice": params["voice"]}
    style = " ".join(s for s in (f"Bahasa Indonesia ({params['language']})." if params.get("language") else "",
                                 params.get("style", "")) if s)
    item = {"type": "text", "text": params["text"]}
    if style:
        item["annotations"] = [{"type": "speech_metadata", "style": style}]
    for attempt in range(max_attempts):
        try:
            # the SDK default has no timeout: a dropped connection would hang forever
            resp = client.interactions.create(model=params["model"], input=[item],
                                              response_format={"type": "audio"},
                                              generation_config={"speech_config": [sc]},
                                              timeout=REQUEST_TIMEOUT)
            _to_wav(_audio_bytes(resp), path)
            return
        except PipelineError:
            raise
        except Exception as e:
            code, msg = _err_code(e), str(e)
            if code is None and ("timeout" in type(e).__name__.lower() or "timed out" in msg.lower()):
                code = 504  # retry timeouts like a gateway timeout
            if code == 429 and re.search(r"per ?day|PerDay|daily", msg, re.I):
                raise DailyQuota(msg[:300])
            if code in (429, 500, 502, 503, 504) and attempt < max_attempts - 1:
                wait = _retry_delay(e) or min(120.0, 8.0 * 2 ** attempt)
                warn(f"HTTP {code}, coba lagi dalam {wait:.0f}s ({attempt + 1}/{max_attempts})")
                time.sleep(wait + 1)
                continue
            raise PipelineError(f"Gemini TTS gagal ({code}): {msg[:600]}")


def run(ep: Episode, jobs: list[dict], args, apply_effect, fx_version: int) -> None:
    if getattr(args, "plan", False):  # request plan only: no key, no network
        return _run(ep, jobs, args, apply_effect, fx_version, None)
    ring = KeyRing(api_keys())
    src = ".env" if (_split(read_env_file().get("GEMINI_API_KEYS")) or
                     _split(read_env_file().get("GEMINI_API_KEY"))) else "environment"
    info(f"API key: {len(ring.keys)} dari {src} (mulai {ring.label})")
    try:
        _run(ep, jobs, args, apply_effect, fx_version, ring)
    except PipelineError as e:  # API errors can echo request details; keys never reach the log
        raise PipelineError(ring.scrub(str(e))) from None


def _client(key: str):
    from google import genai
    from google.genai import types
    # SDK retries off: it would silently sleep through a 429's Retry-After (hours for the daily
    # quota). synth() handles retries itself, visibly, and DailyQuota rotates to the next key.
    return genai.Client(api_key=key, http_options=types.HttpOptions(
        api_version="v1beta", retry_options=types.HttpRetryOptions(attempts=1)))


# ------------------------------------------------------------------ styles
def style_for(ep: Episode, speaker: str, key: str) -> str:
    """Speaker style + pace rule + styles.yaml line. The pace phrase ("tempo sedang, mengalir, tidak
    diseret", story.yaml `gemini_pace`) is left out only for the few lines styles.yaml marks as slow."""
    from .common import DEFAULT_PACE, is_slow_style
    cfg = speaker_cfg(ep, speaker)
    beat = ep.beat_styles.get(key, "")
    pace = str(ep.story.get("gemini_pace", DEFAULT_PACE) or "")
    parts = [str(cfg.get("style") or ""), "" if is_slow_style(beat) else pace, beat]
    return " ".join(x.strip() for x in parts if x and x.strip())


# ------------------------------------------------------------------ merged requests
MERGE_MAX_CHARS = 900     # one request holds at most this much text ...
MERGE_MAX_BEATS = 6       # ... and at most this many beats
MERGE_HINT = "Beri jeda singkat yang jelas di antara paragraf."
SPLIT_SIL_DB, SPLIT_SIL_MIN = -38, 0.16


def plan_requests(ep: Episode, todo: list[dict]) -> list[list[dict]]:
    """Consecutive beats (script order) of the same speaker, style and part → one request."""
    order = {b.key: i for i, b in enumerate([b for b in ep.beats if b.text])}
    groups: list[list[dict]] = []
    for j in todo:
        g = groups[-1] if groups else None
        b = ep.by_key.get(j["key"])
        if (g and b is not None and j["key"] != "recap" and g[-1]["key"] != "recap"
                and order.get(j["key"]) == order.get(g[-1]["key"], -9) + 1
                and ep.by_key[g[-1]["key"]].chapter == b.chapter
                and g[-1]["speaker"] == j["speaker"] and g[-1]["params"]["style"] == j["params"]["style"]
                and len(g) < MERGE_MAX_BEATS
                and sum(len(x["text"]) for x in g) + len(j["text"]) <= MERGE_MAX_CHARS):
            g.append(j)
        else:
            groups.append([j])
    return groups


def _silences(path) -> tuple[list[tuple[float, float]], float]:
    import subprocess
    p = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af",
                        f"silencedetect=noise={SPLIT_SIL_DB}dB:d={SPLIT_SIL_MIN}", "-f", "null", "-"],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
    with wave.open(str(path), "rb") as w:
        total = w.getnframes() / w.getframerate()
    st = [float(x) for x in re.findall(r"silence_start:\s*(-?[\d.]+)", p.stderr)]
    en = [float(x) for x in re.findall(r"silence_end:\s*([\d.]+)", p.stderr)]
    sil = [(max(0.0, a), en[i] if i < len(en) else total) for i, a in enumerate(st)]
    return sil, total


def split_points(path, texts: list[str]) -> tuple[list[tuple[float, float]] | None, str]:
    """[(start, end)] per text, cut in the pauses between them, or (None, reason).

    The k-th cut goes in the pause nearest to where the text lengths say it should be (dynamic
    programming over the detected pauses); then every piece's duration is checked against its share of
    the text. A piece far off its expected length means a wrong cut → caller falls back to per-beat."""
    sil, total = _silences(path)
    head = sil[0][1] if sil and sil[0][0] <= 0.05 else 0.0
    tail = sil[-1][0] if sil and sil[-1][1] >= total - 0.05 else total
    inner = [x for x in sil if x[0] > head + 0.05 and x[1] < tail - 0.05]
    n = len(texts)
    if len(inner) < n - 1:
        return None, f"{len(inner)} jeda, perlu {n - 1}"
    lens = [max(1, len(" ".join(t.split()))) for t in texts]
    speech = tail - head
    cum, expect = 0, []
    for L in lens[:-1]:
        cum += L
        expect.append(head + speech * cum / sum(lens))
    mids = [(a + b) / 2 for a, b in inner]
    INF = float("inf")
    # best[k][i]: cost of placing cut k at pause i
    best = [[INF] * len(inner) for _ in range(n - 1)]
    back = [[-1] * len(inner) for _ in range(n - 1)]
    for i in range(len(inner)):
        best[0][i] = abs(mids[i] - expect[0])
    for k in range(1, n - 1):
        for i in range(k, len(inner)):
            prev = min(range(k - 1, i), key=lambda q: best[k - 1][q])
            best[k][i] = best[k - 1][prev] + abs(mids[i] - expect[k])
            back[k][i] = prev
    i = min(range(len(inner)), key=lambda q: best[n - 2][q])
    picks = [i]
    for k in range(n - 2, 0, -1):
        i = back[k][i]
        picks.append(i)
    picks.reverse()
    pieces, a = [], head
    for k, pi in enumerate(picks + [None]):
        if pi is None:
            b = tail
        else:
            b = inner[pi][0]
        pieces.append((max(0.0, a - 0.06), min(total, b + 0.18)))
        if pi is not None:
            a = inner[pi][1]
    # verify: each piece's speech length vs its share of the text
    for k, ((a, b), L) in enumerate(zip(pieces, lens)):
        exp = speech * L / sum(lens)
        got = b - a
        lo, hi = (0.4, 2.2) if exp < 1.5 else (0.6, 1.6)
        if not (lo <= got / exp <= hi):
            return None, f"potongan {k + 1}: {got:.1f}s, harusnya ±{exp:.1f}s"
    return pieces, "ok"


def _cut(src, dst, a: float, b: float) -> None:
    with wave.open(str(src), "rb") as w:
        rate, ch, sw = w.getframerate(), w.getnchannels(), w.getsampwidth()
        w.setpos(int(a * rate))
        data = w.readframes(int((b - a) * rate))
    tmp = atomic_out(dst)
    with wave.open(str(tmp), "wb") as o:
        o.setnchannels(ch)
        o.setsampwidth(sw)
        o.setframerate(rate)
        o.writeframes(data)
    os.replace(tmp, dst)


def _run(ep: Episode, jobs: list[dict], args, apply_effect, fx_version: int, ring: KeyRing | None) -> None:
    """jobs: [{key, text, speaker, effect}]"""
    model = str(ep.story.get("gemini_model") or DEFAULT_MODEL)
    lang = ep.story.get("gemini_language", "id-ID")
    out_dir = ep.audio_dir
    raw_dir = out_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    plan_only = bool(getattr(args, "plan", False))

    manifest_path = out_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    todo = []
    for j in jobs:
        cfg = speaker_cfg(ep, j["speaker"])
        p = {"engine": "gemini", "model": model, "voice": str(cfg["voice"]), "language": lang,
             "style": style_for(ep, j["speaker"], j["key"]), "text": j["text"], "v": GEMINI_VERSION}
        j["params"], j["raw_hash"] = p, sha(p)
        j["hash"] = sha({**p, "effect": j["effect"], "fx": fx_version})
        wav = ep.audio_path(j["key"])
        if ep.tts_locked and wav.exists() and not args.force:
            continue  # tts.locked: existing (e.g. re-paced) clips are final
        if not args.force and wav.exists() and manifest.get(j["key"]) == j["hash"]:
            continue
        todo.append(j)
    # raw clip still valid (e.g. only the effect changed) → no API call needed
    def raw_ok(j):
        raw, meta = raw_dir / f"{j['key']}.wav", raw_dir / f"{j['key']}.json"
        return (not args.force and raw.exists() and meta.exists()
                and json.loads(meta.read_text(encoding="utf-8")).get("hash") == j["raw_hash"])
    need = [j for j in todo if not raw_ok(j)]
    groups = plan_requests(ep, need)
    step(f"Gemini TTS · {model} · {lang}")
    info(f"{len(jobs) - len(todo)} sudah ada, {len(todo)} akan dibuat · request: {len(groups)} "
         f"(tanpa penggabungan: {len(need)})" + ("  [tts.locked]" if ep.tts_locked else ""))
    if plan_only:
        for g in groups:
            if len(g) > 1:
                info(f"  1 request: {', '.join(x['key'] for x in g)}  ({g[0]['speaker']}, "
                     f"{sum(len(x['text']) for x in g)} huruf)")
        ok(f"Rencana: {len(groups)} request Gemini untuk {len(need)} klip (hemat {len(need) - len(groups)})")
        return

    verify_voices(ep, sorted({j["speaker"] for j in jobs}), ring.key)
    client = _client(ring.key)
    calls = 0

    def call(params, path) -> None:
        nonlocal client, calls
        while True:
            try:
                calls += 1
                synth(client, params, path)
                return
            except DailyQuota as e:
                spent = ring.label
                if not ring.next():
                    done = sum(1 for j in todo if j.get("done"))
                    raise PipelineError(
                        f"Kuota harian habis di semua {len(ring.keys)} key. Selesai {len(jobs) - len(todo) + done}/"
                        f"{len(jobs)}, sisa {len(todo) - done} beat ({calls - 1} request dipakai). Jalankan lagi "
                        f"setelah kuota reset; klip yang sudah jadi tidak dibuat ulang.\n  {e}")
                warn(f"Kuota harian {spent} habis → pindah ke {ring.label}")
                client = _client(ring.key)

    def save_meta(j, extra=None):
        (raw_dir / f"{j['key']}.json").write_text(
            json.dumps({"hash": j["raw_hash"], **j["params"], **(extra or {})}, indent=2, ensure_ascii=False),
            encoding="utf-8")

    fallbacks = 0
    for gi, g in enumerate(groups, 1):
        if len(g) == 1:
            call(g[0]["params"], raw_dir / f"{g[0]['key']}.wav")
            save_meta(g[0])
            continue
        merged = raw_dir / f"_merged_{sha([x['key'] for x in g])}.wav"
        mp = {**g[0]["params"], "text": "\n\n".join(x["text"] for x in g),
              "style": f"{g[0]['params']['style']} {MERGE_HINT}"}
        call(mp, merged)
        pieces, why = split_points(merged, [x["text"] for x in g])
        if pieces:
            for x, (a, b) in zip(g, pieces):
                _cut(merged, raw_dir / f"{x['key']}.wav", a, b)
                save_meta(x, {"merged_with": [y["key"] for y in g], "cut": [round(a, 3), round(b, 3)]})
            info(f"  [{gi}/{len(groups)}] {g[0]['key']}–{g[-1]['key']}: 1 request → {len(g)} klip")
        else:
            fallbacks += 1
            warn(f"  {g[0]['key']}–{g[-1]['key']}: potongan meragukan ({why}) → request per beat")
            for x in g:
                call(x["params"], raw_dir / f"{x['key']}.wav")
                save_meta(x)
        merged.unlink(missing_ok=True)

    for i, j in enumerate(todo, 1):
        raw = raw_dir / f"{j['key']}.wav"
        apply_effect(raw, ep.audio_path(j["key"]), j["effect"])
        manifest[j["key"]] = j["hash"]
        j["done"] = True
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print(f"  [{i}/{len(todo)}] {j['key']}  ({j['params']['voice']}"
              f"{'' if j['effect'] == 'none' else ', ' + j['effect']})", flush=True)
    ok(f"Klip Gemini di {out_dir.relative_to(ROOT)} · request dipakai: {calls} "
       f"(tanpa penggabungan: {len(need)}; {fallbacks} blok jatuh ke per-beat)")
