# 10 — Panjang cerita & outline (jilid)

Satu **jilid** = satu season. Panjang cerita diputuskan SEBELUM menulis episode apa pun.

## Panjang
- Default **1 jilid = 9 episode = 3 arc x 3 episode**. Rentang 6–12 episode hanya kalau cerita jelas membutuhkannya.
- Jumlah jilid tidak dibatasi. Jilid berikutnya hanya dibuat kalau minat penonton bagus (lihat Checkpoint), dan
  setiap jilid baru butuh outline sendiri yang disetujui Bil.
- Nomor episode **berlanjut** antar jilid (jilid 2 dimulai Eps 10).
- Penonton TIDAK diberi tahu posisi dalam jilid. Judul, label video ("<Judul> · Eps N · Part N/M"), caption, dan
  Threads hanya memakai "Eps N" dan "Part N/M" — tidak pernah "1/9", "Jilid 1", atau jumlah total episode.

## Isi satu episode
- 3–4 part vertikal (masing-masing <= 2:55; pada ±115 wpm praktis selalu 4 part) + 1 video panjang horizontal.
- Script 1.100–1.300 kata per episode (±10–11 ribu kata untuk 9 episode). Detail format: 01.
- Setiap episode berakhir dengan **cliffhanger**. Setiap akhir arc berakhir dengan **reveal** yang lebih besar.
- Episode terakhir jilid menutup semua benang cerita jilid itu. Kalau ada kelanjutan (jilid berikutnya), pancingannya
  sudah direncanakan di outline sejak awal.

## Gerbang produksi: `stories/<slug>/outline.yaml`
- Wajib ada sebelum **ep02** diproduksi (ep01 boleh mulai dengan outline kasar).
- Field per episode: `number`, `jilid`, `arc`, `working_title`, `parts` (3–4 judul part), `key_events`,
  `cliffhanger`, `reveal` (hanya episode akhir arc), `characters` (tokoh/voice yang dibutuhkan),
  `status` (`done` | `approved` | `draft`).
- Muse dan Claude Code **tidak boleh menulis atau memproduksi episode yang tidak ada di outline.yaml**.
  Episode berstatus `draft` boleh ditulis script-nya, tapi outline episode itu harus di-OK Bil (`approved`)
  sebelum TTS/render.
- Perubahan outline = usulan untuk Bil, bukan keputusan penulis/agen.
- `python horror.py check <story> <ep>`: error kalau ep >= 2 tanpa outline.yaml atau episode tidak tercantum;
  peringatan kalau status masih `draft` (atau ep01 tanpa outline).

## Checkpoint
Setelah 3 episode pertama sebuah jilid tayang 7 hari, bandingkan rata-rata view-through dan views per part dengan
baseline channel sendiri.
- Jelas di bawah baseline: padatkan outline jadi 6 episode dengan menggabungkan arc.
- Sehat: lanjutkan rencana.
- Tidak pernah memperpanjang di luar outline tanpa persetujuan Bil.
