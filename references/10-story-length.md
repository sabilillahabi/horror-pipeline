# 10 — Panjang cerita & outline (jilid)

Satu **jilid** = satu season. Panjang cerita diputuskan SEBELUM menulis episode apa pun.

## Panjang
- Default **1 jilid = 4 episode = 1 bulan tayang** (keputusan Bil, 28 Nov 2026): 4 episode x 4 part = 16 part,
  ±35–40 menit cerita. Struktur: ep1 pembuka, ep2–3 komplikasi dan reveal, ep4 klimaks dan penutup.
  Pengecualian: Juru Kunci jilid 1 = 6 episode (sudah berjalan sebelum aturan ini).
- Cerita dipadatkan dengan memotong **subplot**, bukan suasana: tiap adegan tetap pelan dan detail (bunyi, rasa
  dingin, gerak kecil tokoh). Lebih sedikit kejadian, tiap kejadian lebih dalam.
- Jumlah jilid tidak dibatasi. Jilid berikutnya hanya dibuat kalau minat penonton bagus (lihat Checkpoint), dan
  setiap jilid baru butuh outline sendiri yang disetujui Bil.
- Nomor episode **mulai lagi dari 1 di setiap jilid** (keputusan Bil, 25 Nov 2026). Supaya folder tidak bertabrakan,
  setiap jilid baru punya folder cerita sendiri: `stories/<slug>-jilid2/` (salin `story.yaml` dan `sound_assets.yaml`,
  tambah `jilid: 2`), dengan `outline.yaml` dan `episodes/ep01/` sendiri. Jilid 1 tetap `stories/<slug>/`.
  Cara menampilkan jilid ke penonton (mis. "Juru Kunci Jilid 2 · Eps 1") diputuskan Bil saat jilid 2 dimulai.
- Penonton TIDAK diberi tahu posisi dalam jilid. Judul, label video ("<Judul> · Eps N · Part N/M"), caption, dan
  Threads hanya memakai "Eps N" dan "Part N/M" — tidak pernah "1/9", "Jilid 1", atau jumlah total episode.

## Isi satu episode
- 3–4 part vertikal (masing-masing <= 2:55; pada ±115 wpm praktis selalu 4 part) + 1 video panjang horizontal.
- Script 1.100–1.300 kata per episode (±4,5–5 ribu kata untuk jilid 4 episode). Detail format: 01.
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
- **Batas episode:** episode hanya berisi `key_events` miliknya dan berhenti di `cliffhanger`-nya. Kejadian, reveal,
  atau penyelesaian episode lain tidak boleh dipakai lebih awal (lihat 01).
- **Gerbang naskah:** sebelum TTS/render, kirim teks lengkap semua part (+ jumlah kata per part) ke Bil dan tunggu OK.
  Setelah OK, ubah status episode jadi `approved`; setelah dirilis/diserahkan, `done`.
- `python horror.py check <story> <ep>`: error kalau ep >= 2 tanpa outline.yaml atau episode tidak tercantum;
  peringatan kalau status masih `draft` (atau ep01 tanpa outline).

## Checkpoint
Setelah episode 2 sebuah jilid tayang 7 hari, bandingkan rata-rata view-through dan views per part dengan
baseline channel sendiri.
- Jelas di bawah baseline: jangan rencanakan jilid 2; tutup jilid sesuai outline.
- Sehat: Bil boleh memutuskan menyiapkan outline jilid 2 (cerita yang sama) atau cerita baru.
- Tidak pernah memperpanjang di luar outline tanpa persetujuan Bil.
