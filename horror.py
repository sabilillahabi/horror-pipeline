#!/usr/bin/env python3
"""Pipeline video cerita horor bersambung.

Contoh:
  python horror.py prompts tester ep01
  python horror.py check tester ep01
  python horror.py tts tester ep01
  python horror.py build tester ep01
  python horror.py shorts tester ep01 --beats 3-6
  python horror.py thumbnail tester ep01 --beat 5 --text "JANGAN DIBUKA"
"""
from __future__ import annotations

import argparse
import sys

if hasattr(sys.stdout, "reconfigure"):  # Windows consoles: keep ✔/⚠ printable
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from pipeline.common import Episode, PipelineError, ok, step  # noqa: E402


def cmd_placeholders(ep: Episode, args) -> None:
    from pipeline import visuals as V

    step(f"Placeholder {ep.slug} {ep.ep}")
    n = 0
    for b in ep.missing_images():
        V.placeholder(ep.images / f"{b.key}.png", b.key, b.scene, b.chars)
        n += 1
    for name, c in ep.characters.items():
        if name == "narrator":
            continue
        p = ep.reference_image(c.name)
        if not p.exists():
            V.reference_placeholder(p, c.name, c.block)
            n += 1
    ok(f"{n} placeholder dibuat (gambar yang sudah ada tidak disentuh).")


def cmd_all(ep: Episode, args) -> None:
    from pipeline.prompts import cmd_check
    from pipeline.render import cmd_build
    from pipeline.tts import cmd_tts

    if cmd_check(ep, args):
        raise PipelineError("Lengkapi gambar dulu.")
    cmd_tts(ep, args)
    cmd_build(ep, args)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="horror.py", description="Pipeline video cerita horor (edge-tts + ffmpeg)")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add(name, help_):
        sp = sub.add_parser(name, help=help_)
        sp.add_argument("story", help="slug cerita (nama folder di stories/)")
        sp.add_argument("ep", help="episode, mis. ep01 atau 1")
        sp.add_argument("--engine", choices=["edge", "gemini"],
                        help="mesin TTS (default: tts_engine di story.yaml, atau edge)")
        return sp

    sp = add("prompts", "tulis output/flow_prompts.md untuk Google Flow")
    sp.add_argument("--missing-only", action="store_true", help="hanya beat yang gambarnya belum ada")

    add("check", "daftar gambar yang belum ada")
    sp = add("import-flow", "salin gambar Flow bernama '[b018a] ...' ke images/<id>.png")
    sp.add_argument("source", nargs="?", help="zip/folder hasil download Flow "
                    "(default: download Flow terbaru di ~/Downloads: zip, folder, atau file [bXXX] lepas)")
    sp.add_argument("--force", action="store_true",
                    help="timpa gambar lokal walau sumbernya lebih lama (yang lama tetap dibackup)")
    add("placeholders", "buat gambar placeholder untuk tes (hanya yang belum ada)")

    def tts_args(sp):
        sp.add_argument("--force", action="store_true", help="buat ulang semua audio")
        sp.add_argument("--workers", type=int, default=3, help="jumlah request edge-tts paralel")
        sp.add_argument("--proxy", help="proxy HTTP untuk edge-tts (opsional)")
        sp.add_argument("--dummy", action="store_true",
                        help="audio dummy offline (nada) untuk tes tanpa internet")

    def build_args(sp):
        sp.add_argument("--bgm", help="nama file musik di assets/bgm (default: file pertama)")
        sp.add_argument("--no-bgm", action="store_true", help="tanpa musik latar")
        sp.add_argument("--clean", action="store_true", help="hapus cache grup setelah selesai")
        sp.add_argument("--no-sound", action="store_true",
                        help="tanpa lapisan suara sound.yaml (musik/ambience/sfx)")
        sp.add_argument("--no-review", action="store_true", help="lewati review otomatis setelah render")

    sp = add("tts", "buat audio per beat + SRT")
    tts_args(sp)
    sp.add_argument("--beats", help="hanya beat ini, mis. b008,b011 (untuk tes; SRT tidak dibuat)")
    sp = add("build", "render video episode 1920x1080")
    sp.add_argument("--force", action="store_true", help="render ulang semua klip")
    sp.add_argument("--beats", help="preview sebagian, mis. b001-b027 → output/preview_b001-b027.mp4")
    sp.add_argument("--vertical", action="store_true",
                    help="versi 9:16 1080x1920 + part 2-3 menit + captions.txt di output/vertical/")
    build_args(sp)

    add("review", "cek teknis render terakhir → output/review_report.md + contact sheet")
    sp = add("threads", "thread Threads per bab → output/threads/bab<N>.md + gambar")
    sp.add_argument("--thumb-only", action="store_true",
                    help="hanya thumbnail di post 1, tanpa gambar adegan 4:5")

    add("covers", "cover per part IG/FB dari covers.yaml, langsung dipasang ke video part")

    sp = add("channel-tts", "buat klip intro/outro channel (Gemini, sekali untuk semua episode)")
    sp.add_argument("--force", action="store_true", help="buat ulang intro.wav/outro.wav")

    sp = add("sound-import", "salin aset suara dari sound_assets.yaml ke assets/sound/")
    sp.add_argument("source", nargs="?", help="folder sumber (default: ~/Downloads)")
    sp.add_argument("--force", action="store_true", help="proses ulang aset yang sudah ada")

    sp = add("all", "check → tts → build sekaligus")
    tts_args(sp)
    build_args(sp)

    sp = add("shorts", "potongan vertikal 1080x1920 (<60 detik)")
    sp.add_argument("--beats", required=True, help="rentang beat, mis. 12-18 (atau 3,5,6)")
    sp.add_argument("--title", help="teks judul di atas (opsional)")
    sp.add_argument("--hold", type=float, default=1.2, help="detik jeda di beat cliffhanger terakhir")
    sp.add_argument("--fg-scale", type=float, default=1.15, help="ukuran gambar utama (1.0 = selebar layar)")
    sp.add_argument("--sub-size", type=int, default=68, help="ukuran font subtitle")
    sp.add_argument("--auto-trim", action="store_true", help="buang beat dari awal jika > 60 detik")
    sp.add_argument("--force", action="store_true")
    build_args(sp)

    sp = add("thumbnail", "thumbnail 1280x720")
    sp.add_argument("--beat", help="id beat sumber gambar (default: thumbnail.beat di script.yaml)")
    sp.add_argument("--text", help="teks maks 4 kata (default: thumbnail.text di script.yaml)")
    sp.add_argument("--generate", action="store_true",
                    help="buat dari beat walau thumbnail Flow (thumbnail/thumbnail_16x9.jpg) sudah ada")
    sp.add_argument("--position", default="left", choices=["left", "right", "center", "top", "bottom"])
    sp.add_argument("--color", default="#FFFFFF", help="warna teks utama")
    sp.add_argument("--accent", default="#FF2B2B", help="warna baris terakhir")
    sp.add_argument("--crop", choices=["wide", "closeup_face", "detail"], help="crop gambar")
    sp.add_argument("--out", help="nama file output (default thumbnail_epXX.png)")

    args = p.parse_args(argv)
    try:
        ep = Episode(args.story, args.ep)
        if getattr(args, "engine", None):
            ep.tts_engine = args.engine
        if args.cmd == "prompts":
            from pipeline.prompts import cmd_prompts
            cmd_prompts(ep, args)
        elif args.cmd == "check":
            from pipeline.prompts import cmd_check
            return cmd_check(ep, args)
        elif args.cmd == "import-flow":
            from pipeline.importer import cmd_import
            return cmd_import(ep, args)
        elif args.cmd == "placeholders":
            cmd_placeholders(ep, args)
        elif args.cmd == "tts":
            from pipeline.tts import cmd_tts
            cmd_tts(ep, args)
        elif args.cmd == "build":
            from pipeline.render import cmd_build
            cmd_build(ep, args)
        elif args.cmd == "all":
            cmd_all(ep, args)
        elif args.cmd == "threads":
            from pipeline.threads import cmd_threads
            cmd_threads(ep, args)
        elif args.cmd == "review":
            from pipeline.review import cmd_review
            cmd_review(ep, args)
        elif args.cmd == "covers":
            from pipeline.covers import cmd_covers
            cmd_covers(ep, args)
        elif args.cmd == "channel-tts":
            from pipeline.channel import cmd_channel_tts
            cmd_channel_tts(ep, args)
        elif args.cmd == "sound-import":
            from pipeline.sound import cmd_sound_import
            return cmd_sound_import(ep, args)
        elif args.cmd == "shorts":
            from pipeline.shorts import cmd_shorts
            cmd_shorts(ep, args)
        elif args.cmd == "thumbnail":
            from pipeline.thumbnail import cmd_thumbnail
            cmd_thumbnail(ep, args)
    except PipelineError as e:
        print(f"\n✗ {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nDibatalkan. Jalankan lagi untuk melanjutkan (file yang sudah jadi dilewati).")
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
