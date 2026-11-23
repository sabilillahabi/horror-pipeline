# 08 — Pelajaran dari Juru Kunci Eps 1 (semuanya pernah terjadi)

1. **Prompt tanpa "Jawa" = gambar Eropa.** b026b keluar kuburan Victoria, b001/b067c gerbang besi, b061a label
   bahasa Inggris. Culture lock di `style_block` dan cek visual setiap gambar.
2. **`position` salah = tokoh terpotong di 9:16.** b071 ditulis center padahal kanan. Tulis posisi sesuai gambar.
3. **Beat `reuse` + close-up sempat di-pan** (dianggap tanpa tokoh) dan memotong wajah. Sudah diperbaiki di kode
   (warisi tokoh dari sumber, close-up/detail tidak di-pan). Kalau muncul lagi: bug, bukan kreatif.
4. **Subtitle vertikal sempat miring ke kiri** karena margin kiri/kanan tidak simetris. Margin sekarang 150/150.
5. **Part IG/FB adalah potongan mix episode** — loudness tiap part berbeda (part 5 −17 LUFS). Normalisasi per part
   dengan gain + limiter; target peak −2.5 sebelum AAC karena AAC menaikkan puncak ±1 dB.
6. **Cache klip tidak tahu kodenya berubah.** Outro lama sempat terpakai setelah layout baru. Setiap perubahan
   tampilan kartu/cover harus ikut di kunci cache (`layout`, `vlayout`).
7. **Dua build bersamaan berbagi file cache audio** (`mix_channel.wav`) → PermissionError. Vertikal sekarang pakai
   nama sendiri (`_v`), tapi tetap jalankan satu per satu.
8. **Menghentikan tugas/terminal bisa ikut membunuh ffmpeg lain** (kode 0xC000013A di Windows) → render gagal di
   tahap gabung. Jangan kill; tunggu selesai.
9. **RAM habis** saat horizontal + vertikal + pre-render jalan bersamaan → tugas dihentikan. Satu per satu.
10. **Gabung akhir dengan grain lambat** (±0,2× realtime di `medium`). Sekarang default encoder hardware atau
    libx264 veryfast + CRF 22 + maxrate 6M (`pipeline/encode.py`); jangan kembali ke `medium`.
11. **Download lama bisa menimpa gambar baru.** `import-flow` kini menolak sumber lebih lama (tanggal entri zip,
    bukan mtime hasil ekstrak) + backup. Jangan pakai `--force` sembarangan.
12. **Kuota Gemini free tier kecil** (10/hari/key). Rencanakan: TTS selesai sehari sebelum tenggat render.
13. **Thumbnail/cover:** user menolak hook teks besar dan badge — gaya cover = judul thumbnail persis + "PART N".
14. **Review tanpa melihat gambar tidak cukup.** Banyak masalah (crop, gambar Eropa, jari) hanya terlihat di contact sheet.
15. **Hook caption jangan membocorkan ending** (hook part 6 otomatis sempat menyebut "dia menoleh… menghilang").
16. **Upload IG/FB sebagai Reels**; post video biasa di FB memotong 9:16 jadi 4:5 di feed.

## Dari peralihan ke format part (23 Nov 2026)
17. **Ep01 jalan ±85 wpm** — terlalu lambat untuk Shorts. Penyebab: style default "bercerita pelan", hampir semua
    baris di styles.yaml bilang "pelan"/"jeda panjang", dan pause 1–2 s. Sekarang: frasa tempo di semua style,
    maks 3 baris pelan per part, pause ≤ 0,6 s (1,0 s cliffhanger). `review` menandai < 120 wpm.
18. **Jangan generate ulang hanya untuk mempercepat**: `repace` (atempo 1,2–1,3 + potong hening + pendekkan jeda
    dalam klip) memakai klip yang ada. Setelah itu `tts.locked: true` — tanpa itu, perubahan style default membuat
    `tts` menganggap semua klip usang dan menghabiskan kuota.
19. **Part ≤ 2:55 termasuk semuanya.** Kartu pembuka 1 s + "Lanjut ke Part" 1,5 s dulu memakan waktu dan membuat
    penonton swipe di detik pertama. Sekarang tanpa kartu; 3 detik pertama harus gambar (review FAIL kalau gelap).
20. **Batas part ditulis di script, bukan dicari otomatis.** Pemotong otomatis lama bisa memotong di tengah
    adegan; `parts:` memaksa hook di awal dan cliffhanger di akhir tiap part.
21. **Style yang unik per beat memboroskan request.** Beat berurutan dengan pembicara + style sama digabung jadi
    satu request (ep01: 95 → 56). Jangan memberi style ke baris biasa.
22. **ffmpeg 6 vs 7:** `-/filter_complex <file>` hanya ada di ffmpeg 7; di ffmpeg 6 (Linux/Muse) pipeline memakai
    `-filter_complex_script` otomatis. `silenceremove` (dipakai `repace`) berperilaku sama sejak 6.1.
23. **Mix audio dua kali = dua hasil berbeda + waktu terbuang.** Vertikal dulu me-mix ulang (`_v`). Sekarang satu
    `mix_story.wav` per episode untuk panjang dan semua part.
24. **Aset tidak ada di `main`.** Muse memulihkan dari branch `muse-assets` (00); setelah TTS/import gambar baru,
    push lagi dengan `scripts/push_assets.py`. Laptop tidak lagi menjalankan TTS terjadwal (key dipakai satu tempat).

