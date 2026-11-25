# 01 — Story & script

Kunci script dulu, baru generate apa pun. Mengubah teks/beat setelah TTS & gambar = generate ulang.
Episode harus tercantum di `stories/<slug>/outline.yaml` dan mengikutinya — lihat `10-story-length.md`.

## Format episode (sejak 23 Nov 2026)
- **1 episode = 3–4 part.** Tiap part target **2:30–2:50**, wajib **≤ 2:55** (batas YouTube Shorts). Part
  menggantikan bab: ditulis di `script.yaml` sebagai `parts:` (judul + beats). Chapter YouTube video panjang =
  awal tiap part.
- **Panjang script tetap 1.100–1.300 kata per episode**: padat, detail, banyak dialog, semua suara tokoh tetap
  dipakai, narator "aku". Pada ±115 wpm (patokan ep01) itu ±10–11 menit = **4 part** (3 part hanya kalau ≤ ±950 kata).
- **Tiap part adalah unit sendiri:** baris pertama = hook (langsung masuk ke kejadian/pertanyaan, bukan
  pembukaan), baris terakhir = cliffhanger (kalimat menggantung/ancaman/temuan). Penonton Shorts bisa mulai dari
  part mana pun.
- **Part 2, 3, 4 dibuka dengan "hook jembatan"**: satu kalimat narator (±10–15 kata, 4–6 s) yang meringkas taruhan
  cliffhanger part sebelumnya *dengan kata baru* sekaligus memancing pertanyaan — bukan menyalin kalimatnya, bukan
  "sebelumnya…". Contoh ep01: "Kakekku ditemukan bersujud di gerbang makam, menggenggam sesuatu yang warga
  rahasiakan." · "Empat puluh tahun kakekku menjaga desa ini, sampai napas terakhir. Malam itu, giliranku." ·
  "'Kalau kamu membaca ini, Le, berarti Mbah sudah gagal melindungimu.' Itu halaman pertama buku kakek."
  Gambarnya boleh `reuse` gambar kuat dari part sebelumnya (wide), jangan text_card/hitam. Hook jembatan ikut di
  video panjang (berfungsi sebagai pembuka chapter). Hitung durasinya dalam batas 2:55.
- Kalau part terlalu mepet 2:55: turunkan jeda default part itu (`pause_after: 0.2` di level part, di bawah
  `title`) sebelum memotong teks.
- **Tanpa beat `black` / `text_card` di dalam part** (keputusan Bil, 25 Nov 2026): layar hitam atau kartu di
  tengah Shorts/TikTok membuat penonton swipe. Lompatan waktu ("Keesokan paginya") ditulis di narasi dan diberi
  gambar (baru, `reuse`, atau `crop`). Kartu teks hanya boleh sebagai beat `long_only` (video panjang saja, mis.
  "Bersambung"). `check` memperingatkan setiap beat hitam/kartu yang bukan `long_only`.
- **Batas episode:** script hanya memakai `key_events` episode itu di outline. Jangan memakai kejadian, reveal, atau
  penyelesaian milik episode lain (contoh gagal: draf ep02 pertama sudah mengembalikan tusuk konde = ep03,
  membebaskan Sumirah = ep09, dan membuka aturan keempat = ep08). Cliffhanger = cliffhanger di outline; berhenti di situ.
- Tempo: ±115 wpm seperti ep01 final (target 110–130, lihat 03). `pause_after` maks 0,6 s; 1,0 s hanya di cliffhanger part; beat hitam (video
  panjang saja) maks 1,5 s. Nilai lebih besar dipotong otomatis dan `check` memperingatkan.
- Gambar: **25–30 gambar Flow baru per episode** (16:9 saja), sisanya `reuse` + `crop` (wide / closeup_face /
  detail). `prompts` dan `check` mencetak jumlahnya dan memperingatkan di atas 30.

## story.yaml (sekali per cerita)
- `title`, `slug`, `hashtag`, `language: id`, `channel: kemenyan-malam`
- `style_block`: gaya gambar, **wajib** berisi culture lock, contoh:
  `"Dark semi-realistic digital painting, muted colors, cinematic lighting. Rural Central Java, Indonesia; Javanese architecture (joglo, gapura batu), Javanese graves (kijing, small stone or wooden nisan); no European elements, no readable text."`
- `tts_engine: gemini`, `gemini_language: id-ID`, `gemini_voices.<tokoh>: {voice, style}` — voice harus ada di
  katalog Gemini (pipeline memverifikasi dan berhenti kalau tidak ada). Voice outro channel tidak boleh dipakai tokoh.
- `characters.<tokoh>`: `name`, `block` (deskripsi visual sangat spesifik: umur, rambut, baju per item, warna), `reference` (path sheet, opsional)
- `render:` override opsional (`preset: medium` default; `veryfast` hanya untuk mengejar tenggat)

## script.yaml (per episode)
```yaml
episode: 1
title: "Pulang"
youtube_title: "…"
thumbnail: {beat: b008, text: "JANGAN DITERIMA"}   # fallback kalau thumbnail Flow/Muse tidak ada
tts: {locked: false}              # true = klip yang ada tidak pernah dibuat ulang (ep01, hasil repace)
parts:                            # 3-4 part, masing-masing <= 2:55; baris pertama hook, terakhir cliffhanger
  - title: "Gerbang"
    beats:
      - id: b001
        speaker: narrator            # narrator | <tokoh>
        text: "…"                    # teks yang dibacakan, apa adanya
        scene: "Close-up of …"       # prompt gambar (bahasa Inggris), tanpa nama tokoh
        characters_in_scene: [{name: bayu, position: right, view: from behind}]
        # opsional:
        visual: image | black | text_card
        card_text: "TIGA MINGGU SEBELUMNYA"   # untuk text_card
        reuse: b030                  # pakai ulang gambar beat lain …
        crop: closeup_face | detail | wide    # … dengan crop ini
        pause_after: 0.6             # maks 0.6; 1.0 hanya untuk beat terakhir part (default otomatis)
        long_only: true              # hanya di video panjang (mis. kartu "Bersambung" setelah cliffhanger)
        effect: phone | echo | whisper
        vertical_crop_x: 0.6         # 0 = jendela 9:16 di kiri, 1 = kanan (override crop vertikal)
        vertical_pan: left_to_right | right_to_left | none
        threads_dialogue: true       # paksa baris narator jadi dialog di Threads
```
Aturan:
- `position` harus sesuai gambar sebenarnya (left/center/right, atau `center-left`/`center-right` untuk dua tokoh
  berdekatan) — crop 9:16 memusatkan ke situ. Adegan dua tokoh: tulis `center-left` + `center-right`, jangan
  `left` + `right` (lihat 02 bagian 1b). Salah tulis
  `center` padahal tokoh di kanan = tokoh terpotong di vertikal (kasus b071).
- Beat `reuse` mewarisi tokoh dari beat sumber; tetap isi `characters_in_scene` kalau komposisinya beda.
- Kalimat yang juga muncul sebagai `text_card` akan tampil dua kali (kartu + subtitle) — sengaja, untuk aksesibilitas.

## File lain per episode
- `styles.yaml`: arahan delivery per beat untuk Gemini (`b008: "berbisik, suara bergetar"`). **Maks 3 baris
  pelan/dramatis per part** (kata seperti "pelan", "lambat", "jeda panjang", "berhenti sejenak"); baris lain
  tidak usah diberi style — beat berurutan dengan pembicara + style sama digabung jadi satu request (03).
- `sound.yaml`: musik, ambience per rentang beat, SFX per beat (lihat 04)
- `covers.yaml`: override gambar cover per part (`part3: {beat: b034}`), biasanya kosong
- `threads.yaml`: override hook/gambar Threads (biasanya kosong)

`python horror.py prompts <slug> <ep>` menulis `output/flow_prompts.md` (prompt per beat) — periksa sebelum generate.
`python horror.py check <slug> <ep>` memeriksa format: jumlah part (3–4), jumlah kata (1.100–1.300), baris
pelan per part (≤ 3), `pause_after`, part yang mulai dengan hitam/kartu, jumlah gambar baru (≤ 30).

## Memilih batas part
Hitung kata kumulatif; target ±280–320 kata per part. Potong tepat setelah kalimat menggantung (pertanyaan,
ancaman, temuan, SFX hit) dan pastikan beat berikutnya bisa jadi hook. Contoh ep01 (1.197 kata):
Gerbang b001–b018d (305) · Juru Kunci b018e–b038b (306) · Tiga Aturan b038c–b061 (301) · Tusuk Konde b061a–b077
(284, + kartu "Bersambung" b078 `long_only`).
