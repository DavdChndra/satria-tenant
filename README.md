# SATRIA 2026 — Pendaftaran Tenant Pameran

Aplikasi pendaftaran booth pameran dengan pembayaran terintegrasi Midtrans Snap,
plus panel admin untuk memantau pendaftaran dan mengatur harga/kuota booth.

## Struktur

```
satria-tenant/
├── app.py                  # routing utama (publik + admin)
├── models.py                # model MongoDB/MongoEngine (BoothType, Tenant, AdminUser)
├── migrate_to_mongo.py       # migrasi data satu kali dari satria.db (SQLite lama) ke MongoDB
├── midtrans_service.py      # wrapper Midtrans Snap + verifikasi webhook
├── templates/
│   ├── base.html
│   ├── index.html            # form pendaftaran publik
│   ├── status.html           # halaman status setelah bayar
│   └── admin/
│       ├── login.html
│       └── dashboard.html    # daftar pendaftaran + pengaturan booth
├── static/css/style.css
├── static/js/register.js     # submit form -> panggil Snap.js
├── requirements.txt
└── .env.example
```

## Setup lokal

```bash
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# edit .env, isi MONGODB_URI (MongoDB Atlas), MIDTRANS_SERVER_KEY, dan MIDTRANS_CLIENT_KEY

python app.py
# buka http://localhost:5000
```

### Koneksi MongoDB Atlas

1. Buat cluster gratis di [MongoDB Atlas](https://www.mongodb.com/cloud/atlas)
2. Di **Network Access**, izinkan IP komputer/server Anda (atau `0.0.0.0/0` untuk testing)
3. Di **Database Access**, buat database user beserta passwordnya
4. Di **Database > Connect > Drivers**, salin connection string-nya ke `MONGODB_URI` di `.env`
   (bentuknya `mongodb+srv://user:password@cluster.mongodb.net/satria?retryWrites=true&w=majority`)

Koleksi MongoDB otomatis dibuat saat pertama kali dijalankan, lengkap
dengan 2 jenis booth contoh dan 1 akun admin default:

- **Username:** `admin`
- **Password:** `ubah-password-ini`

**Ganti password ini sebelum publish.** Cara cepat lewat Python shell:

```bash
python -c "
import app
from models import AdminUser
from werkzeug.security import generate_password_hash
u = AdminUser.objects(username='admin').first()
u.password_hash = generate_password_hash('password-baru-yang-kuat')
u.save()
"
```

### Migrasi data lama dari SQLite

Jika sebelumnya pernah memakai versi SQLite (`satria.db`) aplikasi ini, jalankan
sekali setelah `MONGODB_URI` terisi dan bisa dikoneksi:

```bash
python migrate_to_mongo.py
```

Script ini membaca `satria.db` dan menyalin seluruh data (pendaftar, jenis booth,
opsi tambahan, dll) ke MongoDB. Aman dijalankan di database Mongo yang masih kosong;
jangan dijalankan dua kali pada database yang sama supaya data tidak dobel.

## Kredensial Midtrans

1. Daftar/login ke [dashboard.midtrans.com](https://dashboard.midtrans.com)
2. Buka **Settings > Access Keys** untuk melihat Server Key dan Client Key
3. Untuk testing, gunakan kredensial **Sandbox** (`SB-Mid-server-...`, `SB-Mid-client-...`)
   dan set `MIDTRANS_IS_PRODUCTION=false`
4. Untuk transaksi asli, pakai kredensial **Production** dan set `MIDTRANS_IS_PRODUCTION=true`

### Webhook notification (wajib untuk status otomatis)

Midtrans mengirim notifikasi status pembayaran ke server Anda lewat HTTP POST.
Supaya status pendaftaran otomatis berubah jadi "paid", daftarkan URL webhook di:

**Dashboard Midtrans > Settings > Configuration > Payment Notification URL**

```
https://domain-anda.com/webhook/midtrans
```

Saat masih di localhost, gunakan tool seperti `ngrok` untuk expose URL sementara agar
bisa didaftarkan dan diuji:

```bash
ngrok http 5000
# daftarkan https://xxxx.ngrok.io/webhook/midtrans di dashboard Midtrans
```

## Deploy ke VPS

1. Clone/upload folder ini ke VPS
2. Install dependencies di virtualenv (sama seperti setup lokal)
3. Isi `.env` dengan kredensial **production**
4. Jalankan dengan WSGI server yang layak produksi, contoh dengan `gunicorn`:

   ```bash
   pip install gunicorn
   gunicorn -w 2 -b 0.0.0.0:8000 app:app
   ```

5. Pasang reverse proxy (nginx) di depan gunicorn + HTTPS (Let's Encrypt/Certbot)
6. Update Payment Notification URL di dashboard Midtrans ke domain VPS Anda
7. Ganti `SECRET_KEY` di `.env` dengan string acak yang kuat
8. Ganti password admin default

## Alur sistem

1. Pengunjung mengisi form di `/` → pilih jenis booth → submit
2. Backend membuat record `Tenant` (status `pending`) dan transaksi Midtrans Snap,
   lalu mengembalikan `snap_token` ke browser
3. Snap.js membuka popup pembayaran di sisi klien
4. Setelah pengunjung membayar, Midtrans mengirim notifikasi ke `/webhook/midtrans`
5. Backend memverifikasi signature, lalu memperbarui status `Tenant` jadi `paid`
   (atau `expired`/`cancelled`/`failed` sesuai kondisi)
6. Admin bisa memantau semua ini real-time di `/admin`, termasuk override status
   manual untuk kasus pembayaran offline/khusus

## Catatan penting

- Kuota booth (`slots_remaining`) dihitung dari jumlah pendaftaran berstatus `paid`,
  bukan `pending` — supaya booth tidak "terkunci" oleh orang yang belum menyelesaikan
  pembayaran. Jika ingin slot langsung terkunci begitu checkout dimulai, logika ini
  perlu disesuaikan di `models.py` (`BoothType.slots_taken`).
- Harga yang dibayar tenant adalah snapshot (`price_at_registration`) saat pendaftaran
  dibuat — jika admin mengubah harga booth setelahnya, pendaftaran yang sudah ada
  tidak terpengaruh.
- Database memakai MongoDB (Atlas), diakses lewat ODM MongoEngine. Berkas
  `satria.db` (SQLite) yang lama sudah tidak dipakai aplikasi — disimpan hanya
  sebagai sumber data untuk `migrate_to_mongo.py`, aman dihapus setelah migrasi
  dipastikan berhasil.
