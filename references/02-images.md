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

## 1b. Satu gambar untuk landscape DAN vertikal (wajib)
Versi vertikal (Shorts/TikTok/Reels) hanya memakai **±⅓ lebar** gambar 16:9 (jendela 9:16 di sekitar tokoh). Jadi
setiap gambar Flow harus enak dilihat utuh dan juga saat dipotong sepertiga tengahnya:
- **Subjek utama di sepertiga tengah**: wajah, tangan, benda kunci (HP, kunci, tusuk konde, sesaji). Tidak ada detail
  penting di pinggir kiri/kanan.
- **Kiri-kanan = suasana** (beringin, kabut, dinding, gelap): boleh terpotong di vertikal, tetap sinematik di landscape.
- **Ada ruang di atas kepala**: di vertikal bagian atas tertutup label "Judul · Eps N · Part N/M", bagian bawah
  tertutup subtitle.
- **Dua tokoh atau lebih: berdekatan di tengah.** Di script pakai `position: center-left` dan `center-right`
  (jangan `left` + `right`, itu ujung ke ujung — di vertikal hanya pembicara yang kelihatan). `check` memperingatkan.
- Satu tokoh: `center` paling aman; `left`/`right` boleh (jendela vertikal mengikuti posisi), asal sesuai gambar.

`prompts` menambahkan ini otomatis ke setiap prompt: kalimat dari `composition_block` di story.yaml (default:
*"Main subject centered in the middle third of the frame, important details away from the left and right edges,
atmospheric empty space on both sides, headroom above."*), plus *"The characters stand close together near the
center of the frame."* untuk beat dengan 2+ tokoh. Jangan menghapusnya dari prompt saat menyalin ke Flow.

Saat cek visual (bagian 3) lihat juga `review_crops_*.png` setelah render vertikal: subjek terpotong → minta
regenerate dengan komposisi tengah, atau koreksi `vertical_crop_x` (0 = kiri, 1 = kanan).

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
- subjek utama di sepertiga tengah, tidak ada detail penting di pinggir kiri/kanan (aman untuk vertikal, 1b)
- detail Jawa: tidak ada kuburan Eropa (nisan tinggi, pagar besi, kapel), gerbang makam konsisten (gapura batu),
  tidak ada teks bahasa Inggris/tulisan terbaca
- benda/angka sesuai narasi (mis. "tiga jari" = tiga jari)
Masalah → beri user daftar beat + perbaikan prompt untuk diulang di Flow, lalu import lagi.

## 4. Thumbnail episode (juga dari Flow)
Dua gambar dengan judul tertulis. Format, tipografi, dan contoh resmi: **11** (`references/style/`) — lampirkan
contoh ep01 sebagai referensi di Flow. Nama file `thumb_epXX_16x9` dan `thumb_epXX_9x16`
(akhiran/kurung bebas), ikut di folder import:
```bash
python horror.py import-flow <slug> <ep> <folder>   # → thumbnail/thumbnail_16x9.jpg (1280x720 <2MB) + thumbnail_9x16.jpg
```
`thumbnail_9x16.jpg` adalah sumber judul semua cover part — judulnya harus bersih, di latar gelap.
