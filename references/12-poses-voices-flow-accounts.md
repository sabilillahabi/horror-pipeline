# 12 — Variasi pose, narator & tokoh, multi-akun Flow

Keputusan Bil, 28 Nov 2026. Berlaku untuk semua konten Kemenyan Malam (cerita bersambung dan cerita sekali tamat).

## A. Variasi pose (gambar lebih hidup, tanpa video Flow)
Video Flow berbayar: **tidak dipakai**. Gerak didapat dari beberapa gambar diam per adegan.

- Satu beat boleh punya **maksimal 4 gambar**: gambar dasar + sampai 3 pose.
  `script.yaml`: `poses: [b012, b012b, b012c, b012d]` (gambar dasar dulu; nama Flow `[b012b]`, dst.).
- **Pose = adegan yang sama**: framing kamera, latar, cahaya, kostum, dan tokoh sama. Yang berubah hanya gerak kecil
  yang sesuai narasi: kepala menoleh, tangan bergerak, mata membuka, api lampu condong, pintu sedikit lebih terbuka.
- Cara generate di Flow: buat gambar dasar dulu, lalu tiap pose dengan **gambar dasar dilampirkan sebagai
  referensi** + prompt: "same scene, same composition, same lighting and characters; only change: <gerak>".
- **Durasi adegan tetap mengikuti narasi.** Pose dibagi rata sesuai urutan dalam durasi beat; tiap pose minimal
  1,2 s (beat terlalu pendek → pakai lebih sedikit pose). Gerak kamera (push-in/pan) dihitung untuk seluruh beat,
  jadi tetap mulus melewati pergantian pose; pergantian pose = potong biasa atau dissolve 0,12 s.
- Dipakai untuk adegan tokoh yang ada aksi/emosi. Establishing shot dan benda cukup gerak kamera + efek.
- Jumlah: boleh lebih dari 30 gambar per episode. Patokan: ±25–30 adegan dasar, ±60–90 gambar total termasuk pose.
- QA: lembar kontak pose berdampingan per beat. Tolak pose yang wajah, pakaian, atau latarnya bergeser; generate
  ulang di akun Flow yang sama.

## B. Narator dan tokoh
- **Narator tidak selalu laki-laki.** Setiap cerita baru menentukan narator (laki-laki/perempuan) di `story.yaml`
  (`gemini_voices.narrator`). Cerita sekali tamat: dari 2 cerita per minggu, **minimal 1 bernarator perempuan**.
  Juru Kunci jilid 1 tetap narator laki-laki (Bayu).
- Voice narator perempuan pertama: Muse membuat sampel 1 paragraf dengan 3 kandidat Gemini (mis. Kore, Despina,
  Sulafat — voice yang belum dipakai tokoh lain di cerita itu) dan **Bil yang memilih**; pilihan dicatat di
  `channels/kemenyan-malam.yaml` (`narrator_voices.female`) supaya konsisten di semua cerita.
- **Tokoh tambahan boleh** di setiap konten. Batas supaya produksi dan kuota TTS tetap aman:
  cerita bersambung maks **6 peran bersuara per episode** (termasuk narator), cerita sekali tamat maks **4**.
  Tokoh tanpa dialog tidak dihitung.
- Tokoh baru = tambah di `story.yaml`: voice + style (Gemini, satu voice satu tokoh dalam satu cerita) dan satu
  gambar referensi karakter di style kit (C). Cek dulu katalog voice (03).
- Biaya waktu: narator perempuan tidak menambah waktu. Tiap tokoh bersuara tambahan menambah request TTS (beat
  tokoh berbeda tidak bisa digabung) — tetap gabungkan beat berurutan dari tokoh yang sama (03).

## C. Multi-akun Google Flow
Dipakai supaya kuota harian generate gambar tidak menghambat. Semua akun milik Bil; login ada di vault Muse.
Alamat email tidak ditulis di repo — akun disebut `flow1`…`flow4`.

**Style kit per cerita** (sumber kebenaran visual), di `stories/<slug>/style_kit/` (media di branch `muse-assets`):
- `refs/` — gambar referensi tiap tokoh dan 1–2 gambar gaya (file yang sama persis untuk semua akun).
- `style_kit.yaml` — awalan prompt gaya (teks persis), rasio 16:9, model/setting Flow yang dipakai, daftar tokoh →
  file ref, larangan (mis. tanpa teks di gambar).
- Sebelum generate pertama di sebuah akun: buat project `<Judul>` + collection episode (11), upload **semua** file
  `refs/` apa adanya. Jangan pernah membuat ulang ref per akun.

**Pembagian kerja** — dicatat di `episodes/epXX/flow_plan.yaml`:
- Bagi **per adegan, bukan per pose**: gambar dasar dan semua posenya selalu di akun yang sama.
- Isi `flow1` dulu sampai kena batas, lalu `flow2`, dst. Thumbnail selalu di `flow1`.
- Catat per akun per hari: jumlah gambar yang berhasil dan saat kena batas (supaya batas nyata diketahui).
- Nama file tetap `[bXXX]` / `[bXXXb]`, unik di seluruh episode, apa pun akunnya.

**Setelah download**: import semua zip dari semua akun (09), lalu kirim ke Bil **satu lembar kontak gabungan**:
gambar dikelompokkan per akun dengan ref style kit di sampingnya, plus lembar pose (A). Gambar yang gayanya melenceng
diulang di akun yang sama sebelum render.
