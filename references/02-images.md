# 02 — Gambar (Google Flow, diimport ke Muse)

**Jumlah: 25–30 gambar Flow baru per episode, selalu 16:9** (vertikal dipotong otomatis). Beat lain memakai
`reuse: <beat>` + `crop: wide | closeup_face | detail`. `prompts` mencetak jumlah gambar baru dan memperingatkan
di atas 30. Setelah import: `python scripts/push_assets.py --story <slug> --ep <ep>` (00).

Gambar dibuat user di **Google Flow**, bukan di Muse. Tugasmu: siapkan prompt, import hasilnya, cek visual.
Semua gambar 16:9. Versi vertikal, Threads 4:5 dan cover dipotong otomatis dari gambar ini.

## 1. Prompt untuk Flow
```bash
python horror.py prompts <slug> <ep>                 # → output/flow_prompts.md (prompt per beat + ref tokoh)
python horror.py prompts <slug> <ep> --missing-only  # hanya beat yang gambarnya belum ada
```
Kirim isi `flow_prompts.md` ke user. Di Flow user memakai gambar referensi tokoh (character sheet) untuk setiap
beat bertokoh, rasio 16:9, dan menamai/mengunduh hasilnya dengan id beat (`[b018a] …` atau `b018a_<hash>`).
Pastikan `style_block` di story.yaml memuat culture lock (pedesaan Jawa, gapura batu, kijing/nisan Jawa, tanpa
elemen Eropa, tanpa teks) sebelum membuat prompt.

## 2. Import hasil Flow
User mengunggah zip/folder download Flow ke workspace:
```bash
python horror.py import-flow <slug> <ep> <path-zip-atau-folder>
python horror.py check <slug> <ep>                   # semua gambar lengkap? thumbnail ada?
```
- Gambar lokal yang lebih baru tidak ditimpa ("kept newer local version"); ganti paksa: `--force` (yang lama
  dibackup ke `images/_backup/<waktu>/`). Beberapa take untuk satu beat → yang terbaru dipakai.
- File `[bXXX-old]` dilewati.

## 3. Cek visual setiap gambar (buka file-nya)
- wajah/baju sesuai referensi tokoh; jumlah orang sesuai `characters_in_scene`; posisi sesuai `position`
- detail Jawa: tidak ada kuburan Eropa (nisan tinggi, pagar besi, kapel), gerbang makam konsisten (gapura batu),
  tidak ada teks bahasa Inggris/tulisan terbaca
- benda/angka sesuai narasi (mis. "tiga jari" = tiga jari)
Masalah → beri user daftar beat + perbaikan prompt untuk diulang di Flow, lalu import lagi.

## 4. Thumbnail episode (juga dari Flow)
Dua gambar dengan judul tertulis (gaya tetap: "JURU KUNCI" krem slab-serif bercahaya merah, "EPISODE N" putih
condensed, rata kiri di sepertiga atas; karakter utama). Nama file `thumb_epXX_16x9` dan `thumb_epXX_9x16`
(akhiran/kurung bebas), ikut di folder import:
```bash
python horror.py import-flow <slug> <ep> <folder>   # → thumbnail/thumbnail_16x9.jpg (1280x720 <2MB) + thumbnail_9x16.jpg
```
`thumbnail_9x16.jpg` adalah sumber judul semua cover part — judulnya harus bersih, di latar gelap.
