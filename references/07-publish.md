# 07 — Paket upload, caption & jadwal

| Platform | File | Catatan |
|----------|------|---------|
| YouTube Shorts, TikTok, IG Reels, FB Reels | `output/vertical/epXX_partN.mp4` | **file yang sama** di keempatnya; cover `epXX_partN_cover.jpg` (IG/FB: "Edit cover"; TikTok/Shorts: pilih frame/cover) |
| YouTube (video panjang) | `output/epXX.mp4`, `thumbnail/thumbnail_16x9.jpg`, `output/epXX.srt` (id) | judul = `youtube_title`; deskripsi dari `description.txt` (chapter = awal tiap part, 00:00 …) |
| Threads (opsional) | `output/threads/babN.md` + `images/` | ganti `[LINK YOUTUBE]` setelah video panjang tayang |

Upload IG/FB sebagai **Reels** (post video biasa di FB memotong 9:16 jadi 4:5). Di YouTube, isi "Related video"
tiap Short dengan part berikutnya; part terakhir → video panjang episode itu (setelah tayang).

## Jadwal mingguan (WIB) — 3 episode per minggu
Maksimal **2 upload part per hari**, jam **12:00 dan 19:00**, di keempat platform short-video sekaligus (file sama).

| Hari | 12:00 | 18:00 (YouTube, video panjang) | 19:00 |
|------|-------|-------|-------|
| Senin | Ep A Part 1 | | Ep A Part 2 |
| Selasa | Ep A Part 3 | | Ep A Part 4 |
| Rabu | Ep B Part 1 | **Ep A** | Ep B Part 2 |
| Kamis | Ep B Part 3 | | Ep B Part 4 |
| Jumat | Ep C Part 1 | **Ep B** | Ep C Part 2 |
| Sabtu | Ep C Part 3 | | Ep C Part 4 |
| Minggu | slot cadangan (part ke-4 / susulan) | **Ep C** | slot cadangan |

Aturan:
- Video panjang tiap episode tayang di YouTube jam **18:00 pada hari setelah part terakhirnya** (episode 3 part:
  part terakhir Selasa/Kamis/Sabtu 12:00, panjangnya tetap besok jam 18:00; slot 19:00 yang kosong boleh dipakai
  susulan).
- Kalau ada part yang tertunda, pakai slot Minggu; jangan pernah lebih dari 2 part per hari.
- **Satu file per slot.** Jangan pernah batch-upload beberapa part sekaligus; jadwalkan tiap part di slotnya
  (fitur jadwal platform boleh, tapi satu part per slot).
- Butuh 3 episode jadi per minggu: simpan minimal satu episode stok.
- Threads opsional (kalau dipakai: sesudah video panjang tayang, satu thread per part).

## Caption part (`output/vertical/captions.txt` → tulis ulang sendiri)
Dari isi part (jangan bocorkan akhir part/episode), 2–3 kalimat pendek, sudut pandang "aku": hook → kalimat
menggantung; lalu `🎧 <Judul> · Eps N · Part N/M`. Part terakhir: "Versi lengkap episode N ada di YouTube Kemenyan
Malam." (hanya di caption — video tidak punya kartu penutup). IG: `▶ link di bio`; FB/YouTube: `[LINK YOUTUBE]`.
Hashtag IG/TikTok: `#KemenyanMalam #JuruKunciWringinpitu #ceritahoror #horor #ceritahororjawa #kisahmistis
#horrorindonesia`; FB/Shorts: 3 tag pertama. Hindari gaya "lebay" (huruf kapital semua, banyak emoji).

## Threads (opsional)
Satu thread per part, post ≤ 480 karakter (emoji dihitung byte UTF-8), putus di batas kalimat. Post 1 = hook + 🧵 +
label "<Judul> · Eps N · Part N" + `thumbnail_16x9.jpg`; maks 2 gambar adegan 4:5 (`--thumb-only` tanpa gambar
adegan). Post terakhir: cliffhanger utuh + "Bersambung..." + "🎧 Versi lengkapnya ada di YouTube: [LINK YOUTUBE]"
+ satu topic tag `#KemenyanMalam`.
