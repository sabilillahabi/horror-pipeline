# 05 — Render (video panjang, part vertikal, cover, Threads)

Satu episode = **satu mix audio** (narasi + musik/ambience/SFX) yang dipakai video panjang dan semua part.
Mix dihitung sekali dan disimpan di `cache/mix_story.wav`; dibuat ulang hanya kalau timeline, klip, atau
`sound.yaml` berubah. Render vertikal tidak pernah menjalankan TTS atau mix lagi.

## Urutan
```bash
python horror.py build <slug> <ep>               # video panjang 1920x1080 → output/epXX.mp4 (+ srt, description, review)
python horror.py build <slug> <ep> --vertical    # part 1080x1920 → output/vertical/epXX_partN.mp4 (+ cover, captions, review)
python horror.py build <slug> <ep> --vertical --full   # + episode vertikal penuh (hanya kalau diminta)
python horror.py threads <slug> <ep>             # opsional
```
Preview sebelum episode penuh: `build --beats b001-b018d` (dan `--vertical`) → minta OK user.

## Part vertikal (YouTube Shorts, TikTok, IG Reels, FB Reels — file yang sama)
- Dipotong di batas `parts:` script.yaml dan dirender langsung per part (bukan dipotong dari video penuh).
- **Tanpa kartu pembuka**: video langsung main. **3 detik pertama tidak pernah hitam atau kartu teks**: kalau
  beat pertama part `black`/`text_card`, vertikal menampilkan gambar kuat terdekat dari part itu (skor cover:
  SFX tegang, tokoh, close-up; crop detail dihindari) dengan push-in pelan. Video panjang tetap hitam.
- **Tanpa kartu penutup sama sekali**: tidak ada "Lanjut ke Part N+1", tidak ada "Versi lengkap…", tidak ada outro
  channel. Part berakhir di cliffhanger + jeda 1,0 s dengan fade-out ambience/musik 0,5 s di akhir.
  Beat `long_only` (mis. kartu "Bersambung") tidak masuk part.
- Label kecil tetap di atas: "<Judul> · Eps N · Part N/M". Subtitle Arial/Liberation Bold 64 px, maks 2 baris.
- **Watermark "Kemenyan Malam"** (gaya yang disetujui 24 Nov 2026): serif tebal krem (font tanda tangan outro),
  ±60% opasitas + bayangan halus, 44 px, tengah atas tepat di bawah label part. Jangan pindah ke kanan/bawah
  (tertutup tombol & caption TikTok/Reels/Shorts).
- Cover per part (format: 11, contoh `references/style/part_cover_ep01_part2.jpg`): **hanya** lewat `covers`;
  judul dipotong dari `thumbnail_9x16.jpg` + "PART N", latar gambar terkuat part itu, disematkan
  di video dan disalin `epXX_partN_cover.jpg`. Ganti gambar: `covers.yaml` → `python horror.py covers <slug> <ep>`.
- Tiap part dinormalisasi sendiri (−14 LUFS, ≤ −1.5 dBTP). Target ukuran ±20–40 MB per part.

## Video panjang (YouTube)
1920x1080, satu per episode, dari mix yang sama. Struktur: cold open 0,5 s → beat (tanpa intro, tanpa kartu
bab; kartu teks cerita boleh) → outro channel (hitam, tagline italic + bold "— Kemenyan Malam", bisikan
Vindemiatrix). Outro hanya ada di sini. Chapter YouTube di `description.txt` = awal tiap part. Target < 300 MB.
Watermark "Kemenyan Malam" 42 px di pojok kanan bawah, hilang saat outro (outro sudah menulis "— Kemenyan Malam").
Setelan di `channels/<channel>.yaml` → `watermark: {text, opacity}` (`watermark: false` mematikan); tampilan di
`pipeline/channel.py` (`WM_LAYOUT`, naikkan `WM_VERSION` kalau diubah).

## Kecepatan & ukuran
- Encoder: hardware (h264_nvenc / h264_qsv / h264_amf) kalau ada dan lolos tes encode 0,2 s, kalau tidak libx264
  `-preset veryfast`. CRF/CQ 22, `-maxrate 6M -bufsize 12M`, yuv420p, High profile, 30 fps, keyframe tiap 2 s,
  +faststart; audio AAC 160 kbps 48 kHz (`pipeline/encode.py`).
- Ken Burns: tiap gambar diskala sekali ke 1,5× ukuran output (`stills/`), gerakan pakai crop/scale ffmpeg; shot
  dirender paralel (jumlah core − 1); cache shot = hash isi gambar + gerakan + durasi + resolusi + versi layout
  (`KB_VERSION`), jadi re-import gambar yang sama atau render ulang setelah perubahan kecil hampir instan.
- Subtitle vertikal dibakar dalam encode yang sama dengan gabung akhir (tidak ada encode ketiga).
- Film grain default `grain: 2`. Grain itu noise yang hampir tidak bisa dikompres: grain 5+ membuat setiap encode
  mentok di 6 Mbps (part 2:30 ±115 MB, video panjang ±470 MB); grain 2 → part ±36–40 MB, video panjang ±155 MB.
  Jangan naikkan tanpa izin user.
- Tetap satu render berat pada satu waktu; jangan kill ffmpeg yang sedang jalan.
- Waktu render dicetak di akhir `build` ("Waktu render: …") dan disimpan di manifest; laporkan ke user.
