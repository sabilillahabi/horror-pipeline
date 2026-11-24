# 03 — Narasi (Gemini TTS) + outro channel

```bash
python horror.py tts <slug> <ep> --plan             # rencana: berapa request, beat mana yang digabung (tanpa API)
python horror.py tts <slug> <ep>                    # resume: klip yang sudah ada tidak dibuat ulang
python horror.py tts <slug> <ep> --beats b008,b011  # tes beberapa beat (untuk minta OK voice/style)
python horror.py channel-tts <slug> <ep>            # outro channel (sekali per channel; --force untuk ulang)
```

## Tempo (wajib): patokan = ep01 final, ±115 wpm
Bil sudah memutuskan (24 Nov 2026): ep01 final ±115 wpm terasa pas; 134 wpm terlalu cepat; 85 wpm terlalu lambat.
**Target 110–130 wpm** (kata ÷ durasi part). `review` dan ringkasan `tts` menandai < 105 atau > 135.
- Style default setiap pembicara = style tokoh di `story.yaml` + `gemini_pace` (**"Tempo tenang, mengalir, tidak
  terburu-buru."**). Style tokoh tidak boleh berisi "pelan"/"lambat"/"cepat".
- Baris pelan/dramatis hanya lewat `styles.yaml`, **maks 3 per part**. `check` memperingatkan kalau lebih.
- `pause_after` maks 0,6 s, 1,0 s hanya di cliffhanger part, beat hitam maks 1,5 s (dipotong otomatis).

### Aturan keputusan tempo — jalankan sendiri, JANGAN tanya Bil
Setelah `tts`, baca ringkasan wpm per part (atau `review`), lalu:
| Rata-rata episode | Tindakan |
|---|---|
| 105–135 wpm | pakai apa adanya |
| < 105 wpm (mis. klip lama dengan style lambat) | `repace <slug> <ep> --tempo 1.2 --max-gap 0.8` (= setelan ep01 final) |
| > 135 wpm | `repace <slug> <ep> --tempo 0.9 --max-gap 0.8` |
- Klip hook jembatan atau baris baru yang direkam belakangan: `repace … --tempo 1.0 --max-gap 0.8 --beats <id>` (hanya
  potong hening), dan jalankan SETELAH repace seluruh episode (repace global ikut mengubah klip itu).
- Jangan pernah memakai tempo di atas 1.25 atau menghitung tempo untuk mengejar angka tertentu (contoh salah: 1.43).
- Hanya kalau setelah langkah di atas masih di luar 105–135: laporkan angka per part ke Bil.

## Lebih sedikit request
Beat berurutan dalam satu part dengan pembicara dan style yang sama dikirim sebagai **satu** request Gemini
(maks 6 beat / 900 huruf), lalu audionya dipotong lagi per beat di jeda antar paragraf. Setiap potongan dicek
(durasi vs panjang teks; jeda yang dipilih harus ≥ 0,16 s); kalau ada yang meragukan, blok itu otomatis diulang
per beat. Laporan akhir: `request dipakai: X (tanpa penggabungan: Y; Z blok jatuh ke per-beat)`. Jangan beri
style ke baris yang tidak butuh — style berbeda memutus penggabungan. Ep01 dengan styles.yaml baru: 56 request
untuk 95 klip (dulu 95).

## Mengatur ulang tempo klip tanpa kuota: `repace`
```bash
python horror.py repace <slug> <ep> --tempo 1.2 --max-gap 0.8                      # setelan ep01 final (default)
python horror.py repace <slug> <ep> --tempo 1.0 --max-gap 0.8 --beats h02,h03,h04  # hook/baris baru: potong hening saja
```
atempo (pitch tetap) dari klip mentah `audio/gemini/raw/`, efek dipasang ulang sesudahnya, hening awal/akhir
dipotong, jeda di dalam klip > `--max-gap` dipendekkan. Klip asli dicadangkan sekali ke `audio/gemini/_orig/`; selalu
dihitung dari raw, jadi aman diulang. Setelahnya `script.yaml` berisi `tts: {locked: true}` — `tts` tidak akan membuat
ulang klip yang sudah ada.

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
