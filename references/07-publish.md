# 07 — Paket upload, caption & jadwal

| Platform | File | Catatan |
|----------|------|---------|
| YouTube Shorts, TikTok, IG Reels, FB Reels | `output/vertical/epXX_partN.mp4` | **file yang sama** di keempatnya; cover `epXX_partN_cover.jpg` (IG/FB: "Edit cover"; TikTok/Shorts: pilih frame/cover) |
| YouTube (video panjang) | `output/epXX.mp4`, `thumbnail/thumbnail_16x9.jpg`, `output/epXX.srt` (id) | judul = `youtube_title`; deskripsi dari `description.txt` (chapter = awal tiap part, 00:00 …) |
| Threads (opsional) | `output/threads/partN.md` + `images/` | diposting barengan Short part N; ganti `[LINK SHORTS PART N]` |

Upload IG/FB sebagai **Reels** (post video biasa di FB memotong 9:16 jadi 4:5). Di YouTube, isi "Related video"
tiap Short dengan part berikutnya; part terakhir → video panjang episode itu (setelah tayang).

## Jadwal mingguan (WIB) — 1 upload per hari (keputusan Bil, 28 Nov 2026)
Satu upload per hari supaya tiap video punya waktu cukup untuk didistribusikan dan ditonton. Part satu episode
tayang **berturut-turut** (tidak diselingi cerita lain) supaya rasa penasaran terbawa dari hari ke hari.

| Hari | Upload | Platform |
|------|--------|----------|
| Senin | Episode minggu ini · Part 1 | Shorts, TikTok, IG Reels, FB Reels |
| Selasa | Part 2 | idem |
| Rabu | Part 3 | idem |
| Kamis | Part 4 | idem |
| Jumat | Cerita sekali tamat #1 | idem |
| Sabtu | Cerita sekali tamat #2 | idem |
| Minggu | Video panjang episode minggu ini (16:9) | YouTube saja |

Aturan:
- Jam tayang: **19:00 WIB** untuk semua slot (default; Bil boleh mengganti jamnya, satu jam yang sama tiap hari).
- 1 episode cerita bersambung per minggu → jilid 4 episode selesai dalam 1 bulan.
- Episode yang cuma 3 part: Kamis diisi cerita sekali tamat tambahan atau dikosongkan; jangan pernah 2 upload sehari.
- **Satu file per slot.** Jangan batch-upload beberapa part sekaligus; pakai fitur jadwal platform, satu part per slot.
- Simpan minimal satu episode stok supaya jadwal tidak bolong.
- Format cerita sekali tamat masih dirancang (belum ada aturannya); sampai ada, slot Jumat/Sabtu boleh kosong.
- Threads opsional: satu thread per part, diposting di slot yang sama dengan Short part itu (lihat bawah).

## Judul & deskripsi per platform → `stories/<slug>/episodes/epXX/publish.md`
Tulis sendiri dari isi script (bukan dari `captions.txt` otomatis), satu file per episode, siap copy-paste: per part
satu blok per platform (YouTube Shorts, TikTok, IG Reels, FB Reels), lalu blok video panjang, jadwal, dan nama file cover.
Contoh jadi: `stories/juru-kunci/episodes/ep01/publish.md`.

**Aturan isi (semua platform)**
- Bahasa Indonesia santai, sudut pandang "aku". Tidak membocorkan cliffhanger part itu atau twist part sesudahnya
  (hook boleh dari tengah part). Tanpa huruf kapital semua, maks 1–2 emoji (🎧 ▶).
- Hook = situasi + rasa ganjil konkret ("menyisir rambut dengan sisir yang nggak ada"), bukan kata sifat kosong
  ("seram banget!").
- Label seri selalu ada: `🎧 <Judul> · Eps N · Part N/M`. Part terakhir: tambah "Versi lengkap Episode N ada di
  YouTube Kemenyan Malam."
- Hashtag lengkap (7): `#KemenyanMalam #JuruKunciWringinpitu #ceritahoror #horor #ceritahororjawa #kisahmistis
  #horrorindonesia` (ganti tag judul untuk cerita lain). Hashtag pendek (3) = tiga pertama.

**Per platform**
| | Judul | Deskripsi / caption | Link | Hashtag |
|---|---|---|---|---|
| YouTube Shorts | kolom judul, ≤ 70 huruf + ` #shorts` di akhir (maks 100) | 2–3 kalimat hook + label seri | **tanpa link** (tidak bisa diklik di Shorts) — pakai "Related video" ke part berikutnya, part terakhir → video panjang | 3 |
| TikTok | **tidak ada kolom judul**: baris pertama caption = judul (≤ 70 huruf) | baris kosong, 2–3 kalimat hook, label seri | tidak ada | 7 |
| IG Reels | **tidak ada kolom judul**: baris pertama caption = judul | baris kosong, hook, label seri, `▶ link di bio` | link di bio (caption tidak bisa diklik) | 7 |
| FB Reels | **tidak ada kolom judul**: baris pertama = judul | baris kosong, hook, label seri, `▶ [LINK YOUTUBE]` (bisa diklik) | link video panjang setelah tayang | 3 |
| YouTube (panjang) | `youtube_title` dari script.yaml (≤ 70 huruf terlihat penuh, maks 100) + 1 alternatif | 2 baris pertama = hook (yang terlihat sebelum "lainnya"), sinopsis 3–4 kalimat tanpa spoiler, "Juru Kunci · Episode N: <judul>", ajakan subscribe, **Chapter** (salin dari `output/description.txt`, mulai 00:00), hashtag | link part/Shorts boleh | 5 di deskripsi + 10–15 tag di kolom Tag |

Format judul part: `<hook singkat> | <Judul> Eps N Part N/M` (mis. "Perempuan di Gerbang Makam Menyisir Rambut |
Juru Kunci Eps 1 Part 1/4"). Tiap part judul berbeda; jangan "Part 2" saja.
`[LINK YOUTUBE]` di FB diganti setelah video panjang tayang (caption yang sudah terbit boleh diedit).

## Threads (opsional) — 1 thread per part, barengan dengan Short-nya
`python horror.py threads <slug> <ep>` (sesudah `build --vertical`) → `output/threads/part<N>.md` + `images/`.
- **Jumlah thread = jumlah part video** (3–4). Thread part N diposting **di slot yang sama dengan Short part N**
  (19:00), tepat setelah Short-nya tayang.
- Post 1 = hook + 🧵 + label "<Judul> · Eps N · Part N/M" + cover part (`epXX_partN_cover.jpg`, sama dengan Short).
  Maks 2 gambar adegan 4:5 (`--thumb-only` tanpa gambar adegan). Post ≤ 480 karakter (emoji = byte UTF-8), putus di
  batas kalimat, maks 15 post.
- Post terakhir: cliffhanger utuh + "Bersambung ke Part N+1..." + `🎧 Versi videonya: [LINK SHORTS PART N]` +
  `#KemenyanMalam`. Ganti `[LINK SHORTS PART N]` dengan link Short yang baru diupload (YouTube Shorts atau TikTok).
- Part terakhir: "Bersambung..." + link Short + "Versi lengkap Episode N tayang di YouTube Kemenyan Malam."
  (link video panjang bisa ditambahkan sebagai balasan setelah tayang).
