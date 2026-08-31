from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import secrets

db = SQLAlchemy()


class BoothType(db.Model):
    """Jenis booth pameran — harga dan kuota diatur lewat panel admin."""
    __tablename__ = "booth_types"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, default="")
    price = db.Column(db.Integer, nullable=False)  # dalam Rupiah, tanpa desimal
    quota = db.Column(db.Integer, nullable=False, default=0)
    is_active = db.Column(db.Boolean, default=True)
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    tenants = db.relationship("Tenant", backref="booth_type", lazy=True)

    @property
    def slots_taken(self):
        """Jumlah booth yang sudah terisi oleh pendaftaran yang settlement/capture."""
        return sum(1 for t in self.tenants if t.payment_status == "paid")

    @property
    def slots_remaining(self):
        return max(self.quota - self.slots_taken, 0)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "price": self.price,
            "quota": self.quota,
            "slots_taken": self.slots_taken,
            "slots_remaining": self.slots_remaining,
            "is_active": self.is_active,
            "sort_order": self.sort_order,
        }


class Tenant(db.Model):
    """Pendaftar / peserta pameran."""
    __tablename__ = "tenants"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.String(64), unique=True, nullable=False, index=True)

    institution_name = db.Column(db.String(200), nullable=False)
    pic_name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(150), nullable=False)
    phone = db.Column(db.String(30), nullable=False)

    booth_type_id = db.Column(db.Integer, db.ForeignKey("booth_types.id"), nullable=False)
    price_at_registration = db.Column(db.Integer, nullable=False)  # snapshot harga saat daftar

    # Keterangan dari pendaftar: karya/produk yang akan ditampilkan di booth
    description = db.Column(db.Text, default="")

    payment_status = db.Column(db.String(30), default="pending")
    # pending | paid | expired | cancelled | failed | refunded
    midtrans_transaction_id = db.Column(db.String(100))
    payment_type = db.Column(db.String(50))  # bank_transfer, qris, gopay, dll
    paid_at = db.Column(db.DateTime)

    # Token Snap disimpan agar pembayaran yang belum selesai bisa dibuka lagi
    snap_token = db.Column(db.String(120), default="")

    # order_id yang sedang dipakai di Midtrans. Berbeda dari kolom order_id
    # di atas, yang menjadi alamat tetap halaman status milik pendaftar.
    # Midtrans menolak order_id yang sama dipakai ulang, jadi saat pembayaran
    # diulang nilainya berganti — tanpa mengubah tautan yang sudah disalin.
    midtrans_order_id = db.Column(db.String(64), index=True)

    # Tiket masuk: token acak yang tidak bisa ditebak, dipakai sebagai isi QR.
    # Berbeda dari order_id yang tampil di URL dan email.
    checkin_token = db.Column(db.String(64), unique=True, index=True)
    checked_in_at = db.Column(db.DateTime)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @staticmethod
    def generate_checkin_token():
        """Token acak 32 karakter — tidak dapat ditebak dari nomor pendaftaran."""
        return secrets.token_urlsafe(24)

    def ensure_checkin_token(self):
        """Buat token bila belum ada. Dipanggil saat pembayaran lunas."""
        if not self.checkin_token:
            self.checkin_token = Tenant.generate_checkin_token()
        return self.checkin_token

    @property
    def is_checked_in(self):
        return self.checked_in_at is not None

    @staticmethod
    def generate_order_id():
        return f"SATRIA26-{secrets.token_hex(5).upper()}"

    def to_dict(self):
        return {
            "id": self.id,
            "order_id": self.order_id,
            "institution_name": self.institution_name,
            "pic_name": self.pic_name,
            "email": self.email,
            "phone": self.phone,
            "booth_type": self.booth_type.name if self.booth_type else None,
            "description": self.description,
            "price_at_registration": self.price_at_registration,
            "payment_status": self.payment_status,
            "payment_type": self.payment_type,
            "paid_at": self.paid_at.isoformat() if self.paid_at else None,
            "created_at": self.created_at.isoformat(),
        }


class AdminUser(db.Model):
    __tablename__ = "admin_users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)


class EventInfo(db.Model):
    """Informasi acara (lokasi, tanggal, peta) — baris tunggal, diatur lewat panel admin."""
    __tablename__ = "event_info"

    id = db.Column(db.Integer, primary_key=True)
    venue_name = db.Column(db.String(200), default="")
    address = db.Column(db.Text, default="")
    event_date = db.Column(db.String(120), default="")
    maps_url = db.Column(db.String(500), default="")

    # Bagian sambutan (hero) di halaman depan
    hero_eyebrow = db.Column(db.String(80), default="SATRIA 2026 · Exhibition")
    hero_title_before = db.Column(db.String(120), default="Pamerkan")
    hero_title_accent = db.Column(db.String(120), default="karya terbaik")
    hero_title_after = db.Column(db.String(120), default="mu disini")
    hero_lead = db.Column(db.Text,
                          default="Daftarkan booth untuk menampilkan karya, riset, dan inovasi "
                                  "Anda di hadapan pengunjung SATRIA 2026. Slot terbatas sesuai "
                                  "kuota masing-masing jenis booth.")
    hero_note = db.Column(db.String(200), default="PT Nusa Inspira Teknologi")
    hero_note_prefix = db.Column(db.String(80), default="In collaboration with")

    # Judul bagian pembicara di halaman depan
    speakers_eyebrow = db.Column(db.String(60), default="Narasumber")
    speakers_title = db.Column(db.String(150), default="Pembicara acara")
    speakers_subtitle = db.Column(db.String(300),
                                  default="Menghadirkan praktisi dan akademisi di bidangnya.")

    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def has_content(self):
        return any([self.venue_name, self.address, self.event_date])

    @staticmethod
    def get_or_create():
        """Selalu kembalikan satu baris EventInfo; buat jika belum ada."""
        info = EventInfo.query.first()
        if info is None:
            info = EventInfo()
            db.session.add(info)
            db.session.commit()
        return info


class GalleryPhoto(db.Model):
    """Foto carousel di halaman depan — diunggah dan diurutkan lewat panel admin."""
    __tablename__ = "gallery_photos"

    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    caption = db.Column(db.String(200), default="")
    sort_order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Pengaturan tampilan — gambar asli tidak diubah, hanya cara menampilkannya.
    fit_mode = db.Column(db.String(10), default="contain")   # contain | cover
    pos_x = db.Column(db.Integer, default=50)                # 0-100, kiri ke kanan
    pos_y = db.Column(db.Integer, default=50)                # 0-100, atas ke bawah

    @property
    def object_position(self):
        # Jangan pakai "or 50": posisi 0 sah dan tidak boleh dianggap kosong.
        x = 50 if self.pos_x is None else self.pos_x
        y = 50 if self.pos_y is None else self.pos_y
        return f"{x}% {y}%"


class Broadcast(db.Model):
    """Riwayat pengiriman email massal dari panel admin."""
    __tablename__ = "broadcasts"

    id = db.Column(db.Integer, primary_key=True)
    subject = db.Column(db.String(200), nullable=False)
    body = db.Column(db.Text, nullable=False)
    audience = db.Column(db.String(30), nullable=False)  # all | paid | pending
    total_recipients = db.Column(db.Integer, default=0)
    total_sent = db.Column(db.Integer, default=0)
    total_failed = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    AUDIENCE_LABELS = {
        "all": "Semua pendaftar",
        "paid": "Sudah lunas",
        "pending": "Menunggu pembayaran",
        "custom": "Pilihan manual",
    }

    @property
    def audience_label(self):
        return self.AUDIENCE_LABELS.get(self.audience, self.audience)


class Speaker(db.Model):
    """Pembicara acara — ditampilkan di halaman depan, diatur lewat panel admin."""
    __tablename__ = "speakers"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    institution = db.Column(db.String(200), default="")
    topic = db.Column(db.String(300), default="")
    photo = db.Column(db.String(255), default="")   # nama berkas di static/uploads
    sort_order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Bagian foto yang tampil di bingkai bulat (0-100). Foto selalu dipotong,
    # jadi cukup posisi — tidak perlu pilihan contain/cover seperti carousel.
    pos_x = db.Column(db.Integer, default=50)
    pos_y = db.Column(db.Integer, default=50)

    @property
    def object_position(self):
        x = 50 if self.pos_x is None else self.pos_x
        y = 50 if self.pos_y is None else self.pos_y
        return f"{x}% {y}%"

    @property
    def initials(self):
        """Inisial nama, dipakai bila pembicara belum punya foto."""
        parts = [p for p in (self.name or "").split() if p[:1].isalpha()]
        return "".join(p[0].upper() for p in parts[:2]) or "?"
