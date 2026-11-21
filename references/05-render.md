# 05 — Render (horizontal, vertikal, cover, Threads)

Selalu satu render berat pada satu waktu. Render penuh 14 menit ≈ 45–60 menit per orientasi (CPU biasa);
cache klip dipakai ulang, jadi render ulang setelah perubahan kecil jauh lebih cepat.

## Preview bab 1 (minta OK user sebelum episode penuh)
```bash
python horror.py build <slug> <ep> --beats b001-b027             # → output/preview_b001-b027.mp4 + review
python horror.py build <slug> <ep> --beats b001-b027 --vertical  # → output/vertical/preview_… + part + cover
```

## Episode penuh
```bash
python horror.py build <slug> <ep>               # YouTube: output/epXX.mp4, .srt, description.txt, review
python horror.py build <slug> <ep> --vertical    # TikTok + part IG/FB + cover + captions + review
python horror.py threads <slug> <ep>             # sesudah vertikal (agar video part ikut dirujuk)
```
Yang terjadi otomatis:
- timeline: cold open 0,5 s → beat (tanpa kartu bab) → kartu "Bersambung" → outro; chapter YouTube di description
- vertikal: crop 9:16 mengikuti tokoh (posisi dari script, close-up tidak di-pan, pan pelan hanya untuk shot
  lebar tanpa tokoh), subtitle Arial/Liberation Bold 64 px, maks 2 baris, di tengah, di atas 320 px bawah,
  140 px kanan kosong; label "Judul · Eps N" kecil di atas
- part IG/FB: ≤ 3 menit, dipotong di batas beat setelah kalimat menggantung/SFX hit, kartu 1 s "… · Part N"
  di awal dan 1,5 s "Lanjut ke Part N+1" di akhir; tiap part dinormalisasi sendiri (−14 LUFS, ≤ −1.5 dBTP)
- cover part: judul dipotong persis dari `thumbnail_9x16.jpg` (`thumbnail/title_epXX.png`, sekali per episode)
  + "PART N" di bawah "EPISODE N"; latar = gambar terkuat di part itu (SFX hit / close-up tokoh, crop `detail`
  dihindari, tiap gambar sekali saja), 40% atas digelapkan; disematkan di video part dan disalin `*_cover.jpg`.
  TikTok tetap `thumbnail_9x16.jpg`. Ganti gambar: `covers.yaml` lalu `python horror.py covers <slug> <ep>`
  (detik, tanpa render). Cek `covers/covers_sheet.png`.

## Mengejar tenggat
- render bab yang sudah punya audio dulu; TTS sisa bisa menyusul
- `render: {preset: veryfast}` di story.yaml mempercepat gabung akhir ±3×; kembalikan ke `medium` setelahnya
- jangan menjalankan horizontal & vertikal bersamaan di mesin dengan RAM < 16 GB
