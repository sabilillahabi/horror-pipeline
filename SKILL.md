---
name: "horror_serial"
description: "Produksi cerita horor bersambung di Muse AI: tiap episode = 3-4 part vertikal (<= 2:55, dipakai sama untuk YouTube Shorts/TikTok/IG Reels/FB Reels) + satu video panjang YouTube 16:9. Dari script.yaml (parts) sampai file siap upload: prompt gambar Google Flow (user generate di Flow lalu diimport), narasi Gemini TTS 130-150 wpm (request digabung), lapisan suara, render cepat (encoder hardware/veryfast, shot paralel), outro channel (video panjang saja), cover per part, caption, jadwal 3 episode/minggu, review teknis + visual. Pakai saat user mau membuat / melanjutkan episode cerita horor (mis. Juru Kunci, channel Kemenyan Malam)."
---

# Horror Serial Pipeline (Muse AI)

Pipeline Python (`horror.py`) yang sudah dipakai untuk "Juru Kunci · Eps 1" (channel Kemenyan Malam).
Kamu (agen Muse) menjalankan perintahnya, memeriksa hasilnya, dan berhenti di setiap titik persetujuan.
Semua path di bawah relatif ke folder skill ini (`$SKILL`), mis. `~/workspace/skills/horror-serial/`.

## Tahap 0 — Wajib sebelum apa pun
1. Setup sekali: ikuti `references/00-setup.md` (venv, ffmpeg, font, `.env` berisi `GEMINI_API_KEYS`).
   Pulihkan aset (gambar, audio, thumbnail, suara, font) dari branch `muse-assets`:
   `git fetch origin muse-assets && git checkout origin/muse-assets -- stories assets`.
   Jalankan `python horror.py check <story> <ep>`; semua error setup harus beres dulu.
2. Tanyakan ke user (jangan menebak):
   - cerita (`stories/<slug>/`) dan episode (`ep01`, `ep02`, …); cerita baru atau lanjutan?
   - apakah `script.yaml` episode ini sudah ada/dikunci, atau perlu ditulis dulu (`references/01-story-and-script.md`)
   - gambar dibuat **user di Google Flow** (bukan di Muse): sudah ada yang diunggah, atau perlu prompt dulu?
   - target upload hari ini (YouTube saja, atau + TikTok/IG/FB/Threads) dan tenggat waktunya
3. Output selalu dua orientasi dari gambar 16:9 yang sama: part vertikal 1080x1920 dan video panjang 1920x1080.
   Jangan pernah generate gambar 9:16 terpisah — versi vertikal dipotong dari 16:9 secara otomatis.

## Format (sejak 23 Nov 2026) — patuhi tanpa diminta
- Episode = **3–4 part** di `script.yaml` (`parts:`), tiap part 2:30–2:50, **wajib ≤ 2:55**; 1.100–1.300 kata per
  episode; baris pertama part = hook, baris terakhir = cliffhanger; part 2–4 dibuka "hook jembatan" (01).
- Tempo **130–150 wpm**: style default + "tempo sedang, mengalir, tidak diseret"; maks 3 baris pelan per part;
  `pause_after` ≤ 0,6 s (1,0 s cliffhanger); beat hitam ≤ 1,5 s (03).
- 25–30 gambar Flow baru per episode, sisanya `reuse` + `crop` (02).
- Satu gambar 16:9 harus bagus di landscape dan vertikal: subjek di sepertiga tengah, pinggir = suasana, dua tokoh
  berdekatan (`center-left`/`center-right`). `prompts` menambahkan kalimat komposisinya otomatis (02 bagian 1b).
- Part vertikal: tanpa kartu pembuka/penutup, tanpa outro; 3 detik pertama selalu gambar; label kecil
  "<Judul> · Eps N · Part N/M"; cover per part (05). Outro channel hanya di video panjang.
- Upload: 3 episode/minggu, maks 2 part/hari (12:00 & 19:00 WIB), satu file per slot, video panjang 18:00 sehari
  setelah part terakhir (07).

## Alur kerja (urut, jangan lompat)
| # | Tahap | Perintah utama | Referensi |
|---|-------|----------------|-----------|
| 1 | Story & script dikunci | `prompts`, `check` | 01 |
| 2 | Prompt Flow → user generate di Google Flow → upload → import | `prompts`, `import-flow <zip/folder>`, `check` | 02 |
| 3 | Thumbnail episode (16:9 + 9:16), juga dari Flow | `import-flow <folder>` | 02 |
| 4 | Narasi (cek rencana request dulu) + outro channel | `tts --plan`, `tts`, `channel-tts` | 03 |
| 5 | Lapisan suara | `sound-import <folder>` | 04 |
| 6 | Simpan aset baru ke `muse-assets` | `python scripts/push_assets.py --story <s> --ep <ep>` | 00 |
| 7 | Preview part 1 → **persetujuan user** | `build --beats <part1>` (+ `--vertical`) | 05 |
| 8 | Video panjang, lalu part vertikal (satu per satu) | `build`, `build --vertical` | 05 |
| 9 | Cover part (+ Threads opsional) | otomatis di `build --vertical`; `covers`, `threads` | 05, 07 |
| 10 | Review teknis + **cek visual oleh kamu** (`first_frames.png`!) | otomatis setelah build; `review` | 06 |
| 11 | `publish.md`: judul + deskripsi + hashtag per platform, jadwal | aturan per platform di 07 | 07 |

Sebelum mulai baca `references/08-lessons.md` — semua bug di sana sudah pernah terjadi.

Rilis: **part dulu, video panjang belakangan** — jadwal mingguan di `references/07-publish.md`.
Klip TTS lama yang terlalu lambat: `repace` (atempo, tanpa kuota) — jangan generate ulang (03).
Kalau workspace punya browser yang login ke akun Google Bil dan Bil minta kamu sendiri yang generate gambar di Flow
atau download suara di Pixabay, ikuti `references/09-flow-and-pixabay-browser.md`.

## Output Contract (per episode, di `stories/<slug>/episodes/epXX/`)
- `output/vertical/epXX_partN.mp4` — 3–4 part, masing-masing ≤ 2:55, 120–165 wpm, −14 LUFS / ≤ −1.5 dBTP,
  ±20–40 MB, 3 detik pertama gambar (bukan hitam/kartu), tanpa kartu penutup; sama untuk Shorts/TikTok/IG/FB
- `output/vertical/covers/epXX_partN_cover.jpg` + `covers_sheet.png`; `first_frames.png`; `captions.txt`
- `output/epXX.mp4` (YouTube, 1920x1080, < 300 MB, −14 LUFS ±1, true peak ≤ −1 dBTP, outro channel di akhir)
  + `epXX.srt` + `description.txt` (chapter = awal tiap part)
- `thumbnail/thumbnail_16x9.jpg` (1280x720, < 2 MB) dan `thumbnail_9x16.jpg` (1080x1920)
- (opsional) `output/threads/babN.md` + `images/`; (hanya kalau diminta) `output/vertical/epXX.mp4` via `--full`
- `output/review_report.md` dan `output/vertical/review_report.md` dengan **0 NEEDS FIX** dan bagian
  "Cek visual" terisi (`review_visual_<nama>.md`)

## Aturan operasi
1. **Rahasia:** jangan pernah mencetak isi `.env` atau API key. Pipeline sudah menyamarkan key di log.
2. **Satu render berat pada satu waktu.** Jangan menjalankan dua `build` bersamaan dan jangan menghentikan
   proses ffmpeg/render yang sedang berjalan dengan sinyal (Ctrl+C/kill) — itu yang merusak render kita.
3. **Preview dulu, penuh kemudian:** render bab 1 (`--beats`), minta user OK, baru episode penuh.
4. **Review wajib, dan kamu harus melihat gambarnya.** Setelah tiap render buka semua `review_sheet_*.png`
   (dan `review_crops_*.png` untuk vertikal) dengan tool baca gambar, tulis temuan per timestamp di
   `review_visual_<nama>.md`, jalankan `review` lagi. Bug teknis → perbaiki; masalah kreatif → laporkan saja.
5. **Jangan menimpa gambar user tanpa sengaja.** `import-flow` menolak sumber yang lebih lama dan membackup
   ke `images/_backup/`; `--force` hanya kalau user minta.
6. **Gaya visual yang sudah disetujui tidak diubah:** outro channel, layout subtitle vertikal, gaya cover part
   (judul dipotong dari thumbnail_9x16 + "PART N"). Perubahan gaya hanya atas permintaan user.
7. **Gambar dari Google Flow, bukan Muse.** Jangan memakai media-generation untuk gambar cerita/thumbnail.
   Culture lock (pedesaan Jawa) wajib ada di prompt Flow; gambar Flow dengan kuburan/gerbang gaya Eropa atau
   teks bahasa Inggris → minta user regenerate beat itu di Flow.
8. Angka yang kamu laporkan (durasi, wpm, LUFS, ukuran file, waktu render, jumlah request) harus dari output
   perintah atau ffprobe.
9. Bahasa ke user: ikuti user (biasanya Indonesia santai). Laporan singkat: apa yang jadi, path file, apa yang perlu user lakukan.
10. **Key Gemini hanya dipakai di Muse.** Jangan membuat task/penjadwal TTS di laptop; task lama sudah dimatikan (00).
11. **Upload satu file per slot**, tidak pernah batch beberapa part sekaligus (07).
