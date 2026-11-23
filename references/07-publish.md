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

## Release strategy: Shorts first (since 23 Nov 2026)
The long videos weren't getting views on a new channel, so each episode is released as parts first and the long
video comes after all parts are out.
- Parts are the vertical IG/FB parts, used as-is for **YouTube Shorts, TikTok, IG Reels and FB Reels**.
- Every part must be **<= 2:55** including cards (YouTube Shorts max is 3:00). Re-split if needed; more parts is fine.
- Target part format: no opening card, the first 1-2 s are story audio/hook; small persistent label at the top
  "<Title> · Eps N · Part N/M"; end card "Lanjut ke Part N+1"; last part ends with "Versi lengkap ada di YouTube
  Kemenyan Malam" before the outro. If the current build still has the 1 s opening card, report it to Bil.
- On YouTube, set each Short's "Related video" to the next part; the last part -> the long episode.

### Weekly schedule (WIB), 2 episodes per week
| Day | 12:00 | 18:00 | 19:00 | 21:00 | 23:00 |
|-----|-------|-------|-------|-------|-------|
| Mon | Ep A Part 1 | | Ep A Part 2 | | |
| Tue | Ep A Part 3 | | Ep A Part 4 | | |
| Wed | Ep A Part 5 | | Ep A Part 6 | | |
| Thu | Ep B Part 1 | **Ep A long (YouTube)** | Ep B Part 2 + Threads Ep A Bab 1 | Threads Bab 2 | Threads Bab 3 |
| Fri | Ep B Part 3 | | Ep B Part 4 | | |
| Sat | Ep B Part 5 | | Ep B Part 6 | | |
| Sun | | **Ep B long (YouTube)** | Threads Ep B Bab 1 | Threads Bab 2 | Threads Bab 3 |
Shorts go to YouTube Shorts, TikTok, IG and FB at the same time. If an episode has 7+ parts, add a 16:00 slot.
Two finished episodes are needed every week, so keep at least one episode of stock.
