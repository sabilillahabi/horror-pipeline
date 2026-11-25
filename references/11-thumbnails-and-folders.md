# 11 — Thumbnail, cover part & kerapian folder

Keputusan Bil, 25 Nov 2026. Patuhi tanpa diminta. Contoh resmi ada di `references/style/`.

## A. Format thumbnail & cover (wajib sama di setiap episode)

| File | Contoh resmi | Isi |
|------|--------------|-----|
| `thumbnail/thumbnail_16x9.jpg` (YouTube long) | `style/thumbnail_16x9_ep01.jpg` | Judul 2 baris besar di **sepertiga kiri**, "EPISODE N" di bawahnya (tengah terhadap judul); tokoh/adegan di kanan |
| `thumbnail/thumbnail_9x16.jpg` (sumber cover) | `style/thumbnail_9x16_ep01.jpg` | Judul 1 baris lebar di **atas tengah** (±10–20% dari atas), "EPISODE N" di bawahnya **rata kiri** sejajar huruf J |
| `output/vertical/epXX_partN_cover.jpg` (IG/FB/TikTok/Shorts) | `style/part_cover_ep01_part2.jpg` | Persis layout 9x16 + baris ketiga "PART N"; latar = gambar terkuat part itu |

Tipografi (sama persis dengan ep01):
- **"JURU KUNCI"**: serif klasik berkait tebal (bukan condensed, bukan sans), warna krem/gading, cahaya/outline
  merah gelap di belakang huruf. Huruf lebar dan tinggi, ±80–90% lebar frame di 9x16. Jarak aman dari tepi atas
  ±8% (jangan menempel tepi).
- **"EPISODE N"** dan **"PART N"**: sans condensed tebal, putih, bayangan halus; "PART N" sedikit lebih kecil dari
  "EPISODE N"; keduanya rata kiri sejajar awal judul (9x16/cover).
- Tidak ada teks lain (tidak ada judul bab, jilid, "x/9", tagline, logo channel).
- Latar boleh beda per episode/part; teks di area gelap supaya terbaca.

Contoh SALAH: `style/WRONG_part_cover_ep02_part1_muse.jpg` — judul memakai font slab condensed yang beda dari ep01,
menempel tepi atas, "EPISODE/PART" terlalu kecil. Cover dibuat dari nol, bukan lewat `covers`.

Cara membuat (jangan menyimpang):
1. Thumbnail 16x9 dan 9x16 digenerate di Flow (09), dengan **`style/thumbnail_16x9_ep01.jpg` dan
   `style/thumbnail_9x16_ep01.jpg` dilampirkan sebagai referensi** + prompt: "same title lettering, colors and
   layout as the reference; change only the background scene and the episode number". Teks: judul + "EPISODE N" saja.
2. Bandingkan berdampingan dengan contoh resmi. Font/posisi/warna beda → ulang (atau edit di Flow) sebelum import.
3. Cover part **hanya** lewat `python horror.py covers <slug> <ep>` (judul dipotong dari `thumbnail_9x16.jpg`
   + "PART N"). Jangan membuat cover part sendiri di Flow, Canva, atau editor lain.
4. Kirim ke Bil satu contact sheet: thumbnail 16x9, 9x16, dan semua cover part, di samping contoh resmi.

## B. Kerapian aset

**Google Flow**
- Satu project per cerita ("Juru Kunci"). **Sebelum generate apa pun untuk satu episode, buat dulu collection**
  `<Judul> - Eps NN` (mis. "Juru Kunci - Eps 03") dan generate/pindahkan semua hasil episode itu ke sana:
  gambar adegan, regenerasi, dan thumbnail. Tidak ada gambar episode yang tertinggal di luar collection.
- Download hanya lewat "Download collection" dari collection episode itu.

**Google Drive (kalau upload hasil)**
- Buat/pakai folder dulu, jangan upload ke root atau folder acak:
  `Kemenyan Malam/<Judul>/Eps NN/` dengan subfolder `vertical/` (part + cover), `long/` (video panjang +
  thumbnail 16x9 + srt), `publish/` (publish.md, caption).
- Cek folder sudah ada sebelum membuat (jangan buat duplikat "Eps 02 (1)"). Nama file tetap nama output pipeline
  (`ep02_part1.mp4`, `ep02_part1_cover.jpg`, `ep02.mp4`, …).
- Laporkan ke Bil link folder episode, bukan link per file.
