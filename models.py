import secrets
from datetime import datetime

import mongoengine as me


class BoothType(me.Document):
    """Jenis booth pameran — harga dan kuota diatur lewat panel admin."""
    meta = {"collection": "booth_types"}

    name = me.StringField(max_length=100, required=True)
    description = me.StringField(default="")
    price = me.IntField(required=True)  # dalam Rupiah, tanpa desimal
    quota = me.IntField(required=True, default=0)
    is_active = me.BooleanField(default=True)
    sort_order = me.IntField(default=0)
    created_at = me.DateTimeField(default=datetime.utcnow)

    @property
    def slots_taken(self):
        """Jumlah booth yang sudah terisi oleh pendaftaran yang settlement/capture."""
        return Tenant.objects(booth_type=self, payment_status="paid").count()

    @property
    def slots_remaining(self):
        return max(self.quota - self.slots_taken, 0)

    def to_dict(self):
        return {
            "id": str(self.id),
            "name": self.name,
            "description": self.description,
            "price": self.price,
            "quota": self.quota,
            "slots_taken": self.slots_taken,
            "slots_remaining": self.slots_remaining,
            "is_active": self.is_active,
            "sort_order": self.sort_order,
        }


class AddOn(me.Document):
    """Opsi tambahan saat pendaftaran (mis. dinner, cetak poster) — dikelola lewat panel admin."""
    meta = {"collection": "add_ons"}

    name = me.StringField(max_length=120, required=True)
    description = me.StringField(default="")
    price = me.IntField(required=True, default=0)  # dalam Rupiah, tanpa desimal
    is_active = me.BooleanField(default=True)
    sort_order = me.IntField(default=0)
    created_at = me.DateTimeField(default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": str(self.id),
            "name": self.name,
            "description": self.description,
            "price": self.price,
            "is_active": self.is_active,
        }


class SelectedAddOn(me.EmbeddedDocument):
    """Satu opsi tambahan yang dipilih pendaftar, dengan nama & harga snapshot saat mendaftar."""
    add_on = me.ReferenceField(AddOn)
    name = me.StringField(required=True)
    price = me.IntField(required=True)  # snapshot harga saat daftar


class Tenant(me.Document):
    """Pendaftar / peserta pameran."""
    meta = {
        "collection": "tenants",
        "indexes": [
            "midtrans_order_id",
            {"fields": ["checkin_token"], "unique": True, "sparse": True},
        ],
    }

    order_id = me.StringField(max_length=64, required=True, unique=True)

    institution_name = me.StringField(max_length=200, required=True)
    pic_name = me.StringField(max_length=150, required=True)
    email = me.StringField(max_length=150, required=True)
    phone = me.StringField(max_length=30, required=True)

    booth_type = me.ReferenceField(BoothType, required=True)
    price_at_registration = me.IntField(required=True)  # snapshot harga saat daftar

    # Keterangan dari pendaftar: karya/produk yang akan ditampilkan di booth
    description = me.StringField(default="")

    payment_status = me.StringField(max_length=30, default="pending")
    # pending | paid | expired | cancelled | failed | refunded
    midtrans_transaction_id = me.StringField(max_length=100)
    payment_type = me.StringField(max_length=50)  # bank_transfer, qris, gopay, dll
    paid_at = me.DateTimeField()

    # Token Snap disimpan agar pembayaran yang belum selesai bisa dibuka lagi
    snap_token = me.StringField(max_length=120, default="")

    # order_id yang sedang dipakai di Midtrans. Berbeda dari field order_id
    # di atas, yang menjadi alamat tetap halaman status milik pendaftar.
    # Midtrans menolak order_id yang sama dipakai ulang, jadi saat pembayaran
    # diulang nilainya berganti — tanpa mengubah tautan yang sudah disalin.
    midtrans_order_id = me.StringField(max_length=64)

    # Tiket masuk: token acak yang tidak bisa ditebak, dipakai sebagai isi QR.
    # Berbeda dari order_id yang tampil di URL dan email.
    checkin_token = me.StringField(max_length=64)
    checked_in_at = me.DateTimeField()

    selected_add_ons = me.EmbeddedDocumentListField(SelectedAddOn, default=list)

    created_at = me.DateTimeField(default=datetime.utcnow)
    updated_at = me.DateTimeField(default=datetime.utcnow)

    def save(self, *args, **kwargs):
        self.updated_at = datetime.utcnow()
        return super().save(*args, **kwargs)

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

    @property
    def addon_total(self):
        """Total harga seluruh opsi tambahan yang dipilih (snapshot saat daftar)."""
        return sum(a.price for a in self.selected_add_ons)

    @property
    def total_amount(self):
        """Total yang benar-benar ditagihkan: harga booth + seluruh opsi tambahan."""
        return self.price_at_registration + self.addon_total

    @staticmethod
    def generate_order_id():
        return f"SATRIA26-{secrets.token_hex(5).upper()}"

    def to_dict(self):
        return {
            "id": str(self.id),
            "order_id": self.order_id,
            "institution_name": self.institution_name,
            "pic_name": self.pic_name,
            "email": self.email,
            "phone": self.phone,
            "booth_type": self.booth_type.name if self.booth_type else None,
            "description": self.description,
            "price_at_registration": self.price_at_registration,
            "add_ons": [{"name": a.name, "price": a.price} for a in self.selected_add_ons],
            "total_amount": self.total_amount,
            "payment_status": self.payment_status,
            "payment_type": self.payment_type,
            "paid_at": self.paid_at.isoformat() if self.paid_at else None,
            "created_at": self.created_at.isoformat(),
        }


class AdminUser(me.Document):
    meta = {"collection": "admin_users"}

    username = me.StringField(max_length=80, required=True, unique=True)
    password_hash = me.StringField(max_length=255, required=True)


class EventInfo(me.Document):
    """Informasi acara (lokasi, tanggal, peta) — baris tunggal, diatur lewat panel admin."""
    meta = {"collection": "event_info"}

    venue_name = me.StringField(max_length=200, default="")
    address = me.StringField(default="")
    event_date = me.StringField(max_length=120, default="")
    maps_url = me.StringField(max_length=500, default="")

    # Bagian sambutan (hero) di halaman depan
    hero_eyebrow = me.StringField(max_length=80, default="SATRIA 2026 · Exhibition")
    hero_title_before = me.StringField(max_length=120, default="Pamerkan")
    hero_title_accent = me.StringField(max_length=120, default="karya terbaik")
    hero_title_after = me.StringField(max_length=120, default="mu disini")
    hero_lead = me.StringField(
        default="Daftarkan booth untuk menampilkan karya, riset, dan inovasi "
                "Anda di hadapan pengunjung SATRIA 2026. Slot terbatas sesuai "
                "kuota masing-masing jenis booth.")
    hero_note = me.StringField(max_length=200, default="PT Nusa Inspira Teknologi")
    hero_note_prefix = me.StringField(max_length=80, default="In collaboration with")

    # Judul bagian pembicara di halaman depan
    speakers_eyebrow = me.StringField(max_length=60, default="Narasumber")
    speakers_title = me.StringField(max_length=150, default="Pembicara acara")
    speakers_subtitle = me.StringField(
        max_length=300, default="Menghadirkan praktisi dan akademisi di bidangnya.")

    # Catatan/ketentuan acara — satu baris satu poin, tampil sebagai daftar di halaman depan.
    event_notes = me.StringField(default="")

    updated_at = me.DateTimeField(default=datetime.utcnow)

    def save(self, *args, **kwargs):
        self.updated_at = datetime.utcnow()
        return super().save(*args, **kwargs)

    @property
    def has_content(self):
        return any([self.venue_name, self.address, self.event_date])

    @property
    def notes_list(self):
        return [line.strip() for line in (self.event_notes or "").splitlines() if line.strip()]

    @staticmethod
    def get_or_create():
        """Selalu kembalikan satu baris EventInfo; buat jika belum ada."""
        info = EventInfo.objects.first()
        if info is None:
            info = EventInfo()
            info.save()
        return info


class GalleryPhoto(me.Document):
    """Foto carousel di halaman depan — diunggah dan diurutkan lewat panel admin."""
    meta = {"collection": "gallery_photos"}

    filename = me.StringField(max_length=255, required=True)
    caption = me.StringField(max_length=200, default="")
    sort_order = me.IntField(default=0)
    is_active = me.BooleanField(default=True)
    created_at = me.DateTimeField(default=datetime.utcnow)

    # Pengaturan tampilan — gambar asli tidak diubah, hanya cara menampilkannya.
    fit_mode = me.StringField(max_length=10, default="contain")   # contain | cover
    pos_x = me.IntField(default=50)                # 0-100, kiri ke kanan
    pos_y = me.IntField(default=50)                # 0-100, atas ke bawah

    @property
    def object_position(self):
        # Jangan pakai "or 50": posisi 0 sah dan tidak boleh dianggap kosong.
        x = 50 if self.pos_x is None else self.pos_x
        y = 50 if self.pos_y is None else self.pos_y
        return f"{x}% {y}%"


class Broadcast(me.Document):
    """Riwayat pengiriman email massal dari panel admin."""
    meta = {"collection": "broadcasts"}

    subject = me.StringField(max_length=200, required=True)
    body = me.StringField(required=True)
    audience = me.StringField(max_length=30, required=True)  # all | paid | pending
    total_recipients = me.IntField(default=0)
    total_sent = me.IntField(default=0)
    total_failed = me.IntField(default=0)
    created_at = me.DateTimeField(default=datetime.utcnow)

    AUDIENCE_LABELS = {
        "all": "Semua pendaftar",
        "paid": "Sudah lunas",
        "pending": "Menunggu pembayaran",
        "custom": "Pilihan manual",
    }

    @property
    def audience_label(self):
        return self.AUDIENCE_LABELS.get(self.audience, self.audience)


class Speaker(me.Document):
    """Pembicara acara — ditampilkan di halaman depan, diatur lewat panel admin."""
    meta = {"collection": "speakers"}

    name = me.StringField(max_length=150, required=True)
    institution = me.StringField(max_length=200, default="")
    topic = me.StringField(max_length=300, default="")
    photo = me.StringField(max_length=255, default="")   # nama berkas di static/uploads
    sort_order = me.IntField(default=0)
    is_active = me.BooleanField(default=True)
    created_at = me.DateTimeField(default=datetime.utcnow)

    # Bagian foto yang tampil di bingkai bulat (0-100). Foto selalu dipotong,
    # jadi cukup posisi — tidak perlu pilihan contain/cover seperti carousel.
    pos_x = me.IntField(default=50)
    pos_y = me.IntField(default=50)

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
