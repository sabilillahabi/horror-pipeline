---
name: "horror_serial"
description: "Produksi cerita horor bersambung (YouTube 16:9 + TikTok/IG/FB 9:16 + Threads) dari script.yaml sampai file siap upload di Muse AI: prompt gambar untuk Google Flow (gambar dibuat user di Flow lalu diimport), narasi Gemini TTS, lapisan suara (musik/ambience/SFX), render horizontal & vertikal, outro channel, cover per part, caption, thread Threads, dan review teknis + visual. Pakai saat user mau membuat / melanjutkan episode cerita horor (mis. Juru Kunci, channel Kemenyan Malam)."
---

# Horror Serial Pipeline (Muse AI)

Pipeline Python (`horror.py`) yang sudah dipakai untuk "Juru Kunci · Eps 1" (channel Kemenyan Malam).
Kamu (agen Muse) menjalankan perintahnya, memeriksa hasilnya, dan berhenti di setiap titik persetujuan.
Semua path di bawah relatif ke folder skill ini (`$SKILL`), mis. `~/workspace/skills/horror-serial/`.

## Tahap 0 — Wajib sebelum apa pun
1. Setup sekali: ikuti `references/00-setup.md` (venv, ffmpeg, font, `.env` berisi `GEMINI_API_KEYS`).
   Jalankan `python horror.py check <story> <ep>`; semua error setup harus beres dulu.
2. Tanyakan ke user (jangan menebak):
   - cerita (`stories/<slug>/`) dan episode (`ep01`, `ep02`, …); cerita baru atau lanjutan?
   - apakah `script.yaml` episode ini sudah ada/dikunci, atau perlu ditulis dulu (`references/01-story-and-script.md`)
   - gambar dibuat **user di Google Flow** (bukan di Muse): sudah ada yang diunggah, atau perlu prompt dulu?
   - target upload hari ini (YouTube saja, atau + TikTok/IG/FB/Threads) dan tenggat waktunya
3. Output selalu dua orientasi dari gambar 16:9 yang sama: YouTube 1920x1080 dan vertikal 1080x1920.
   Jangan pernah generate gambar 9:16 terpisah — versi vertikal dipotong dari 16:9 secara otomatis.

## Alur kerja (urut, jangan lompat)
| # | Tahap | Perintah utama | Referensi |
|---|-------|----------------|-----------|
| 1 | Story & script dikunci | `prompts`, `check` | 01 |
| 2 | Prompt Flow → user generate di Google Flow → upload → import | `prompts`, `import-flow <zip/folder>`, `check` | 02 |
| 3 | Thumbnail episode (16:9 + 9:16), juga dari Flow | `import-flow <folder>` | 02 |
| 4 | Narasi + outro channel | `tts`, `channel-tts` | 03 |
| 5 | Lapisan suara | `sound-import <folder>` | 04 |
| 6 | Preview bab 1 → **persetujuan user** | `build --beats <bab1>` (+ `--vertical`) | 05 |
| 7 | Episode penuh | `build`, lalu `build --vertical` (satu per satu) | 05 |
| 8 | Cover part IG/FB + Threads | otomatis di `build --vertical`; `covers`, `threads` | 05, 07 |
| 9 | Review teknis + **cek visual oleh kamu** | otomatis setelah build; `review` | 06 |
| 10 | Paket upload + caption | lihat tabel di 07 | 07 |

Sebelum mulai baca `references/08-lessons.md` — semua bug di sana sudah pernah terjadi.

Rilis: **Shorts dulu, long belakangan** — jadwal mingguan dan aturan part ≤ 2:55 ada di `references/07-publish.md`.
Kalau workspace punya browser yang login ke akun Google Bil dan Bil minta kamu sendiri yang generate gambar di Flow
atau download suara di Pixabay, ikuti `references/09-flow-and-pixabay-browser.md`.

## Output Contract (per episode, di `stories/<slug>/episodes/epXX/`)
- `output/epXX.mp4` (YouTube, 1920x1080, −14 LUFS ±1, true peak ≤ −1 dBTP) + `epXX.srt` + `description.txt` (chapter)
- `thumbnail/thumbnail_16x9.jpg` (1280x720, < 2 MB) dan `thumbnail_9x16.jpg` (1080x1920)
- `output/vertical/epXX.mp4` (TikTok) + `epXX_partN.mp4` (IG/FB, ≤ 3 menit, tiap part −14 LUFS, ≤ −1.5 dBTP)
- `output/vertical/covers/epXX_partN_cover.jpg` + `covers_sheet.png`; `captions.txt`
- `output/threads/babN.md` + `images/`
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
8. Angka yang kamu laporkan (durasi, LUFS, ukuran file, jumlah beat) harus dari output perintah atau ffprobe.
9. Bahasa ke user: ikuti user (biasanya Indonesia santai). Laporan singkat: apa yang jadi, path file, apa yang perlu user lakukan.
