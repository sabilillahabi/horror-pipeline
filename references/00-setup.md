# 00 — Setup (sekali per workspace)

## 1. Python + dependensi
```bash
cd $SKILL
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt          # PyYAML, Pillow, edge-tts, google-genai
ffmpeg -version && ffprobe -version     # wajib; build butuh ffmpeg dengan libass (subtitle) dan libx264
```
Kalau ffmpeg belum ada dan workspace mengizinkan: `apt-get install -y ffmpeg`.

## 2. Font (hasil harus sama dengan versi Windows sebisa mungkin)
`pipeline/fonts.py` memilih font per peran; di Linux butuh padanan bebas lisensi:
```bash
apt-get install -y fonts-liberation fonts-dejavu-core fontconfig   # Arial/Georgia → Liberation/DejaVu
mkdir -p assets/fonts
# PART N di cover (padanan Bahnschrift Bold Condensed): Oswald Bold, Google Fonts (OFL)
curl -L -o assets/fonts/Oswald-Bold.ttf "https://github.com/googlefonts/OswaldFont/raw/main/fonts/ttf/Oswald-Bold.ttf"
```
Cek: `python -c "from pipeline import fonts; print(fonts.report())"` — tidak boleh ada `None`.
Jangan menaruh font lain di root `assets/fonts/` tanpa alasan: file pertama di sana dipakai sebagai font judul.

## 3. API key Gemini (TTS)
Buat `$SKILL/.env` (jangan di-commit, jangan dicetak):
```
GEMINI_API_KEYS=key1,key2,key3
```
Free tier: ±10 request/hari per key/proyek. Pipeline merotasi key saat kuota harian habis dan berhenti dengan
pesan "Kuota harian habis di semua N key. Selesai X/Y, sisa Z beat" — jalankan `tts` lagi nanti (lihat 03).

## 4. Aset dari user (diunggah ke workspace)
| Aset | Cara masuk |
|------|-----------|
| Musik/SFX/ambience (Pixabay, sesuai `stories/<slug>/sound_assets.yaml`) | upload ke satu folder → `python horror.py sound-import <slug> <ep> <folder>` |
| Gambar beat dari Google Flow (zip/folder download) | `python horror.py import-flow <slug> <ep> <folder-atau-zip>` |
| Thumbnail `thumb_epXX_16x9` / `thumb_epXX_9x16` | ikut folder import-flow di atas |

`import-flow` dan `sound-import` tanpa argumen mencari di `~/Downloads` — di Muse selalu beri path folder.

## 5. Struktur
```
horror.py                    # CLI (python horror.py -h)
pipeline/                    # modul: tts, gemini_tts, sound, render, vertical, covers, threads, review, …
scripts/auto_tts.py          # retry TTS terjadwal (Windows Task Scheduler; di Muse jalankan tts manual)
channels/<channel>.yaml      # outro channel + struktur episode default
channels/<channel>/audio/    # outro.wav (dibuat sekali, dipakai semua episode)
stories/<slug>/story.yaml    # tokoh, voice Gemini, style_block, channel
stories/<slug>/episodes/epXX/{script,styles,sound,covers,threads}.yaml
```
