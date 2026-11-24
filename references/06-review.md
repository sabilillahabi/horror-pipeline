# 06 — Review (wajib setelah setiap render)

`build` selalu diakhiri `review`; ulang tanpa render: `python horror.py review <slug> <ep>`
(memakai render terakhir; untuk yang lain:
`python -c "from pipeline.common import Episode; from pipeline.review import review; ep=Episode('<slug>','<ep>'); review(ep, ep.cache/'render_vertical.json')"`).

## Part vertikal (`output/vertical/review_report.md`) — FAIL = NEEDS FIX
Per part: durasi **> 2:55** · **salah satu frame di 3 detik pertama gelap** (luma rata-rata < 20, dicek tiap
0,25 s) · **3 detik pertama berisi kartu teks/hitam** (dari rencana shot) · **detik pertama hening** (< −50 dB) ·
tempo di luar **105–135 wpm** (patokan ep01 final ±115) · loudness/true peak. Tabel per part: durasi, kata, wpm, ukuran (peringatan
> 40 MB), LUFS/TP, luma minimum, level detik pertama, cover; plus hook (baris pertama) dan cliffhanger
(baris terakhir) tiap part.
**`output/vertical/first_frames.png`** = frame pertama semua part berdampingan — selalu buka dan cek: harus gambar
yang jelas, bukan hitam/kartu. Contact sheet per part: `review_sheet_partN_XX.png`; peta crop `review_crops_*.png`.

## Video panjang — pemeriksaan otomatis (review_report.md)
tempo per part (105–135 wpm) dan durasi part (≤ 2:55) · loudness (−14 ±1 LUFS, TP ≤ −1, LRA) · jarak musik+ambience di jeda vs suara (12–26 dB) · gambar > 12 s
(peringatan saja, jangan diubah otomatis) · hening > 3 s / layar hitam / gambar beku yang tidak disengaja ·
subtitle tumpang tindih/terlalu cepat/tagline masuk subtitle · chapter YouTube (satu per part, mulai 00:00) ·
thumbnail (ukuran, < 2 MB) · Threads (post > 500, thread > 15 post).

## Cek visual — tugasmu, jangan dilewati
Buka **semua** `review_sheet_*.png` (1 frame / 4 s, subtitle seperti di video) dan untuk vertikal juga
`review_crops_*.png` (kuning = posisi awal crop, biru = akhir pan). Periksa per timestamp:
1. subtitle menimpa teks di layar?
2. wajah/objek kunci (HP, kunci, tusuk konde, gerbang, tangan) terpotong oleh crop/zoom?
3. gambar salah/tidak Jawa (kuburan Eropa, teks Inggris, tokoh salah, jumlah benda salah)?
4. potongan mendadak, ghosting aneh, hitam/beku tak sengaja?
5. outro terbaca, cover part benar.
Untuk part, buka juga `first_frames.png`. Tulis temuan di `review_visual_<nama-video>.md` (part:
`review_visual_epXX_parts.md` di `output/vertical/`) di folder video (format: bagian "Diperbaiki", "Masih
terpotong — saran override", "Gambar kurang Jawa", "Lainnya"), lalu jalankan `review` lagi supaya masuk laporan.

## Memperbaiki
- Bug teknis (loudness, crop logika, subtitle posisi, file rusak) → perbaiki kode/konfigurasi, render ulang
  bagian yang perlu, review lagi sampai 0 NEEDS FIX.
- Kreatif (gambar kurang Jawa, crop kurang pas karena data posisi) → laporkan dengan saran konkret:
  `vertical_crop_x: 0.6`, `position: right`, atau "regenerate b026b dengan culture lock". Jangan ubah tanpa izin.
- Durasi audio di beat hitam panjang: pastikan tidak ada > 2 s yang cuma hening/room tone.
- Tempo di luar 105–135 wpm: ikuti aturan keputusan tempo di 03 (repace 1.2 / 0.9), tanpa kuota.
  Part > 2:55: pindahkan batas part ke cliffhanger lebih awal (01), jangan memotong di tengah kalimat.
