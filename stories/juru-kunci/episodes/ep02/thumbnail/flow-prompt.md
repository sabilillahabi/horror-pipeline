# Thumbnail ep02 — Flow prompt (rework, refs/11)

Alasan rework: thumbnail v3 (slab font, kepala kepotong di 16:9) tidak sesuai
references/11-thumbnails-and-folders.md. Bil perintahkan regenerate per refs/11
dengan contoh ep01 sebagai referensi.

## Aturan kunci (references/11)
- Dua gambar dari Flow: `thumb_ep02_16x9` + `thumb_ep02_9x16`, import via `import-flow`.
- Lampirkan contoh ep01 (`references/style/thumbnail_16x9_ep01.jpg` /
  `thumbnail_9x16_ep01.jpg`) sebagai referensi: "same title lettering, colors and
  layout as the reference; change only the background scene and the episode number".
- Tipografi (LOCKED): "JURU KUNCI" = **classic thick serif dengan bracketed serif
  (Cinzel/Trajan-like) — BUKAN condensed, BUKAN sans, BUKAN slab**; krem/ivory;
  dark red glow/outline di belakang huruf; huruf lebar dan tinggi, ±80–90% lebar
  frame di 9:16. "EPISODE N" = thick condensed sans, putih, soft shadow.
  Tidak ada teks lain (tanpa judul bab, jilid, "x/9", tagline, logo channel).
  Teks di atas area gelap supaya terbaca.
- Sebelum generate apa pun untuk episode ini, buat dulu collection Flow
  **"Juru Kunci - Eps 02"** dan simpan semua gambar episode itu di sana.
- `thumbnail_9x16.jpg` adalah sumber judul semua cover part — judulnya harus bersih,
  di latar gelap.

## Karakter — LOCKED (story.yaml, Bayu/narrator)
Salin kata per kata ke setiap prompt, jangan disingkat:
"Young Javanese Indonesian man, 25 years old, lean build, short neat black hair
slightly grown out, thin mustache stubble, calm but tired eyes, wearing a faded
dark navy flannel shirt over a grey t-shirt"
Ref sheet `characters/bayu.png` TIDAK ada di repo (di komputer Bil). b001.png adalah
satu-satunya referensi wajah yang ada — selalu lampirkan sebagai ingredient.
LESSON 2026-11-25: prompt thumbnail pertama hanya bilang "A Javanese man in a worn
dark blue shirt" tanpa character_block → Flow menggambar muka lain. Muka harus
ngikutin character_block + b001, bukan deskripsi bebas.

## Format judul — LOCKED (references/11, contoh ep01)
PER ASPEK BEDA — jangan samain:
- **16:9** (lihat ep01 thumbnail_16x9.jpg): "JURU KUNCI" DITUMPUK dua baris
  ("JURU" di atas "KUNCI"), huruf krem classic thick serif sangat besar dengan
  dark red glow, di SEPERTIGA KIRI, vertically centered (blok judul kira-kira
  y 25-75%); "EPISODE N" putih condensed di bawahnya DENGAN JARAK JELAS (bukan
  nempel di bawah KUNCI), centered terhadap judul. KOMPOSISI: MEDIUM SHOT —
  karakter di kanan, kepala + bahu kelihatan penuh dengan ruang di atas kepala
  (kepala JANGAN kepotong tepi atas), lingkungan (rumah kayu / kuburan) kelihatan
  di tengah. BUKAN close-up ketat, tangan JANGAN mendominasi frame.
- **9:16** (lihat ep01 thumbnail_9x16.jpg): "JURU KUNCI" SATU BARIS, huruf krem
  classic thick serif sangat besar dengan dark red glow, SELEBAR ATAS (hampir
  selebar gambar, ±80–90% lebar frame), posisi 10–20% dari atas, jarak aman ±8%
  dari tepi atas (JANGAN nempel tepi); "EPISODE N" putih condensed di bawahnya,
  RATA KIRI sejajar dengan huruf J dari JURU. Karakter di bawah garis judul,
  muka kelihatan penuh.
- Cover part ngikutin 9:16: judul SATU BARIS + "EPISODE N" + "PART N".
LESSON 2026-11-25: gua sempat pakai format numpuk 16:9 buat 9:16 juga — SALAH,
Bil yang nangkep ("format perpart beda"). Selalu cek thumbnail ep01 per aspek.

## Cara generate (disarankan)
Di Flow, buat dulu collection "Juru Kunci - Eps 02" di project "Juru Kunci".
Pakai gambar referensi: contoh ep01 (aspek yang sama) + `images/b001.png`
(laki-laki + tusuk konde) sebagai ingredient, lalu prompt di bawah. Tujuannya:
lettering/layout sama dengan ep01, hanya adegan latar + nomor episode yang beda,
tusuk konde kelihatan penuh.

## Prompt 16:9
Cinematic horror thumbnail, 16:9. Young Javanese Indonesian man, 25 years old, lean
build, short neat black hair slightly grown out, thin mustache stubble, calm but tired
eyes, wearing a faded dark navy flannel shirt over a grey t-shirt. MEDIUM SHOT: he is
on the right half, head and shoulders fully in frame with clear space above his head,
his face exactly like the reference image, somber, looking down at the ornate silver
hairpin with a floral filigree head held out in his open palm at chest level. The
hairpin is fully visible and sharply detailed, catching warm lamplight, but the hand
does NOT dominate the frame — the dim wooden house interior with warm oil lamp glow
and dark shadows stays visible in the center. Title text stacked on two lines in the
left third, clear of the hairpin: "JURU" above "KUNCI" in very large wide cream
classic thick serif letters with bracketed serifs, like Cinzel or Trajan, with a dark
red glow behind the letters, vertically centered, and below it with a clear gap
"EPISODE 2" in smaller white thick condensed sans letters, centered relative to the
title. The hairpin and hand are completely unobstructed by text. Dark background
behind the title text. Same title lettering, colors and layout as the reference
thumbnail; change only the background scene and the episode number. No other text.

## Prompt 9:16
Same scene and title style as the 16:9 version, vertical 9:16. Young Javanese
Indonesian man, 25 years old, lean build, short neat black hair slightly grown out,
thin mustache stubble, calm but tired eyes, wearing a faded dark navy flannel shirt
over a grey t-shirt, his face exactly like the reference image. Title "JURU KUNCI"
in ONE LINE in very large cream classic thick serif letters with bracketed serifs,
like Cinzel or Trajan, with a dark red glow behind the letters, spanning almost the
full width across the top, 10-20% from the top edge with a clear safe distance from
the edge, and below it "EPISODE 2" in smaller white thick condensed sans letters,
left-aligned with the J of JURU, on a dark background, clean and fully legible. The
man's face is below the title band, fully visible, and the silver hairpin in his open
palm fills the lower two thirds, the hairpin fully visible, not covered by any text.
Same title lettering, colors and layout as the reference thumbnail; change only the
background scene and the episode number. No other text.

## Setelah generate
- Download kedua thumbnail dari collection "Juru Kunci - Eps 02", simpan sebagai
  `thumb_ep02_16x9.jpg` + `thumb_ep02_9x16.jpg`, lalu
  `python horror.py import-flow juru-kunci 2 <folder>` (→ thumbnail/thumbnail_16x9.jpg
  1280x720 <2MB + thumbnail_9x16.jpg 1080x1920).
- Bandingkan berdampingan dengan contoh ep01 (huruf, posisi, warna) SEBELUM import
  — kalau beda, regenerate/edit di Flow dulu.
- Cover part HANYA via `python horror.py covers juru-kunci 2`, setelah part
  hasil rework selesai di-render.
- Upload thumbnail final ke Drive folder Kemenyan Malam/Juru Kunci/Eps 02/long/
  (struktur baru, refs/11).
