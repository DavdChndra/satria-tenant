# Prompt Claude Code — UI SATRIA 2026 Tenant Registration (AILO)

Jalankan tiap **PART** di Claude Code secara berurutan (satu prompt = satu pesan). Tempel apa adanya. Setiap prompt sudah membawa design system lengkap supaya konsisten meski dikerjakan terpisah-pisah.

Design system yang dipakai di semua prompt:
- Warna: teal `#00809D` (primary), teal gelap `#02657D`, tint teal `#E6F2F4`, oranye `#F37121` (accent/CTA), oranye gelap `#D65E12`, hitam `#0A0A0A`, abu teks `#4A4F52`, latar `#F5F8F9`, garis `#DFE6E8`.
- Font: **Poppins** (400/500/600/700/800) via Google Fonts, satu-satunya font di seluruh aplikasi.
- Radius: 8px untuk input/tombol kecil, 14–20px untuk card/panel besar. Tombol utama pakai `border-radius: 999px` (pill).
- Gaya: bukan kartu SaaS generik dengan shadow abu-abu seragam — pakai garis solid `1.5px`, aksen oranye untuk elemen "unggulan"/CTA, motif garis putus (dashed) untuk elemen bergaya tiket (booth, ringkasan harga, tiket peserta).
- Wajib responsif penuh: breakpoint utama di 960px (grid 2 kolom) dan 720px (mobile, nav jadi burger menu, grid jadi 1 kolom, tombol full width).

---

## PART 0 — Setup Design System & Base Layout

```
Saya sedang membangun ulang UI untuk aplikasi Flask "SATRIA Tenant" (pendaftaran tenant/booth pameran). Stack: Flask 3.1 + Jinja2 + JS vanilla + CSS murni (tanpa framework CSS). Struktur project: app.py, templates/ (Jinja2), static/css/, static/js/.

Buatkan design system dasar dan base layout, dengan token berikut:

WARNA:
- --teal: #00809D
- --teal-dark: #02657D
- --teal-tint: #E6F2F4
- --orange: #F37121
- --orange-dark: #D65E12
- --ink: #0A0A0A
- --ink-soft: #4A4F52
- --paper: #FFFFFF
- --cloud: #F5F8F9
- --line: #DFE6E8

TIPOGRAFI: font Poppins (import dari Google Fonts, weight 400/500/600/700/800) untuk SELURUH teks di aplikasi, tanpa kecuali dan tanpa font fallback lain selain sans-serif system sebagai fallback teknis.

RADIUS & SPACING: radius kecil 8px (input, tombol biasa), radius besar 14–20px (card/panel), tombol utama pill (border-radius 999px). Gunakan CSS variables, bukan angka hardcoded berulang.

Tugas:
1. Buat file static/css/tokens.css berisi semua CSS variable warna, radius, shadow, dan @font-face/import Poppins, reset dasar (box-sizing, margin, font-family global).
2. Buat/perbarui templates/base.html sebagai layout dasar Jinja2 (blocks: title, content, extra_head, extra_scripts) yang meng-include tokens.css dan file static/css/style.css.
3. Buat komponen header (nav) dan footer sebagai partial Jinja2 terpisah (templates/partials/header.html dan footer.html) dengan gaya: header sticky, blur background saat discroll, logo + nama acara di kiri, menu nav di tengah/kanan, tombol CTA oranye pill "Daftar Tenant" di kanan. Di mobile (<720px) menu berubah jadi burger menu full-width dropdown.
4. Semua elemen harus responsif: breakpoint 960px dan 720px.
5. Jangan pakai shadow abu generik seragam di semua elemen — shadow hanya untuk elemen elevated seperti modal/summary card, itu pun warnanya condong ke warna brand (teal/hitam transparan), bukan abu netral.

Jangan tanya balik, langsung buat file-filenya dan tunjukkan hasilnya.
```

---

## PART 1 — Landing Page (Halaman Utama `/`)

```
Lanjutkan di project SATRIA Tenant yang sama (Flask + Jinja2), pakai design system dan base.html yang sudah dibuat di step sebelumnya (token warna teal #00809D, oranye #F37121, hitam #0A0A0A, font Poppins).

Buat/perbarui templates/index.html untuk halaman utama publik (route GET /), dengan section berikut, top to bottom:

1. HERO: dua kolom (kiri: kicker badge "Pendaftaran dibuka", headline besar dengan satu kata di-highlight warna teal, paragraf singkat, dua tombol — tombol utama oranye pill "Mulai pendaftaran" mengarah ke #daftar, tombol outline hitam "Lihat paket booth" mengarah ke #booth — lalu baris statistik kecil seperti jumlah tenant terdaftar. Kanan: card gelap (background hitam) berisi detail acara — venue, tanggal, jam operasional, batas pendaftaran, metode bayar — data ini ambil dari variabel Jinja `event_info` (venue, event_date, dst sesuai model EventInfo di models.py).

2. INFO ACARA tambahan (opsional galeri foto dan pembicara) jika context Jinja `gallery_photos` dan `speakers` tersedia — render sebagai carousel/grid horizontal scroll di mobile.

3. BOOTH TYPES (id="booth"): grid 3 kolom (2 kolom di tablet, 1 kolom di mobile) me-render `booth_types` dari context Jinja. Tiap card: nama booth, harga besar warna teal-dark, indikator kuota tersisa (dot kecil, warna oranye kalau slot_remaining < 20% dari quota), daftar fitur singkat dari description, tombol pilih. Booth dengan quota/sisa slot terbanyak terjual (paling laris) diberi border oranye dan badge "Paling laris" — tentukan ini di template dengan flag Jinja, bukan hardcode.

4. Section pendaftaran (id="daftar") hanya berupa CTA singkat yang mengarah/scroll ke form registrasi (form aktualnya dibuat di prompt terpisah).

Style: pakai warna dan font sesuai design system. Section hero pakai gradient halus dari teal-tint ke putih. Section booth pakai card dengan border solid 1.5px, hover mengangkat card (translateY) dan border berubah teal. Pastikan seluruh halaman responsif sampai lebar 360px, teks tidak overflow, dan grid berubah jadi 1 kolom di mobile.

Jangan tanya balik, langsung implementasikan.
```

---

## PART 1B — Ganti Landing Page ke Gaya "Event Summit" (semua isi diatur dari admin)

Pakai ini kalau kamu mau landing page bergaya AWS Summit (hero besar → pembicara → sorotan acara → keynote → agenda → alasan hadir → CTA), dan SEMUA kontennya bisa diubah dari panel admin tanpa edit kode. Ini menggantikan struktur section 1–2 di PART 1 (booth grid tetap dipakai, cukup dipindah ke bawah agenda).

Karena model `EventInfo` yang ada di models.py saat ini cuma menyimpan venue/tanggal/maps/hero/catatan, prompt ini juga MENAMBAH struktur data baru di MongoEngine supaya section "Sorotan acara", "Agenda/jadwal", dan "Alasan hadir" jadi punya daftar item yang bisa ditambah/hapus/urutkan dari admin — persis seperti Speakers dan GalleryPhotos yang sudah ada.

```
Lanjutkan di project SATRIA Tenant (Flask + MongoEngine + Jinja2), pakai design system yang sudah ada (teal #00809D, oranye #F37121, hitam #0A0A0A, font Poppins).

TUJUAN: ubah templates/index.html jadi landing page bergaya "event summit" dengan urutan section berikut, dan pastikan SEMUA teks/gambar di dalamnya berasal dari database (context Jinja), bukan hardcode, supaya bisa diatur dari panel admin.

1. TAMBAH MODEL BARU di models.py (MongoEngine), mengikuti pola BoothType/Speaker yang sudah ada:
   - `HighlightItem`: title (string, wajib), description (string, wajib), image (string path, opsional), sort_order (int), is_active (boolean).
   - `AgendaItem`: time_label (string, cth "09.30"), activity (string), sort_order (int).
   - `ReasonItem`: title (string), description (string), sort_order (int).
   - `KeynoteSection`: title (string), body (string panjang), embedded/singleton mengikuti pola EventInfo (satu dokumen saja).
   Tambahkan field baru di `EventInfo` yang belum ada: `hero_video_url` (opsional, string), `subtitle` (string pendek untuk sub-headline hero), `intro_title` dan `intro_body` (untuk section "Hadiri acara ini").

2. TAMBAH ROUTE ADMIN untuk kelola data baru ini, mengikuti pola endpoint booth/addon yang sudah ada (form POST biasa, bukan JSON):
   - `/admin/highlight/new`, `/admin/highlight/<id>/update`, `/admin/highlight/<id>/delete`
   - `/admin/agenda/new`, `/admin/agenda/<id>/update`, `/admin/agenda/<id>/delete`
   - `/admin/reason/new`, `/admin/reason/<id>/update`, `/admin/reason/<id>/delete`
   - `/admin/keynote/update` (update singleton)
   - Perluas route `/admin/event` yang sudah ada supaya menerima field baru EventInfo di atas.
   Semua route ini pakai decorator `admin_required` yang sudah ada.

3. BUAT UI ADMIN untuk kelola konten ini: tambahkan section baru di templates/admin/content.html (atau buat templates/admin/site-settings.html kalau lebih rapi) dengan pola yang SAMA seperti kelola galeri foto/pembicara yang sudah ada — list item existing (bisa diedit inline atau lewat modal, drag/atau input angka untuk sort_order, toggle is_active kalau ada), form tambah item baru di bagian bawah tiap list, dan tombol hapus dengan konfirmasi. Kelompokkan jadi tab atau section berlabel jelas: "Hero & Intro", "Sorotan Acara", "Sesi Keynote", "Agenda", "Alasan Hadir".

4. BANGUN ULANG templates/index.html dengan urutan section berikut, SEMUA datanya diambil dari context Jinja (event_info, speakers, highlight_items, keynote_section, agenda_items, reason_items, booth_types):

   a. HERO full-width tinggi (min-height besar): background gradasi gelap dengan aksen teal dan oranye (atau video dari event_info.hero_video_url kalau ada, fallback ke gradient), breadcrumb kecil, judul acara besar, subtitle (tanggal + venue dari event_info), dua tombol CTA (oranye solid "Daftar sebagai tenant" scroll ke #daftar, outline putih "Lihat agenda" scroll ke #agenda).
   b. SUB NAVIGASI horizontal tepat di bawah hero, background hitam, link ke Beranda/Agenda/Paket Booth/FAQ/Daftar, item aktif digarisbawahi oranye.
   c. INTRO dua kolom: kiri judul + 1-2 paragraf dari event_info.intro_title/intro_body, kanan video/thumbnail placeholder dengan tombol play bulat.
   d. PEMBICARA: grid render dari `speakers`, 4 kolom desktop, foto persegi rounded, nama, institusi+topik di bawahnya.
   e. SOROTAN ACARA: grid render dari `highlight_items` (urutkan by sort_order, filter is_active), card dengan gambar/placeholder warna gradient teal-oranye di atas, judul dan deskripsi di bawah.
   f. KEYNOTE: section full-width background hitam, judul dan body dari `keynote_section`, tombol CTA oranye.
   g. AGENDA (id="agenda"): dua kolom — kiri judul tanggal acara + paragraf ekspektasi, kanan timeline vertikal render dari `agenda_items` (urutkan by sort_order), tiap baris waktu (bold, warna teal-dark) + aktivitas, dipisah garis putus horizontal.
   h. PAKET BOOTH (id="booth"): pindahkan grid booth_types yang sudah dibuat sebelumnya ke sini, style tetap sama seperti PART 1.
   i. ALASAN HADIR: grid 3 kolom render dari `reason_items`, tiap card ada angka urut kecil dalam kotak rounded warna teal-tint, judul, deskripsi.
   j. CTA STRIP terakhir: background teal-tint, 3 kartu kecil putih ("Daftar sebagai tenant" → #daftar, "Cek status pendaftaran" → halaman status, "Punya pertanyaan?" → FAQ kalau ada).

5. Update fungsi seed_defaults() di app.py/models.py supaya membuat beberapa contoh HighlightItem, AgendaItem, ReasonItem, dan satu KeynoteSection default kalau koleksinya masih kosong — supaya halaman tidak kosong saat pertama kali dijalankan.

6. Wajib responsif: di layar <960px, grid pembicara dan sorotan jadi 2 kolom, alasan hadir jadi 1 kolom, agenda jadi 1 kolom (timeline di bawah teks). Di layar <600px, semua grid jadi 1 kolom, tombol hero full width dan stack vertikal, timeline item jadi stack (waktu di atas, aktivitas di bawah).

Langsung implementasikan semuanya tanpa bertanya balik — termasuk perubahan models.py, route baru, template admin, dan template index.html.
```

---

## PART 2 — Form Pendaftaran Multi-Step (bagian dari `/`, submit ke `POST /api/register`)

```
Masih di project SATRIA Tenant yang sama, lanjutkan section pendaftaran di templates/index.html (atau pisahkan ke templates/partials/registration_form.html lalu include).

Buat form pendaftaran tenant BERTAHAP (3 langkah, ditampilkan sebagai stepper horizontal di atas form dengan background gelap #0A0A0A: langkah 1 "Data institusi", langkah 2 "Pilih add-on", langkah 3 "Pembayaran". Step aktif berwarna teal-dark dengan angka bulat oranye, step selesai bertanda centang dengan angka bulat teal, step belum aktif transparan/redup).

Field form (semua wajib kecuali disebut opsional), sesuai field model Tenant di models.py:
- institution_name (nama institusi, teks, max 200)
- pic_name (nama PIC, teks, max 150)
- email (email, validasi format)
- phone (nomor WhatsApp, teks, max 30)
- booth_type_id (dipilih dari section booth di atas, bukan input manual — tampilkan sebagai ringkasan booth terpilih yang bisa diganti)
- description (textarea, max 2000 karakter, tampilkan counter karakter sisa)
- add_on_ids: render dari context Jinja `add_ons` sebagai daftar checkbox custom (bukan checkbox HTML default) — tiap baris addon punya nama, deskripsi singkat, harga di kanan, dan checkbox kotak bulat kecil yang berubah warna teal + background teal-tint saat dicentang.

Di bagian bawah, tampilkan RINGKASAN HARGA sebagai box gelap (background #0A0A0A, teks putih): baris harga booth terpilih, baris tiap add-on terpilih, garis putus (dashed) sebelum baris TOTAL yang dicetak tebal dengan angka total berwarna oranye. Ringkasan ini harus update otomatis via JavaScript vanilla setiap ada perubahan pilihan booth/add-on (buat/perbarui static/js/register.js untuk logic ini, hitung total = harga booth + jumlah harga add-on terpilih, format ke Rupiah dengan pemisah ribuan).

Validasi sisi client: tampilkan pesan error inline berwarna oranye-gelap di bawah field yang invalid (bukan alert browser), sebelum submit ke POST /api/register.

Setelah submit sukses (backend mengembalikan snap_token), panggil Snap.js (`snap.pay(snap_token, {...})`) sesuai dokumentasi Midtrans yang sudah ada di app — TIDAK PERLU membuat ulang logic backend, cukup pastikan hook JS untuk trigger Snap sudah terpasang di register.js.

Tombol navigasi antar step: "Lanjut" (oranye pill) dan "Kembali" (link teks abu-abu, tanpa border) di footer form dengan background --cloud dan border-top tipis.

Wajib responsif: di layar <720px, field grid 2 kolom berubah jadi 1 kolom, stepper bisa wrap jadi 2 baris, tombol navigasi jadi full-width dan stack vertikal (tombol lanjut di atas, kembali di bawah, center text).

Langsung implementasikan tanpa bertanya balik.
```

---

## PART 3 — Halaman Status Pendaftaran (`/status/<order_id>`)

```
Di project SATRIA Tenant yang sama, buat/perbarui templates/status.html untuk route GET /status/<order_id>, memakai design system (teal #00809D, oranye #F37121, hitam #0A0A0A, font Poppins) dan base.html yang sudah ada.

Halaman ini harus menampilkan status pendaftaran tenant (variabel Jinja `tenant`) dengan tampilan BERBEDA per payment_status:

- pending: card dengan aksen oranye, ikon jam, teks "Menunggu pembayaran", tombol pill oranye "Lanjutkan pembayaran" yang memanggil POST /api/pay/<order_id> lalu buka Snap.js, dan tombol sekunder outline untuk cek ulang status via POST /api/payment/<order_id>/confirm (tampilkan spinner kecil saat proses cek, lalu reload/redirect otomatis ke /ticket/<order_id> kalau hasilnya paid).
- paid: card dengan aksen teal, ikon centang, teks "Pembayaran berhasil", tombol pill teal "Lihat tiket peserta" mengarah ke /ticket/<order_id>.
- expired / cancelled / failed: card netral dengan border merah-oranye tipis, ikon silang, teks status jelas ("Pembayaran kedaluwarsa" / "Dibatalkan" / "Gagal"), dan tombol outline hitam "Daftar ulang" mengarah ke halaman utama.
- refunded: card teal muda, teks "Dana telah dikembalikan".

Di bawah status utama, tampilkan ringkasan pendaftaran: order_id (dengan tombol salin ke clipboard kecil di sampingnya), nama institusi, nama PIC, jenis booth, daftar add-on, dan total_amount (format Rupiah).

Layout: card status di tengah halaman, max-width sekitar 560px, latar halaman warna --cloud, card sendiri putih dengan radius besar dan border sesuai warna status. Responsif penuh sampai 360px — card padding menyesuaikan, tombol full width di mobile.

Buat juga logic polling ringan di static/js/status.js: kalau status pending, cek ulang otomatis tiap beberapa detik sampai berubah (tanpa reload penuh halaman, update DOM saja), maksimal beberapa kali percobaan lalu berhenti otomatis supaya tidak spam request.

Langsung implementasikan tanpa bertanya balik.
```

---

## PART 4 — Kartu Peserta / Tiket (`/ticket/<order_id>`)

```
Di project SATRIA Tenant yang sama, buat/perbarui templates/ticket.html untuk route GET /ticket/<order_id>, hanya bisa diakses tenant dengan payment_status paid, memakai design system yang sama.

Desain tiket bergaya kartu event fisik/boarding-pass, BUKAN card generik:
- Bentuk kartu horizontal (di desktop) dengan dua bagian dipisah garis putus vertikal bergaya sobekan tiket: bagian kiri lebih lebar berisi info (nama institusi, nama PIC, jenis booth, order_id), bagian kanan sempit berwarna teal solid berisi QR code besar (dari endpoint GET /ticket/<order_id>/qr.svg, di-embed via <img>) dan label "Tunjukkan QR ini saat check-in".
- Beri "notch" visual di titik sobekan (dua setengah lingkaran kecil warna latar halaman menempel di tepi atas dan bawah garis pemisah) untuk kesan tiket sungguhan.
- Header kartu memakai warna hitam solid dengan nama acara "SATRIA 2026" dan tanggal acara.
- Tampilkan status "Sudah check-in" (badge teal) atau "Belum check-in" (badge oranye pudar) berdasarkan variabel Jinja checked_in_at.
- Sertakan tombol "Unduh sebagai gambar" dan "Cetak" (window.print) di bawah kartu — sembunyikan tombol-tombol ini saat mode print via CSS @media print.

Responsif: di layar <720px, kartu berubah jadi vertikal (info di atas, QR + label di bawah, garis pemisah horizontal, bukan vertikal), tetap dengan notch visual di kiri-kanan garis pemisah.

Langsung implementasikan tanpa bertanya balik.
```

---

## PART 5 — Admin: Login (`/admin/login`)

```
Di project SATRIA Tenant yang sama, buat/perbarui templates/admin/login.html untuk route GET/POST /admin/login, memakai design system yang sama (teal #00809D, oranye #F37121, hitam #0A0A0A, Poppins).

Layout: halaman full-height, dibagi dua kolom di desktop — kolom kiri panel gelap (background #0A0A0A) berisi logo/nama acara dan satu kalimat singkat tentang panel admin panitia SATRIA, kolom kanan form login di atas background putih/--cloud, terpusat vertikal. Di mobile, kolom kiri disembunyikan atau diciutkan jadi header pendek di atas form saja.

Form: field username, field password (dengan tombol show/hide password ikon mata sederhana pakai SVG/emoji, tanpa library eksternal), tombol submit pill oranye penuh lebar "Masuk". Tampilkan area untuk pesan error (login gagal) sebagai banner tipis warna oranye-gelap di atas form, hanya muncul kalau ada context Jinja error/flash message.

Jangan tambahkan elemen "lupa password" karena sistem ini tidak punya fitur reset password mandiri.

Langsung implementasikan tanpa bertanya balik.
```

---

## PART 6 — Admin: Shell Dashboard & Navigasi (`/admin`)

```
Di project SATRIA Tenant yang sama, buat templates/admin/base.html sebagai layout khusus area admin (extend dari base.html utama atau berdiri sendiri), dipakai oleh semua halaman /admin/*, dengan design system yang sama.

Layout: sidebar kiri tetap (fixed) lebar sekitar 260px, background hitam #0A0A0A, berisi: logo kecil + nama acara di atas, lalu daftar menu navigasi admin (Dashboard, Booth & Add-on, Konten Acara, Galeri & Pembicara, Pendaftar/Tenant, Broadcast Email, Scan Check-in, Pengaturan Akun), item menu aktif diberi background teal-dark dengan garis aksen oranye tipis di sisi kiri. Di bagian bawah sidebar: nama admin yang login + tombol logout kecil.

Konten utama di kanan sidebar (margin-left sesuai lebar sidebar), dengan topbar berisi judul halaman dan breadcrumb sederhana.

Buat templates/admin/dashboard.html sebagai halaman GET /admin: tampilkan grid kartu ringkasan statistik (total tenant, total lunas, total pending, total pendapatan terkumpul) dengan angka besar warna teal-dark dan label kecil abu-abu, lalu di bawahnya tabel ringkas 5-10 pendaftar terbaru (nama institusi, booth, status berupa badge berwarna sesuai status: paid=teal, pending=oranye, expired/cancelled/failed=abu gelap, refunded=teal muda).

Responsif: di layar <960px, sidebar berubah jadi bisa di-toggle (hamburger di topbar membuka sidebar sebagai drawer overlay dari kiri, dengan latar gelap transparan menutupi konten saat sidebar terbuka). Buat logic toggle ini di static/js/admin.js.

Langsung implementasikan tanpa bertanya balik.
```

---

## PART 7 — Admin: Kelola Booth & Add-on

```
Di project SATRIA Tenant yang sama, buat templates/admin/booth.html untuk kelola booth_types dan add_ons (route terkait: POST /admin/booth/new, /admin/booth/<id>/update, /admin/addon/new, /admin/addon/<id>/update), extend dari templates/admin/base.html, pakai design system yang sama.

Layout: dua section dalam satu halaman (atau dua tab dengan underline oranye untuk tab aktif) — "Jenis Booth" dan "Add-on".

Tiap section: tabel/list card berisi item existing (name, price format Rupiah, quota, is_active sebagai toggle switch kecil warna teal saat aktif, sort_order sebagai input angka kecil, tombol edit ikon pensil), lalu form tambah item baru dalam card terpisah di atas atau modal overlay yang muncul saat klik tombol pill oranye "+ Tambah booth baru" / "+ Tambah add-on baru".

Form tambah/edit: field name, description (textarea singkat), price (input angka dengan prefix "Rp"), quota (khusus booth), is_active (toggle), sort_order. Validasi client: price dan quota tidak boleh negatif (tampilkan pesan error oranye-gelap inline jika user mencoba input negatif).

Toggle switch is_active: buat sebagai custom toggle (bukan checkbox default) — pill kecil dengan lingkaran geser, warna abu saat nonaktif dan teal saat aktif, dengan transisi halus.

Responsif: di mobile, tabel berubah jadi stack card per item (bukan tabel horizontal scroll yang menyulitkan).

Langsung implementasikan tanpa bertanya balik.
```

---

## PART 8 — Admin: Konten Acara, Galeri & Pembicara

```
Di project SATRIA Tenant yang sama, buat templates/admin/content.html untuk kelola event_info, gallery_photos, dan speakers (routes: POST /admin/event, /admin/photo/upload + update/delete, /admin/speaker/new + update/delete), extend templates/admin/base.html, design system yang sama.

Bagi halaman jadi 3 section vertikal dengan pembatas jelas (bukan sekadar spasi kosong — pakai judul section dengan garis bawah tipis warna --line):

1. Info Acara: form venue, tanggal, link maps, judul pembicara, catatan acara, dan area upload hero image (dropzone dengan border dashed teal, menampilkan preview gambar yang sudah ada, tombol ganti gambar).

2. Galeri Foto: grid thumbnail foto existing (caption di bawah tiap thumbnail, toggle aktif/nonaktif kecil di pojok, tombol hapus ikon silang muncul saat hover), plus dropzone upload foto baru di akhir grid bergaya "+" besar pada card kosong dengan border dashed.

3. Pembicara: list card horizontal (foto kecil bulat di kiri, nama+institusi+topik di tengah, tombol edit/hapus di kanan), form tambah pembicara baru (nama, institusi, topik, upload foto) dalam card terpisah atau modal.

Semua area upload gambar validasi client-side untuk ekstensi JPG/JPEG/PNG/WEBP/GIF dan ukuran maksimum 5MB, tampilkan pesan error oranye-gelap jika tidak sesuai SEBELUM submit ke server.

Responsif: grid galeri dari 4 kolom (desktop) → 2 kolom (tablet) → 1 kolom (mobile).

Langsung implementasikan tanpa bertanya balik.
```

---

## PART 9 — Admin: Daftar Tenant, Ekspor CSV & Broadcast Email

```
Di project SATRIA Tenant yang sama, buat templates/admin/tenants.html (untuk manajemen tenant + link ke GET /admin/tenants/export.csv) dan templates/admin/broadcast.html (untuk POST /admin/broadcast), extend templates/admin/base.html, design system yang sama.

HALAMAN TENANT:
- Toolbar atas: search input (cari nama institusi/PIC/email), filter dropdown status (semua/pending/paid/expired/cancelled/failed/refunded), filter dropdown booth type, dan tombol pill teal "Ekspor CSV" di kanan yang mengarah ke /admin/tenants/export.csv.
- Tabel data tenant: order_id (font monospace kecil khusus kolom ini saja, bukan di seluruh halaman), institution_name, booth_type, total_amount (format Rupiah), payment_status (badge warna sesuai status: paid=teal, pending=oranye, gagal/batal/expired=abu-hitam, refunded=teal muda), checked_in_at (badge kecil "Sudah check-in" teal atau "-"), dan kolom aksi (tombol ubah status via dropdown kecil, tombol hapus ikon tempat sampah dengan konfirmasi modal sebelum submit).
- Tabel harus scrollable horizontal di mobile dengan indikator visual bisa discroll (bayangan tipis di tepi kanan), bukan tabel yang overflow tersembunyi begitu saja.

HALAMAN BROADCAST:
- Form: subject (input teks), body (textarea besar, minimal 8 baris), audience (radio button custom bergaya pill — pilihan: Semua, Sudah Lunas, Belum Lunas, Pilihan Manual). Kalau "Pilihan Manual" dipilih, tampilkan daftar checkbox tenant dengan search filter di atasnya.
- Setelah submit, tampilkan ringkasan hasil (jumlah penerima/terkirim/gagal) sebagai tiga angka besar berdampingan dengan warna teal (terkirim) dan oranye-gelap (gagal).
- Riwayat broadcast sebelumnya ditampilkan sebagai list di bawah form (subject, audience, waktu, ringkasan hasil).

Langsung implementasikan tanpa bertanya balik.
```

---

## PART 10 — Admin: Scan Check-in (`/admin/scan`)

```
Di project SATRIA Tenant yang sama, buat templates/admin/scan.html untuk route GET /admin/scan (kirim JSON ke POST /admin/scan/verify, reset via POST /admin/scan/reset/<tenant_id>), extend templates/admin/base.html, design system yang sama. Gunakan library jsQR yang sudah ada di project untuk baca QR dari kamera.

Layout: dua kolom di desktop — kolom kiri area kamera (video feed dalam frame bulat/rounded besar dengan border teal 3px dan sudut-sudut penanda seperti frame scanner QR sungguhan di keempat sudutnya), tombol mulai/berhenti kamera di bawahnya. Kolom kanan panel hasil scan: kondisi kosong (belum ada scan) tampilkan ikon dan teks "Arahkan kamera ke QR peserta", kondisi hasil valid tampilkan card besar hijau-teal dengan nama institusi, PIC, booth, dan status "Check-in berhasil", kondisi "repeat" (sudah pernah check-in) tampilkan card oranye dengan teks "Sudah check-in sebelumnya" beserta waktu check-in pertama, kondisi invalid/tenant belum lunas tampilkan card abu-gelap dengan pesan jelas.

PENTING keamanan: hasil scan dari server HARUS dirender pakai textContent/DOM API atau template Jinja escaping, JANGAN pakai innerHTML dengan data mentah dari server (ini exploit XSS yang sudah tercatat sebagai risiko di dokumentasi teknis proyek — pastikan diperbaiki di implementasi JS baru ini).

Di bawah panel hasil, tampilkan daftar riwayat check-in terakhir (nama institusi, waktu, tombol kecil "Batalkan check-in" yang memanggil POST /admin/scan/reset/<tenant_id> dengan modal konfirmasi sebelum submit).

Responsif: di mobile, kolom kamera dan panel hasil jadi stack vertikal (kamera di atas, hasil di bawah, riwayat check-in di paling bawah, bisa di-collapse/expand supaya tidak menutupi area kamera).

Langsung implementasikan tanpa bertanya balik.
```

---

## PART 11 — Pass Terakhir: QA Responsif & Konsistensi

```
Ini pass terakhir untuk project SATRIA Tenant yang sama. Tolong review ulang SEMUA halaman yang sudah dibuat di templates/ (index.html, status.html, ticket.html, admin/*.html) dan pastikan:

1. Konsistensi token: seluruh warna, radius, dan font Poppins benar-benar diambil dari static/css/tokens.css, tidak ada warna hardcoded baru yang menyimpang dari palet teal #00809D / oranye #F37121 / hitam #0A0A0A.
2. Responsif nyata sampai lebar 360px: cek tidak ada elemen overflow horizontal, teks terlalu kecil, atau tombol terlalu rapat untuk disentuh (minimum target sentuh 44x44px untuk semua tombol dan link penting).
3. Aksesibilitas dasar: semua input punya label yang terhubung (for/id), tombol punya teks yang jelas (bukan cuma ikon tanpa aria-label), fokus keyboard terlihat jelas (outline visible saat tab, bukan dihilangkan dengan outline:none tanpa pengganti).
4. Motion: hanya ada transisi halus pada hover/interaksi (bukan animasi fade-in massal di semua section saat load halaman) supaya halaman terasa cepat dan tidak norak.
5. Jalankan cek visual singkat kalau environment mendukung screenshot/browser preview, dan laporkan bagian mana saja yang masih perlu diperbaiki.

Perbaiki langsung semua yang ditemukan, lalu berikan ringkasan singkat perubahan apa saja yang dilakukan di pass ini.
```
