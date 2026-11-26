#!/usr/bin/env python3
"""Push episode assets to the `muse-assets` branch via the GitHub REST API.

    python3 scripts/push_assets_api.py --story juru-kunci --ep ep02 --dry-run
    python3 scripts/push_assets_api.py --story juru-kunci --ep ep02

Why the API and not `git push`: the vault token is only usable as a Bearer
token (the runtime swaps the hsurr: surrogate for the real token on approved
egress to api.github.com); git's HTTPS transport needs Basic auth, where the
surrogate is NOT swapped, so `git push` from this VM cannot authenticate
(verified 2026-11-26: dry-run push -> 401 "Invalid username or token";
GET /user with Bearer -> 200, login sabilillahabi).

Same file set and rules as scripts/push_assets.py (same collect(), same
95 MB cap, same NEVER dirs, same Windows system-font skip). Differences:
blobs/trees/commits go through the Git Data API instead of local git objects.

Flow:
  1. GET refs/heads/muse-assets -> tip SHA (expected parent).
  2. GET the tip's recursive tree (path -> blob SHA).
  3. Collect local files; compute each file's git blob SHA.
     - >95 MB -> skipped (listed).
     - same path + same SHA in the remote tree -> already there, no blob.
     - SHA exists elsewhere in the remote tree -> no blob POST needed.
     - else -> POST /git/blobs (base64). Idempotent: safe to resume.
  4. POST /git/trees with base_tree=tip tree + changed entries.
     If the resulting tree == tip tree -> nothing to do.
  5. POST /git/commits (one commit, parent=tip).
  6. Re-read the ref; if it moved -> STOP, report, do not update.
     Else PATCH the ref with force=false.
  7. Verify: GET the new tip's recursive tree; count ep01 files
     before/after and ep02 files; report.

Rate limits: on 403/429/502/503, retry with backoff (Retry-After /
X-RateLimit-Reset respected), up to 5 attempts per request.

The token is read from the vault at runtime (dynamic_credentials) and only
ever travels inside the Authorization header of requests to api.github.com.
It is never printed and never written to disk. This file holds no secret,
only the credential NAME.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, "/opt/muse/skills/custom-connector-setup/bin")

from dynamic_credentials import add_surrogate_to_request  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OWNER = "sabilillahabi"
REPO = "horror-pipeline"
BRANCH = "muse-assets"
API = "https://api.github.com"
CREDENTIAL = "custom.github-horror-pipeline"
MAX_BYTES = 95 * 1024 * 1024
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


def is_system_font(p: Path) -> bool:
    n = p.name.lower()
    return any(n.startswith(s) for s in SYSTEM_FONTS)


def collect(stories: list[tuple[str, str]]) -> tuple[list[Path], list[tuple[Path, str]]]:
    """Same file set as scripts/push_assets.py."""
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
            if p.is_symlink():
                skipped.append((rel, "symlink (tidak didukung rute API)"))
                continue
            if r.name == "fonts" and p.suffix.lower() in (".ttf", ".otf", ".ttc") and is_system_font(p):
                skipped.append((rel, "font sistem Windows (tidak boleh dibagikan)"))
                continue
            if p.stat().st_size > MAX_BYTES:
                skipped.append((rel, f"{p.stat().st_size / 1e6:.0f} MB > 95 MB"))
                continue
            files.append(p)
    return files, skipped


def blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def _sleep_for_rate_limit(resp_headers, attempt: int) -> float:
    """Tidur untuk rate limit ASLI saja. Dipanggil hanya untuk 429 / 403
    rate-limit, jadi X-RateLimit-Reset di sini memang relevan. (Untuk
    502/503 pemanggil memakai backoff eksponensial, bukan fungsi ini.)"""
    retry_after = resp_headers.get("Retry-After")
    if retry_after:
        try:
            return max(float(retry_after), 1.0)
        except ValueError:
            pass
    reset = resp_headers.get("X-RateLimit-Reset")
    if reset:
        try:
            wait = float(reset) - time.time() + 5.0
            if wait > 0:
                return wait
        except ValueError:
            pass
    return min(5.0 * (2 ** attempt), 60.0)


def api(method: str, path: str, body: dict | None = None, timeout: int = 60) -> dict:
    """One GitHub REST call with Bearer auth from the vault + retries.

    Never logs headers or bodies (bodies carry base64 file content).
    """
    url = API + path
    payload = json.dumps(body).encode("utf-8") if body is not None else None
    last_err = ""
    for attempt in range(5):
        req = urllib.request.Request(url, data=payload, method=method)
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("Content-Type", "application/json")
        req.add_header("X-GitHub-Api-Version", "2022-11-28")
        add_surrogate_to_request(req, CREDENTIAL, allowed_hosts=["api.github.com"])
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", "replace")
            try:
                msg = json.loads(raw).get("message", raw)
            except json.JSONDecodeError:
                msg = raw
            last_err = f"HTTP {e.code}: {str(msg)[:300]}"
            # 403 ada dua macam: rate limit (boleh retry setelah tidur) dan
            # izin kurang ("Resource not accessible by personal access token")
            # yang TIDAK akan sembuh dengan retry -> gagal cepat.
            msg_lower = str(msg).lower()
            rate_limited = ("rate limit" in msg_lower or "abuse" in msg_lower
                            or e.headers.get("X-RateLimit-Remaining") == "0")
            if e.code in (429, 502, 503) or (e.code == 403 and rate_limited):
                if e.code in (429,) or (e.code == 403 and rate_limited):
                    wait = _sleep_for_rate_limit(e.headers, attempt)
                else:  # 502/503: backoff eksponensial, bukan Reset header
                    wait = min(5.0 * (2 ** attempt), 60.0)
                print(f"  rate limit/transient ({last_err}), tunggu {wait:.0f} dtk ...", flush=True)
                time.sleep(wait)
                continue
            raise SystemExit(f"GitHub API {method} {path} gagal: {last_err}")
        except (urllib.error.URLError, TimeoutError) as e:
            last_err = f"{type(e).__name__}: {str(e)[:200]}"
            wait = min(5.0 * (2 ** attempt), 60.0)
            print(f"  jaringan ({last_err}), tunggu {wait:.0f} dtk ...", flush=True)
            time.sleep(wait)
    raise SystemExit(f"GitHub API {method} {path} gagal setelah retry: {last_err}")


def get_ref() -> dict:
    return api("GET", f"/repos/{OWNER}/{REPO}/git/ref/heads/{BRANCH}")


def get_recursive_tree(tree_sha: str) -> dict[str, str]:
    data = api("GET", f"/repos/{OWNER}/{REPO}/git/trees/{tree_sha}?recursive=1")
    if data.get("truncated"):
        raise SystemExit("daftar tree terpotong (truncated) — berhenti, tidak aman membandingkan.")
    return {e["path"]: e["sha"] for e in data.get("tree", []) if e.get("type") == "blob"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--story", action="append", help="slug (default juru-kunci)")
    ap.add_argument("--ep", action="append", help="episode folder, e.g. ep02 (default ep01)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    stories = list(zip(a.story or ["juru-kunci"], a.ep or ["ep01"]))

    files, skipped = collect(stories)
    total = sum(p.stat().st_size for p in files)
    for rel, why in skipped:
        print(f"  dilewati: {rel}  ({why})")

    ref = get_ref()
    tip = ref["object"]["sha"]
    tip_commit = api("GET", f"/repos/{OWNER}/{REPO}/git/commits/{tip}")
    tip_tree = tip_commit["tree"]["sha"]
    remote = get_recursive_tree(tip_tree)
    remote_shas = set(remote.values())
    print(f"tip {BRANCH}: {tip[:8]} ({tip_commit['message'].splitlines()[0]})")
    print(f"tree lama: {len(remote)} file")

    # Rencana: file mana yang butuh blob baru.
    plan: list[tuple[Path, str, bytes]] = []  # (path, rel posix, data)
    already = 0
    for p in files:
        rel = p.relative_to(ROOT).as_posix()
        data = p.read_bytes()
        sha = blob_sha(data)
        if remote.get(rel) == sha:
            already += 1
            continue
        plan.append((p, rel, data))
    # Blob yang SHAn-ya sudah ada di tree (di path lain) tidak perlu di-POST.
    to_post = [(p, rel, data) for (p, rel, data) in plan if blob_sha(data) not in remote_shas]
    upload_bytes = sum(len(data) for (_, _, data) in to_post)
    top = sorted({rel.split("/")[0] for (_, rel, _) in plan})
    print(f"terkumpul: {len(files)} file, {total / 1e6:.1f} MB")
    print(f"sudah ada di branch (path+SHA sama): {already} file")
    print(f"perlu blob baru: {len(to_post)} file, {upload_bytes / 1e6:.1f} MB")
    print(f"folder tingkat atas: {', '.join(top)}")
    if a.dry_run:
        return 0
    if not plan:
        print(f"{BRANCH} sudah sama, tidak ada yang di-push.")
        return 0

    # 1. Blobs (idempotent: aman diulang kalau terputus). Paralel 4 worker:
    #    satu POST ~7 dtk (didominasi upload body), sekuensial butuh ~50 mnt
    #    untuk 419 blob; 4 worker ~12 mnt. Tiap request ambil surrogate baru
    #    (pola resmi) dan aman di thread (socket baru per panggilan).
    def _post_blob(item: tuple[Path, str, bytes]) -> tuple[str, str]:
        p, rel, data = item
        sha = blob_sha(data)
        res = api("POST", f"/repos/{OWNER}/{REPO}/git/blobs",
                  {"content": base64.b64encode(data).decode("ascii"), "encoding": "base64"},
                  timeout=300)
        if res["sha"] != sha:
            raise SystemExit(f"blob SHA tidak cocok untuk {rel}: API {res['sha'][:8]} vs lokal {sha[:8]}")
        return rel, sha

    new_shas: dict[str, str] = {}
    done = 0
    done_lock = threading.Lock()
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(_post_blob, item): item for item in to_post}
        for fut in as_completed(futs):
            rel, sha = fut.result()
            new_shas[rel] = sha
            with done_lock:
                done += 1
                n_done = done
            if n_done % 25 == 0 or n_done == len(to_post):
                print(f"  blob {n_done}/{len(to_post)}", flush=True)
    for (p, rel, data) in plan:
        if rel not in new_shas:
            new_shas[rel] = blob_sha(data)  # SHA sudah ada di tree

    # 2. Tree di atas tree lama.
    entries = [{"path": rel, "mode": "100644", "type": "blob", "sha": sha}
               for rel, sha in sorted(new_shas.items())]
    tree_res = api("POST", f"/repos/{OWNER}/{REPO}/git/trees",
                   {"base_tree": tip_tree, "tree": entries})
    new_tree = tree_res["sha"]
    if new_tree == tip_tree:
        print(f"{BRANCH} sudah sama, tidak ada yang di-push.")
        return 0

    # 3. Satu commit, parent = tip yang dibaca tadi.
    msg = f"Assets: {', '.join(f'{s}/{e}' for s, e in stories)} + assets/sound + assets/fonts ({len(files)} file)"
    commit_res = api("POST", f"/repos/{OWNER}/{REPO}/git/commits",
                     {"message": msg, "tree": new_tree, "parents": [tip]})
    commit = commit_res["sha"]
    # Tulis SHA lengkap (bukan [:8]): kalau ref update gagal, commit yang
    # sudah dibuat masih bisa ditemukan lewat API (API tidak menerima SHA pendek).
    print(f"commit baru: {commit} (parent {tip}, tree {new_tree})")

    # 4. Ref check + update (tidak pernah force). PERHATIKAN: endpoint update
    #    memakai "refs" (jamak), BUKAN "ref" seperti GET — PATCH ke /git/ref/
    #    mengembalikan 404 (kejadian 2026-11-26: commit sudah dibuat tapi ref
    #    tidak ke-update).
    ref_now = get_ref()
    if ref_now["object"]["sha"] != tip:
        raise SystemExit(
            f"BERHENTI: ref {BRANCH} bergerak ({tip[:8]} -> {ref_now['object']['sha'][:8]}). "
            f"Commit {commit[:8]} dibuat tapi ref TIDAK di-update. Lapor dulu.")
    api("PATCH", f"/repos/{OWNER}/{REPO}/git/refs/heads/{BRANCH}",
        {"sha": commit, "force": False})
    print(f"OK: ref {BRANCH} -> {commit}")

    # 5. Verifikasi: tree baru masih berisi ep01 + berisi ep02.
    new_ref = get_ref()
    new_commit = api("GET", f"/repos/{OWNER}/{REPO}/git/commits/{new_ref['object']['sha']}")
    new_remote = get_recursive_tree(new_commit["tree"]["sha"])
    ep01_prefix = "stories/juru-kunci/episodes/ep01/"
    ep02_prefix = "stories/juru-kunci/episodes/ep02/"
    ep01_before = sum(1 for p in remote if p.startswith(ep01_prefix))
    ep01_after = sum(1 for p in new_remote if p.startswith(ep01_prefix))
    ep02_after = sum(1 for p in new_remote if p.startswith(ep02_prefix))
    print(f"verifikasi: ep01 {ep01_before} -> {ep01_after} file; "
          f"ep02 {ep02_after} file; total {len(remote)} -> {len(new_remote)} file")
    if ep01_before != ep01_after:
        raise SystemExit("VERIFIKASI GAGAL: jumlah file ep01 berubah!")
    if ep02_after == 0:
        raise SystemExit("VERIFIKASI GAGAL: tidak ada file ep02 di tree baru!")
    missing = [rel for rel in new_shas if new_remote.get(rel) != new_shas[rel]]
    if missing:
        raise SystemExit(f"VERIFIKASI GAGAL: {len(missing)} file tidak ada di tree baru, contoh: {missing[0]}")
    print(f"OK: {len(to_post)} blob di-upload ({upload_bytes / 1e6:.1f} MB), "
          f"commit {commit} di {BRANCH}")
    print(f"Pulihkan: git fetch origin {BRANCH} && git checkout origin/{BRANCH} -- stories assets")
    return 0


if __name__ == "__main__":
    sys.exit(main())
