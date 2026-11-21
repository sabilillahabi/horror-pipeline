# 07 — Paket upload & caption

| Platform | File | Catatan |
|----------|------|---------|
| YouTube | `output/epXX.mp4`, `thumbnail/thumbnail_16x9.jpg`, `output/epXX.srt` (id) | judul = `youtube_title`; deskripsi dari `description.txt` (chapter 00:00 …) |
| TikTok | `output/vertical/epXX.mp4` | cover `thumbnail_9x16.jpg` |
| IG / FB | `output/vertical/epXX_partN.mp4` | upload sebagai **Reels**; cover pilih manual "Edit cover" → `epXX_partN_cover.jpg` |
| Threads | `output/threads/babN.md` + `images/` | ganti `[LINK YOUTUBE]` setelah video YouTube tayang |

Upload YouTube dulu — link-nya dipakai di Threads dan Facebook.

## Caption IG/FB per part (`output/vertical/captions_igfb.md`)
Tulis sendiri dari isi part (jangan bocorkan akhir part/episode), 3 paragraf pendek, sudut pandang "aku":
hook/adegan pembuka → perkembangan → kalimat menggantung; lalu `🎧 <Judul> · Eps N · Part N/M — lanjut ke Part N+1`.
Part terakhir: "tamat episode N. Episode N+1 tayang <jadwal dari kartu Bersambung>".
Penutup: IG `▶ Episode lengkap dengan narasi suara, musik, dan efek: link di bio` (link IG tidak bisa diklik);
FB `… : [LINK YOUTUBE]`.
Hashtag IG: `#KemenyanMalam #JuruKunciWringinpitu #ceritahoror #horor #ceritahororjawa #kisahmistis #horrorindonesia`;
FB: 3 tag pertama. Hindari gaya "lebay" (huruf kapital semua, banyak emoji).

## Threads
Satu thread per bab, post ≤ 480 karakter (emoji dihitung byte UTF-8), putus di batas kalimat. Post 1 = hook + 🧵 +
label "<Judul> · Eps N · Bab N" + `thumbnail_16x9.jpg` apa adanya; maks 2 gambar adegan 4:5 (`--thumb-only` tanpa
gambar adegan). Post terakhir: cliffhanger utuh + "Bersambung..." + "🎧 Versi lengkapnya ada di YouTube, dengan narasi
suara, musik, dan efek: [LINK YOUTUBE]" + satu topic tag `#KemenyanMalam`.

## Format 4:5 (feed biasa, bukan Reels)
Belum dibuat otomatis. Kalau user butuh, tawarkan render 1080x1350 dengan logika crop yang sama (±1,5 jam).
