# 04 — Lapisan suara

`stories/<slug>/sound_assets.yaml` memetakan nama aset → file Pixabay (cocok via ID numerik di nama file).
```bash
python horror.py sound-import <slug> <ep> <folder-upload>   # → assets/sound/<nama>.mp3, laporkan yang belum ada
```
Pemrosesan khusus otomatis: ambience di-loop mulus, kentongan dipola 3-3, humming di-pitch −2 st + reverb + lowpass.

`episodes/epXX/sound.yaml` (nilai yang sudah disetujui untuk ep01):
```yaml
music: {file: bgm_dark_ambient, vol: -18, duck_under_voice: -5, fade_in: 3, fade_out: 4,
        mute_on_beats: [b009, b020, b070]}
ambience:  # rentang beat inklusif, crossfade 1,5 s
  - {file: amb_night_village, from: b001, to: b008, vol: -14}
sfx:
  b008: {file: sfx_hit_big, at: end, vol: -6}      # at: start | end | detik dari awal beat
```
Aturan mix (otomatis di `build`):
- musik+ambience selalu ≥ 6 dB di bawah suara; beat yang melanggar dibatasi (dilaporkan di log, mis. "b013 −2.5")
- loudness akhir −14 LUFS, true peak ≤ −1.5 dBTP; intro/outro channel tidak kena musik cerita
- `review` mengukur jarak bed di jeda vs suara (target 12–26 dB)
Ubah level hanya atas permintaan user; laporkan level relatif suara sebelum/sesudah.
