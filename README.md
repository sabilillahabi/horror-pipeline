# Pipeline Video Cerita Horor Bersambung

CLI Python untuk membuat episode YouTube cerita horor (10–15 menit, 1920×1080):
narasi **edge-tts**, gambar dari **Google Flow** (dibuat manual), render dengan **ffmpeg**.

```
prompts → (buat gambar di Flow) → check → tts → build → shorts → thumbnail
```

---

## 1. Instalasi

1. Install **Python 3.10+** dan **ffmpeg** (harus ada di PATH).
   - Windows: `winget install ffmpeg`
   - macOS: `brew install ffmpeg`
   - Linux: `sudo apt install ffmpeg`
2. Install library Python:
   ```bash
   pip install -r requirements.txt
   ```
3. (Opsional) Taruh font tebal (mis. *Anton*, *Bebas Neue*, *Oswald Bold* dari Google Fonts) di
   `assets/fonts/`. Font ini dipakai untuk kartu judul, subtitle short, dan thumbnail. Kalau kosong,
   dipakai Impact/Arial Bold dari sistem.
4. (Opsional) Taruh musik latar (`.mp3`/`.wav`) di `assets/bgm/`.

Semua perintah dijalankan dari folder ini:

```bash
python horror.py <perintah> <slug-cerita> <episode> [opsi]
```

`<episode>` boleh ditulis `ep01`, `01`, atau `1`.

---

## 2. Struktur folder

```
stories/<slug-cerita>/
  story.yaml              # judul, hashtag, style_block, daftar karakter + suara
  characters/<nama>.png   # gambar referensi karakter (untuk Flow, tidak dipakai di render)
  episodes/ep01/
    script.yaml           # naskah episode
    images/               # beat_001.png, beat_002.png ... (hasil Flow, kamu yang menaruh)
    audio/                # dibuat otomatis oleh `tts`
    output/               # video final, srt, short, thumbnail, prompt Flow, deskripsi
    cache/                # klip sementara (boleh dihapus kapan saja)
assets/
  bgm/                    # musik latar
  fonts/                  # font tebal (opsional)
```

---

## 3. Alur kerja langkah demi langkah

### Langkah 1 — Tulis `story.yaml` (sekali per cerita)

```yaml
title: "Rumah Kos Nomor 13"
hashtag: "#ceritahoror #horor"
style_block: "Dark semi-realistic digital painting, muted colors, cinematic lighting."
prompt_suffix: "No text, no captions, no watermark."   # opsional

characters:
  - name: narrator              # WAJIB ada
    voice: id-ID-ArdiNeural
    pitch: "-8Hz"
    rate: "-5%"
    effect: none
  - name: Laras
    character_block: "Laras, an Indonesian woman in her early 20s, long straight black hair, ..."
    voice: id-ID-GadisNeural
    pitch: "-2Hz"
    rate: "-5%"
    effect: none                # none | phone | echo | whisper
```

- **Suara Indonesia**: `id-ID-ArdiNeural` (pria) dan `id-ID-GadisNeural` (wanita).
  Buat variasi karakter dengan `pitch` (mis. `-15Hz` = lebih berat, `+10Hz` = lebih muda) dan
  `rate` (mis. `-10%` = lebih lambat).
- **Efek suara**: `phone` (seperti telepon), `echo` (bergema), `whisper` (berbisik, lebih pelan).
- Karakter yang hanya tampil di gambar (tidak bicara) cukup diberi `name` + `character_block`;
  tanpa `voice`, suaranya otomatis sama dengan narator (atau tulis `voice: narrator`).
- `character_block` = deskripsi visual tetap (bahasa Inggris). Dipakai otomatis di setiap prompt Flow
  supaya wajah/pakaian karakter konsisten.
- Simpan foto referensi karakter di `characters/<nama huruf kecil>.png`.

### Langkah 2 — Tulis `script.yaml` per episode

```yaml
episode: 2
title: "Kamar yang Terkunci"
recap: >-                       # dibacakan narator di awal (15–30 detik)
  Sebelumnya, Dimas baru saja pindah ...
recap_image: 3                  # opsional: gambar beat 3 saat recap (default kartu "SEBELUMNYA...")

chapters:
  - title: "Suara dari Balik Dinding"
    beats:
      - id: 1
        speaker: narrator
        text: "Malam itu hujan turun deras..."           # bahasa Indonesia, yang dibacakan
        scene: "A small dim bedroom at night, rain..."    # bahasa Inggris, TANPA deskripsi karakter/gaya
        characters_in_scene:
          - {name: Dimas, position: left foreground}

      - id: 2
        speaker: Laras
        text: "Kenapa kamu buka pintunya?"
        effect: phone                                     # opsional, menimpa efek default speaker
        reuse: 1                                          # pakai ulang gambar beat 1 (tanpa prompt baru)
        crop: closeup_face                                # wide | closeup_face | detail
        pause_after: 1.5                                  # opsional, jeda setelah beat (detik)

      - id: 3
        speaker: narrator
        text: "Tiga hari kemudian, Dimas kembali."        # tetap dibacakan
        visual: text_card                                 # image | black | text_card
        card_text: "Tiga hari kemudian."                  # teks di layar
        min_duration: 3                                   # opsional, durasi minimum (detik)

      - id: 3a                                            # ID boleh pakai huruf: b018a → images/b018a.png
        speaker: narrator
        text: "Lalu semuanya sunyi."
        visual: black                                     # layar hitam selama audio
```

Kolom beat:

| kolom | keterangan |
|---|---|
| `id` | unik; menentukan nama file gambar. Angka → `beat_001.png`; teks → apa adanya (`b018a` → `b018a.png`). Urutan tetap mengikuti naskah |
| `speaker` | `narrator` atau nama karakter dari story.yaml |
| `text` | teks narasi/dialog (boleh kosong jika `min_duration` diisi → beat hening) |
| `scene` | deskripsi gambar bahasa Inggris (tanpa karakter & style) |
| `characters_in_scene` | daftar `{name, position, view}`. `position`: `left`, `right`, `center`, `foreground`, `background` (boleh digabung: `left foreground`). `view` opsional, mis. `from behind` → masuk ke prompt Flow ("seen from behind"). Format pendek juga bisa: `- "Dimas:left"` |
| `reuse` + `crop` | pakai ulang gambar beat lain, tanpa prompt Flow baru. `crop`: `wide` (penuh), `closeup_face` (50% tengah-atas), `detail` (40% tengah). Bisa ditambah `focus: [0.4, 0.3]` untuk menggeser titik crop. (Bentuk lama `image: {beat: 3, crop: ...}` masih didukung) |
| `visual` | `image` (default), `black` (layar hitam murni selama audio), `text_card` (teks serif putih di tengah layar hitam, fade in/out; narasi tetap diputar). Teks kartu dari `card_text` (default: `text`) |
| `min_duration`, `pause_after` | opsional, dalam detik |
| `effect` | opsional, menimpa efek suara karakter untuk beat ini saja |

Tips durasi: 10–15 menit ≈ 1.300–2.000 kata narasi ≈ 80–130 beat.

### Langkah 3 — Buat prompt untuk Google Flow

```bash
python horror.py prompts rumah-kos ep02
```

Hasilnya `output/flow_prompts.md`: daftar bernomor, satu prompt per beat yang butuh gambar baru,
berisi **[deskripsi karakter + posisi] + [scene] + [style_block]**, beserta file referensi karakter
yang harus dilampirkan di Flow. Beat yang memakai ulang gambar lain tidak ikut di daftar.

Di Flow: lampirkan gambar referensi yang disebut, tempel prompt, pilih 16:9, lalu simpan hasilnya
sebagai `episodes/ep02/images/beat_XXX.png` (`.jpg`/`.webp` juga bisa).

Opsi `--missing-only` = hanya beat yang gambarnya belum ada.

### Langkah 3b — Import hasil download Flow

Beri nama gambar di Flow dengan id beat dalam kurung siku, mis. `[b018a] pintu terbuka.jpg`, lalu:

```bash
python horror.py import-flow juru-kunci ep01 "~/Downloads/Juru Kunci - Eps 01.zip"
```

- Zip diekstrak ke folder sementara (file di Downloads tidak diubah/dihapus); folder juga bisa.
- Tanpa path: otomatis memakai zip/folder terbaru di `~/Downloads` yang namanya mengandung nama cerita.
- Setiap gambar `[id] ...` disalin ke `images/<id>.png` (JPG/WEBP dikonversi ke PNG).
- File dengan id berakhiran `-old` (mis. `[b018a-old]`) dilewati.
- Kalau ada beberapa file untuk satu id, yang terbaru dipakai (ada peringatan).

### Langkah 4 — Cek gambar yang belum ada

```bash
python horror.py check rumah-kos ep02
```

Menampilkan gambar yang belum ada, file di `images/` yang tidak terpakai, status audio, dan
referensi karakter yang belum ada.

### Langkah 5 — Buat audio narasi

```bash
python horror.py tts rumah-kos ep02
```

- Satu file per beat di `audio/beat_XXX.wav` (+ `audio/recap.wav`), memakai voice/pitch/rate
  speaker dan efek ffmpeg.
- Membuat subtitle `output/ep02.srt` dan `output/description.txt` (judul + timestamp bab untuk
  deskripsi YouTube + hashtag).
- **Bisa dilanjutkan**: beat yang sudah punya audio dilewati. Kalau kamu mengubah teks/suara satu
  beat, hanya beat itu yang dibuat ulang (dicek lewat `audio/manifest.json`).
  `--force` = buat ulang semua.
- Butuh internet (edge-tts memakai server Microsoft). Kalau sering gagal, kurangi `--workers 1`.

### Langkah 6 — Render video

```bash
python horror.py build rumah-kos ep02
```

Hasil: `output/ep02.mp4` + `output/ep02.srt`.

Yang dilakukan:
- Tiap gambar tampil selama audio beat + jeda, dengan gerakan Ken Burns pelan (zoom in/out,
  pan kiri/kanan/atas/bawah bergantian).
- Maksimal 12 detik per gambar; kalau beat lebih panjang, gambar dipotong menjadi beberapa shot
  yang bergantian antara *wide* dan *crop* dari gambar yang sama.
- Crossfade pendek antar shot.
- Kartu judul bab (latar hitam, teks putih, 3 detik) di setiap awal bab.
- Musik latar dari `assets/bgm/` (file pertama, atau `bgm:` di story.yaml / `--bgm nama.mp3`),
  otomatis mengecil saat ada suara (ducking). `--no-bgm` = tanpa musik.
- Film grain halus.

**Bisa dilanjutkan**: setiap shot disimpan di `cache/clips/`. Kalau proses berhenti, jalankan lagi —
shot yang sudah jadi dilewati. Mengganti satu gambar/teks hanya merender ulang shot yang
terpengaruh. `--force` = render ulang semua. Folder `cache/` aman dihapus setelah selesai.

Jalan pintas: `python horror.py all rumah-kos ep02` = check → tts → build.

### Langkah 7 — Buat Shorts

```bash
python horror.py shorts rumah-kos ep02 --beats 12-18 --title "Kamar 13"
```

`--beats` mengikuti urutan naskah: `12-18` atau `b012-b018` ikut mengambil beat bersufiks
seperti `b018a`, `b018b`. Daftar juga bisa: `--beats b012,b015,b018a`.

- Video vertikal 1080×1920, gambar di tengah dengan latar blur, subtitle besar tertanam,
  berakhir di beat terakhir (cliffhanger) dengan jeda dan fade out.
- Harus di bawah 60 detik. Kalau lebih, perintah berhenti dan menampilkan durasi tiap beat;
  persempit rentang atau pakai `--auto-trim` (membuang beat dari awal).
- Opsi: `--hold 1.2` (jeda akhir), `--fg-scale 1.15` (ukuran gambar), `--sub-size 68`,
  `--no-bgm`, `--bgm`.
- Hasil: `output/short_ep02_b12-18.mp4`.

### Langkah 8 — Buat thumbnail

```bash
python horror.py thumbnail rumah-kos ep02 --beat 5 --text "JANGAN DIBUKA"
```

- 1280×720 dari gambar beat 5, kontras dinaikkan, tepi digelapkan, teks tebal kontras tinggi
  (maksimal 4 kata; baris terakhir berwarna merah).
- Opsi: `--position left|right|center|top|bottom`, `--color "#FFFFFF"`, `--accent "#FF2B2B"`,
  `--crop closeup_face`, `--out nama.png`.

---

## 4. Coba dulu dengan cerita contoh "tester"

Cerita contoh `stories/tester` punya karakter Dimas & Laras dan 1 episode berisi 6 beat
(2 bab, ada efek whisper/echo, text card, dan beat yang memakai ulang gambar dengan crop).

```bash
python horror.py prompts tester ep01        # lihat stories/tester/episodes/ep01/output/flow_prompts.md
python horror.py placeholders tester ep01   # buat gambar placeholder (pengganti hasil Flow)
python horror.py check tester ep01
python horror.py tts tester ep01
python horror.py build tester ep01
python horror.py shorts tester ep01 --beats 3-6 --title "Kamar 13"
python horror.py thumbnail tester ep01 --beat 5 --text "JANGAN DIBUKA"
```

`placeholders` hanya membuat gambar yang **belum ada**, jadi aman: gambar asli dari Flow tidak akan
tertimpa. Hapus placeholder lalu taruh gambar asli kapan saja; `build` akan merender ulang shot
yang berubah saja.

Tidak ada internet? `python horror.py tts tester ep01 --dummy` membuat audio nada sebagai pengganti
suara, supaya seluruh alur bisa dites. Jalankan `tts` biasa nanti — audio dummy otomatis diganti.

---

## 5. Pengaturan render (opsional)

Bisa ditimpa di `story.yaml` (semua episode) atau `script.yaml` (satu episode):

```yaml
render:
  max_shot: 12          # detik maksimal per gambar/crop
  crossfade: 0.5        # durasi crossfade (detik), 0 = potong langsung
  pause_after: 0.35     # jeda default setelah tiap beat
  chapter_end_pause: 1.2
  chapter_card: 3.0     # durasi kartu judul bab
  zoom: 0.12            # kekuatan Ken Burns (0.12 = 12%)
  grain: 8              # film grain 0–20 (0 = mati, render ~3x lebih cepat)
  bgm_volume: 0.16      # volume musik
  duck: true            # musik mengecil saat ada suara
  fps: 30
  crf: 19               # kualitas (lebih kecil = lebih bagus/besar)
  preset: medium        # kecepatan encode final (veryfast/fast/medium/slow)
```

Font lain: `font: assets/fonts/Anton-Regular.ttf`, `subtitle_font: ...`, dan `card_font: ...`
(serif untuk text_card; default Georgia/Times, atau taruh font di `assets/fonts/serif/`) di story.yaml.

---

## 6. Masalah umum

| Masalah | Solusi |
|---|---|
| `ffmpeg tidak ditemukan` | Install ffmpeg dan buka terminal baru |
| edge-tts gagal / timeout | Cek internet, coba lagi (yang sudah jadi dilewati), pakai `--workers 1` |
| Wajah terpotong di `closeup_face` | Tambah `focus: [x, y]` di `image:` (mis. `[0.3, 0.35]` = kiri atas) |
| Render lambat | `grain: 0`, atau `preset: fast` di `render:` |
| Video berubah tapi hasil sama | Hapus folder `cache/` atau pakai `--force` |
