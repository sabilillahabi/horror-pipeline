# 03 — Narasi (Gemini TTS) + outro channel

```bash
python horror.py tts <slug> <ep>                    # resume: klip yang sudah ada tidak dibuat ulang
python horror.py tts <slug> <ep> --beats b008,b011  # tes beberapa beat (untuk minta OK voice/style)
python horror.py channel-tts <slug> <ep>            # outro channel (sekali per channel; --force untuk ulang)
```
- Model `gemini-3.8-flash-tts`; voice per tokoh dari `story.yaml`, style = style tokoh + `styles.yaml` beat.
- Voice tidak ada di katalog → pipeline berhenti dan menyarankan voice terdekat. Jangan mengganti diam-diam;
  tanyakan user.
- Efek phone/echo/whisper diterapkan setelah TTS (raw tersimpan di `audio/gemini/raw/`, ganti efek tidak butuh API).
- Kuota: rotasi otomatis antar key. Kalau semua habis, laporkan "selesai X/Y, sisa Z" ke user dan coba lagi
  nanti (kuota pulih bertahap dalam 24 jam). Di Muse tidak ada Task Scheduler — jadwalkan ulang `tts` kalau
  Muse punya fitur penjadwalan, atau minta user memicu lagi.
- `--engine edge` = edge-tts (cadangan offline/darurat, suara berbeda — hanya atas izin user).

## Outro channel (`channels/kemenyan-malam.yaml`)
Tagline dibisikkan voice Vindemiatrix, di layar hitam (tagline italic + "— Kemenyan Malam"), tidak masuk
subtitle. `channels/kemenyan-malam/audio/outro.wav` sudah ada di paket — jangan buat ulang tanpa alasan.
Struktur default channel: tanpa intro, tanpa kartu bab, cold open 0,5 s.
