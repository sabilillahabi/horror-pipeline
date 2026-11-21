# 01 — Story & script

Kunci script dulu, baru generate apa pun. Mengubah teks/beat setelah TTS & gambar = generate ulang.

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
chapters:
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
        pause_after: 1.2
        effect: phone | echo | whisper
        vertical_crop_x: 0.6         # 0 = jendela 9:16 di kiri, 1 = kanan (override crop vertikal)
        vertical_pan: left_to_right | right_to_left | none
        threads_dialogue: true       # paksa baris narator jadi dialog di Threads
```
Aturan:
- `position` harus sesuai gambar sebenarnya (left/center/right) — crop 9:16 memusatkan ke situ. Salah tulis
  `center` padahal tokoh di kanan = tokoh terpotong di vertikal (kasus b071).
- Beat `reuse` mewarisi tokoh dari beat sumber; tetap isi `characters_in_scene` kalau komposisinya beda.
- Kalimat yang juga muncul sebagai `text_card` akan tampil dua kali (kartu + subtitle) — sengaja, untuk aksesibilitas.

## File lain per episode
- `styles.yaml`: arahan delivery per beat untuk Gemini (`b008: "berbisik, suara bergetar"`)
- `sound.yaml`: musik, ambience per rentang beat, SFX per beat (lihat 04)
- `covers.yaml`: override gambar cover per part (`part3: {beat: b034}`), biasanya kosong
- `threads.yaml`: override hook/gambar Threads (biasanya kosong)

`python horror.py prompts <slug> <ep>` menulis `output/flow_prompts.md` (prompt per beat) — periksa sebelum generate.
