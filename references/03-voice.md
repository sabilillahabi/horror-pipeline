# 03 — Narasi (Gemini TTS) + outro channel

```bash
python horror.py tts <slug> <ep> --plan             # rencana: berapa request, beat mana yang digabung (tanpa API)
python horror.py tts <slug> <ep>                    # resume: klip yang sudah ada tidak dibuat ulang
python horror.py tts <slug> <ep> --beats b008,b011  # tes beberapa beat (untuk minta OK voice/style)
python horror.py channel-tts <slug> <ep>            # outro channel (sekali per channel; --force untuk ulang)
```

## Tempo (wajib): 130–150 wpm
Ep01 lama jalan ±85 wpm — terlalu lambat untuk Shorts. Aturannya sekarang:
- Voice dan karakter tokoh tetap sama. Style default setiap pembicara = style tokoh di `story.yaml` +
  `gemini_pace` (default **"Tempo sedang, mengalir, tidak diseret."**). Style tokoh tidak boleh berisi
  "pelan"/"lambat".
- Baris pelan/dramatis hanya lewat `styles.yaml`, **maks 3 per part**. Baris yang ditandai pelan tidak mendapat
  frasa tempo. `check` memperingatkan kalau lebih.
- `pause_after` maks 0,6 s, 1,0 s hanya di cliffhanger part, beat hitam maks 1,5 s (dipotong otomatis).
- `review` mengukur wpm per part (kata ÷ durasi part) dan menandai < 120 atau > 165.

## Lebih sedikit request
Beat berurutan dalam satu part dengan pembicara dan style yang sama dikirim sebagai **satu** request Gemini
(maks 6 beat / 900 huruf), lalu audionya dipotong lagi per beat di jeda antar paragraf. Setiap potongan dicek
(durasi vs panjang teks; jeda yang dipilih harus ≥ 0,16 s); kalau ada yang meragukan, blok itu otomatis diulang
per beat. Laporan akhir: `request dipakai: X (tanpa penggabungan: Y; Z blok jatuh ke per-beat)`. Jangan beri
style ke baris yang tidak butuh — style berbeda memutus penggabungan. Ep01 dengan styles.yaml baru: 56 request
untuk 95 klip (dulu 95).

## Mengatur ulang tempo klip lama tanpa kuota: `repace`
```bash
python horror.py repace <slug> <ep> --sample b008 --tempo 1.3   # satu contoh → output/repace_sample_*.wav, DENGARKAN
python horror.py repace <slug> <ep> --tempo 1.3                 # semua klip
```
atempo (pitch tetap) dari klip mentah `audio/gemini/raw/`, efek dipasang ulang sesudahnya, hening awal/akhir
dipotong, jeda di dalam klip > 0,5 s dipendekkan (`--max-gap`). Klip asli dicadangkan sekali ke
`audio/gemini/_orig/`; jalankan lagi dengan tempo lain kapan saja (selalu dari raw). Setelahnya `script.yaml` berisi
`tts: {locked: true}` — `tts` tidak akan membuat ulang klip (style default berubah, tanpa kunci semua klip akan
di-generate ulang dan menghabiskan kuota). Batas wajar 1,2–1,3; di atas itu cek suara serak/terburu-buru.

## Lain-lain
- Model `gemini-3.8-flash-tts`; voice per tokoh dari `story.yaml` (`gemini_voices`).
- Voice tidak ada di katalog → pipeline berhenti dan menyarankan voice terdekat. Jangan mengganti diam-diam;
  tanyakan user.
- Efek phone/echo/whisper diterapkan setelah TTS (raw tersimpan di `audio/gemini/raw/`, ganti efek tidak butuh API).
- Kuota: rotasi otomatis antar key. Kalau semua habis, laporkan "selesai X/Y, sisa Z" ke user dan coba lagi
  nanti (kuota pulih bertahap dalam 24 jam). Key hanya dipakai Muse — task terjadwal di laptop sudah dimatikan
  (00), jangan membuat penjadwal TTS baru tanpa izin.
- `--engine edge` = edge-tts (cadangan offline/darurat, suara berbeda — hanya atas izin user).
- Setelah TTS selesai: `python scripts/push_assets.py --story <slug> --ep <ep>` supaya klip tersimpan di
  `muse-assets` (00).

## Outro channel (`channels/kemenyan-malam.yaml`)
Tagline dibisikkan voice Vindemiatrix, di layar hitam (tagline italic + "— Kemenyan Malam"), tidak masuk
subtitle. `channels/kemenyan-malam/audio/outro.wav` sudah ada di paket — jangan buat ulang tanpa alasan.
Outro **hanya ada di video panjang**; part vertikal tidak pernah punya outro/kartu penutup.
