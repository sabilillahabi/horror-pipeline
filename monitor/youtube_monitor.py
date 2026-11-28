#!/usr/bin/env python3
"""Kemenyan Malam — YouTube monitor (daily / weekly) → Telegram.

Runs on GitHub Actions (.github/workflows/monitor.yml). Uses only public data through a YouTube Data API key
(no OAuth): views, likes, comment counts, and new public comments. Gemini writes a short insight and draft
replies in the channel's voice; Bil posts replies himself.

Env: YT_API_KEY, YT_CHANNEL (@handle or UC… id), TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
     GEMINI_API_KEY (optional; without it the report has no insight/drafts), GEMINI_MODEL (optional),
     MODE=daily|weekly, STATE_FILE (default monitor/state/state.json), DRY_RUN=1 (print instead of sending).
Never prints keys.
"""
from __future__ import annotations

import datetime as dt
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

YT = "https://www.googleapis.com/youtube/v3/"
WIB = dt.timezone(dt.timedelta(hours=7))
SHORT_MAX_S = 180
MAX_VIDEOS = 50
MAX_DRAFTS = 10


def env(name: str, default: str | None = None) -> str:
    v = os.environ.get(name, default)
    if v is None or v == "":
        sys.exit(f"Missing env {name}")
    return v


def http_json(url: str, data: dict | None = None, timeout: int = 60) -> dict:
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"} if body else {})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors="replace")[:300]
            if e.code in (429, 500, 502, 503) and attempt < 2:
                time.sleep(5 * (attempt + 1))
                continue
            safe = re.sub(r"(key|token)=[^&\s]+", r"\1=***", url)
            raise RuntimeError(f"HTTP {e.code} for {safe.split('?')[0]}: {msg}") from None
    raise RuntimeError("unreachable")


def yt(path: str, **params) -> dict:
    params["key"] = env("YT_API_KEY")
    return http_json(YT + path + "?" + urllib.parse.urlencode(params))


def iso_dur(s: str) -> int:
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", s or "")
    if not m:
        return 0
    d, h, mi, se = (int(x or 0) for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + se


def channel() -> dict:
    c = env("YT_CHANNEL").strip()
    q = {"id": c} if c.startswith("UC") else {"forHandle": c if c.startswith("@") else "@" + c}
    items = yt("channels", part="snippet,statistics,contentDetails", **q).get("items", [])
    if not items:
        sys.exit(f"Channel not found: {c}")
    return items[0]


def recent_videos(uploads: str) -> list[dict]:
    ids = [it["contentDetails"]["videoId"]
           for it in yt("playlistItems", part="contentDetails", playlistId=uploads,
                        maxResults=MAX_VIDEOS).get("items", [])]
    if not ids:
        return []
    out = []
    for v in yt("videos", part="snippet,statistics,contentDetails", id=",".join(ids)).get("items", []):
        st = v.get("statistics", {})
        dur = iso_dur(v["contentDetails"].get("duration", ""))
        out.append({"id": v["id"], "title": v["snippet"]["title"], "published": v["snippet"]["publishedAt"],
                    "dur": dur, "short": dur <= SHORT_MAX_S,
                    "views": int(st.get("viewCount", 0)), "likes": int(st.get("likeCount", 0)),
                    "comments": int(st.get("commentCount", 0))})
    return out


def new_comments(channel_id: str, since: str | None) -> list[dict]:
    try:
        items = yt("commentThreads", part="snippet", allThreadsRelatedToChannelId=channel_id,
                   maxResults=50, order="time", textFormat="plainText").get("items", [])
    except RuntimeError as e:  # comments disabled etc.
        print(f"comments: {e}")
        return []
    out = []
    for it in items:
        top = it["snippet"]["topLevelComment"]["snippet"]
        if since and top["publishedAt"] <= since:
            continue
        if top.get("authorChannelId", {}).get("value") == channel_id:
            continue  # our own comments
        out.append({"video": it["snippet"].get("videoId", ""), "author": top.get("authorDisplayName", ""),
                    "text": top.get("textDisplay", "")[:400], "at": top["publishedAt"],
                    "replies": it["snippet"].get("totalReplyCount", 0)})
    return out


GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={k}"
VOICE = ("Kamu admin channel horor Indonesia 'Kemenyan Malam' (tagline: Dengarkan pelan-pelan. Mereka juga sedang "
         "mendengarkan.). Gaya balasan: hangat, tenang, sedikit misterius, bahasa Indonesia santai, 1–2 kalimat, "
         "maks 1 emoji (🕯️ atau 👀). Tanpa spoiler cerita berikutnya, tanpa janji jadwal, tanpa link. Komentar "
         "kasar/spam/agama/politik: jangan dibalas (tulis SKIP).")


GEMINI_ERR: list[str] = []


def gemini(prompt: str) -> str | None:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        if not GEMINI_ERR:
            GEMINI_ERR.append("secret GEMINI_API_KEY kosong/tidak ada")
        return None
    m = os.environ.get("GEMINI_MODEL") or "gemini-flash-latest"
    try:
        r = http_json(GEMINI_URL.format(m=m, k=key),
                      {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
                       "generationConfig": {"temperature": 0.7, "maxOutputTokens": 1500}}, timeout=90)
        return "".join(p.get("text", "") for p in r["candidates"][0]["content"]["parts"]).strip()
    except Exception as e:  # report still goes out without AI parts
        msg = re.sub(r"AIza[0-9A-Za-z_\-]{10,}", "***", str(e))
        print(f"gemini: {msg}")
        if not GEMINI_ERR:
            GEMINI_ERR.append(f"model {m}: {msg[:300]}")
        return None


def fmt(n: int) -> str:
    return f"{n/1000:.1f}K".replace(".0K", "K") if n >= 1000 else str(n)


def short_title(t: str, n: int = 48) -> str:
    t = t.split("|")[0].strip() if "|" in t else t
    return t if len(t) <= n else t[: n - 1] + "…"


def part_label(t: str) -> str:
    m = re.search(r"Eps\s*(\d+)\s*Part\s*(\d+)", t, re.I)
    return f"E{m.group(1)}P{m.group(2)}" if m else ""


def send_telegram(text: str) -> None:
    if os.environ.get("DRY_RUN"):
        print(text)
        return
    url = f"https://api.telegram.org/bot{env('TELEGRAM_BOT_TOKEN')}/sendMessage"
    chunks, cur = [], ""
    for line in text.split("\n"):
        if len(cur) + len(line) + 1 > 3900:
            chunks.append(cur)
            cur = ""
        cur += line + "\n"
    chunks.append(cur)
    for c in chunks:
        http_json(url, {"chat_id": env("TELEGRAM_CHAT_ID"), "text": c, "parse_mode": "HTML",
                        "disable_web_page_preview": True})


def main() -> None:
    mode = os.environ.get("MODE", "daily")
    state_file = Path(os.environ.get("STATE_FILE", "monitor/state/state.json"))
    state = json.loads(state_file.read_text()) if state_file.exists() else {}
    now = dt.datetime.now(dt.timezone.utc)

    ch = channel()
    cid = ch["id"]
    vids = recent_videos(ch["contentDetails"]["relatedPlaylists"]["uploads"])
    prev = state.get("videos", {})
    week = state.get("week", {})  # snapshot from the last weekly report
    comments = new_comments(cid, state.get("last_comment_at"))

    def delta(v, base):
        b = base.get(v["id"])
        return v["views"] - b["views"] if b else None

    E = html.escape
    st = ch["statistics"]
    subs = int(st.get("subscriberCount", 0))
    prev_subs = state.get("subs")
    lines = [f"<b>🕯️ Kemenyan Malam — laporan {'mingguan' if mode == 'weekly' else 'harian'}</b>",
             f"{now.astimezone(WIB):%a %d %b %Y, %H:%M} WIB",
             f"Subscriber: <b>{fmt(subs)}</b>" + (f" ({subs - prev_subs:+d})" if prev_subs is not None else ""),
             ""]
    base = week if mode == "weekly" else prev
    span = "7 hari" if mode == "weekly" else "24 jam"
    shorts = [v for v in vids if v["short"]]
    longs = [v for v in vids if not v["short"]]
    rows = sorted(shorts, key=lambda v: v["published"], reverse=True)[:12]
    if rows:
        lines.append(f"<b>Shorts terbaru</b> (views · like · komen · +{span})")
        for v in rows:
            d = delta(v, base)
            lr = f"{v['likes'] / v['views'] * 100:.1f}%" if v["views"] else "-"
            lab = part_label(v["title"])
            lines.append(f"• {E(lab + ' ' if lab else '')}{E(short_title(v['title']))}\n"
                         f"   {fmt(v['views'])} · {v['likes']} ({lr}) · {v['comments']}"
                         + (f" · <b>+{fmt(d)}</b>" if d is not None else " · baru"))
    if longs:
        lines += ["", "<b>Video panjang</b>"]
        for v in sorted(longs, key=lambda v: v["published"], reverse=True)[:4]:
            d = delta(v, base)
            lines.append(f"• {E(short_title(v['title']))}: {fmt(v['views'])} views · {v['likes']} like"
                         + (f" · +{fmt(d)}" if d is not None else ""))
    movers = sorted((v for v in vids if delta(v, base)), key=lambda v: -delta(v, base))[:3]
    if movers:
        lines += ["", f"<b>Paling naik {span}</b>: " + ", ".join(
            f"{E(part_label(v['title']) or short_title(v['title'], 24))} +{fmt(delta(v, base))}" for v in movers)]

    titles = {v["id"]: v["title"] for v in vids}
    if comments:
        lines += ["", f"<b>Komentar baru ({len(comments)})</b>"]
        todo = comments[:MAX_DRAFTS]
        drafts = None
        if todo:
            listing = "\n".join(f"{i+1}. [{short_title(titles.get(c['video'], ''), 40)}] {c['author']}: {c['text']}"
                                for i, c in enumerate(todo))
            raw = gemini(VOICE + "\n\nTulis satu balasan per komentar, format persis `N. <balasan>` atau `N. SKIP`."
                         "\n\n" + listing)
            if raw:
                drafts = {int(m.group(1)): m.group(2).strip()
                          for m in re.finditer(r"^\s*(\d+)\.\s*(.+)$", raw, re.M)}
        for i, c in enumerate(comments):
            lab = part_label(titles.get(c["video"], ""))
            lines.append(f"\n💬 <b>{E(c['author'])}</b> {E('(' + lab + ')' if lab else '')}\n{E(c['text'])}")
            if drafts and drafts.get(i + 1) and drafts[i + 1].upper() != "SKIP":
                lines.append(f"↳ <i>draf:</i> <code>{E(drafts[i + 1])}</code>")
            lines.append(f"https://youtu.be/{c['video']}" if c["video"] else "")
    else:
        lines += ["", "Komentar baru: tidak ada"]

    summary = "\n".join(f"{part_label(v['title']) or short_title(v['title'], 30)}: {v['views']} views, "
                        f"{v['likes']} like, {v['comments']} komen, +{delta(v, base) or 0} dalam {span}"
                        for v in sorted(vids, key=lambda v: v["published"], reverse=True)[:14])
    insight = gemini("Kamu analis channel YouTube horor 'Kemenyan Malam' (cerita bersambung, tiap episode 4 part "
                     "Shorts Sen–Kam 19:00 WIB, video panjang Minggu). Dari data ini, tulis maks 3 poin singkat "
                     "bahasa Indonesia santai (gua/lu): pola yang terlihat dan satu saran konkret. Jangan mengarang "
                     "angka di luar data.\n\n" + summary)
    if insight:
        lines += ["", "<b>Catatan</b>", E(insight)]
    elif GEMINI_ERR:
        lines += ["", f"⚠️ <i>Gemini gagal ({E(GEMINI_ERR[0])})</i>"]
    send_telegram("\n".join(lines))

    state["videos"] = {v["id"]: {"views": v["views"], "likes": v["likes"]} for v in vids}
    state["subs"] = subs
    if mode == "weekly" or not week:
        state["week"] = state["videos"]
    if comments:
        state["last_comment_at"] = max(c["at"] for c in comments)
    elif not state.get("last_comment_at"):
        state["last_comment_at"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    state["updated"] = now.isoformat()
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(state, indent=1))
    print(f"ok: {len(vids)} videos, {len(comments)} new comments, mode={mode}")


if __name__ == "__main__":
    main()
