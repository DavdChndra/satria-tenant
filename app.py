import csv
import io
import os
import re
import secrets
from functools import wraps
from datetime import datetime, timedelta

import mongoengine as me
from bson.errors import InvalidId
from dotenv import load_dotenv
from flask import (Flask, render_template, request, jsonify, redirect,
                   url_for, session, flash, Response, abort)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

from models import (BoothType, Tenant, AdminUser, EventInfo,
                    GalleryPhoto, Broadcast, Speaker, AddOn, SelectedAddOn,
                    HighlightItem, AgendaItem, ReasonItem, KeynoteSection)
from midtrans_service import (create_transaction, verify_notification_signature,
                              map_transaction_status, get_transaction_status)
from email_service import (send_registration_received, send_payment_success,
                           send_broadcast, is_configured as email_is_configured)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-ganti-di-produksi")
ADMIN_IDLE_TIMEOUT = timedelta(minutes=5)
app.config["PERMANENT_SESSION_LIFETIME"] = ADMIN_IDLE_TIMEOUT
app.config["MIDTRANS_CLIENT_KEY"] = os.environ.get("MIDTRANS_CLIENT_KEY", "")
app.config["MIDTRANS_IS_PRODUCTION"] = os.environ.get("MIDTRANS_IS_PRODUCTION", "false").lower() == "true"

UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
ALLOWED_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # batas unggahan 5 MB
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Warna penanda tiap jenis booth pada kartu pratinjau di halaman depan
BOOTH_COLORS = ["#2563EB", "#1F8A5B", "#E0722F", "#6D28D9"]

MONGODB_URI = os.environ.get("MONGODB_URI")
if not MONGODB_URI:
    raise RuntimeError(
        "MONGODB_URI belum diisi di .env. Contoh: "
        "mongodb+srv://user:password@cluster.mongodb.net/satria"
    )
me.connect(host=MONGODB_URI)


# ---------- helper ----------

def admin_required(view):
    """
    Wajibkan login admin, dan paksa logout otomatis setelah 5 menit tanpa
    aktivitas - mengembalikan pengunjung ke halaman utama, bukan ke login,
    supaya tidak terlihat seperti sesi admin sedang menunggu di sana.
    """
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin_id"):
            return redirect(url_for("admin_login"))

        last_activity_raw = session.get("last_activity")
        if last_activity_raw:
            try:
                last_activity = datetime.fromisoformat(last_activity_raw)
            except ValueError:
                last_activity = None
            if last_activity is None or datetime.utcnow() - last_activity > ADMIN_IDLE_TIMEOUT:
                session.clear()
                flash("Sesi admin berakhir karena tidak ada aktivitas. Silakan login kembali.", "error")
                return redirect(url_for("index"))

        session.permanent = True
        session["last_activity"] = datetime.utcnow().isoformat()
        return view(*args, **kwargs)
    return wrapped


def get_or_none(model, doc_id):
    """Ambil dokumen berdasarkan id (ObjectId), atau None bila id tidak valid/tidak ada."""
    if not doc_id:
        return None
    try:
        return model.objects(pk=doc_id).first()
    except (InvalidId, me.ValidationError, TypeError):
        return None


def get_or_404(model, doc_id):
    obj = get_or_none(model, doc_id)
    if obj is None:
        abort(404)
    return obj


def get_by_field_or_404(model, **kwargs):
    obj = model.objects(**kwargs).first()
    if obj is None:
        abort(404)
    return obj


def valid_object_ids(id_list):
    """Saring hanya string yang berbentuk ObjectId (24 karakter heksadesimal) yang sah."""
    from bson import ObjectId
    result = []
    for i in id_list or []:
        try:
            result.append(ObjectId(str(i)))
        except (InvalidId, TypeError):
            continue
    return result


def form_text(name, default=""):
    value = request.form.get(name, default)
    return value.strip() if isinstance(value, str) else default


def nonnegative_int(value, default=None):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= 0 else default


def valid_email(value):
    return bool(re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value))


def next_sort_order(model):
    last = model.objects.order_by("-sort_order").first()
    return (last.sort_order if last else 0) + 1


def save_uploaded_photo(file_storage):
    """
    Simpan file gambar yang diunggah ke static/uploads dengan nama acak.
    Mengembalikan nama file, atau None jika file tidak valid.
    """
    if not file_storage or not file_storage.filename:
        return None
    ext = os.path.splitext(secure_filename(file_storage.filename))[1].lower()
    if ext not in ALLOWED_IMAGE_EXT:
        return None
    filename = f"{secrets.token_hex(8)}{ext}"
    file_storage.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
    return filename


def delete_photo_file(filename):
    """Hapus berkas foto dari disk; abaikan bila berkas sudah tidak ada."""
    if not filename:
        return
    try:
        os.remove(os.path.join(app.config["UPLOAD_FOLDER"], filename))
    except OSError:
        pass


def seed_defaults():
    """Isi data awal jika database masih kosong."""
    if BoothType.objects.count() == 0:
        BoothType(name="Booth standar", description="Ruang pameran 2x2 meter, meja, dua kursi.",
                  price=250000, quota=20, sort_order=1).save()
        BoothType(name="Booth premium", description="Ruang pameran 3x3 meter, signage, slot demo panggung utama.",
                  price=300000, quota=10, sort_order=2).save()
    if EventInfo.objects.count() == 0:
        EventInfo(
            venue_name="Gedung Serbaguna Telkom University",
            address="Jl. Telekomunikasi No. 1, Terusan Buahbatu, Bandung, Jawa Barat 40257",
            event_date="15 - 17 Mei 2026",
            maps_url="https://maps.google.com/?q=Telkom+University+Bandung",
        ).save()
    if AdminUser.objects.count() == 0:
        AdminUser(
            username="admin",
            password_hash=generate_password_hash("ubah-password-ini"),
        ).save()
    if AddOn.objects.count() == 0:
        AddOn(name="Makan malam (dinner)",
              description="Termasuk makan malam bersama panitia dan peserta lain di hotel.",
              price=75000, sort_order=1).save()
        AddOn(name="Cetak poster",
              description="Poster A1 dicetak panitia dan dipasang di area booth Anda.",
              price=40000, sort_order=2).save()
    if HighlightItem.objects.count() == 0:
        HighlightItem(title="50+ Tenant",
                      description="Booth UMKM, komunitas, dan startup kampus dalam satu area pameran.",
                      sort_order=1).save()
        HighlightItem(title="Panggung Talkshow",
                      description="Diskusi kewirausahaan bersama praktisi dan alumni.",
                      sort_order=2).save()
        HighlightItem(title="Zona Komunitas",
                      description="Ruang kolaborasi antar organisasi dan UKM kampus.",
                      sort_order=3).save()
        HighlightItem(title="Hiburan Panggung",
                      description="Penampilan musik dan pertunjukan mahasiswa sepanjang acara.",
                      sort_order=4).save()
    if AgendaItem.objects.count() == 0:
        AgendaItem(time_label="08.00", activity="Registrasi & pembukaan booth", sort_order=1).save()
        AgendaItem(time_label="09.30", activity="Sesi pembuka & sambutan panitia", sort_order=2).save()
        AgendaItem(time_label="11.00", activity="Talkshow kewirausahaan", sort_order=3).save()
        AgendaItem(time_label="12.30", activity="Istirahat & jejaring", sort_order=4).save()
        AgendaItem(time_label="13.30", activity="Sesi komunitas & hiburan panggung", sort_order=5).save()
        AgendaItem(time_label="17.00", activity="Booth ditutup", sort_order=6).save()
    if ReasonItem.objects.count() == 0:
        ReasonItem(title="Jangkau ratusan pengunjung",
                  description="Booth kamu terlihat langsung oleh pengunjung kampus dan komunitas sekitar.",
                  sort_order=1).save()
        ReasonItem(title="Bangun relasi baru",
                  description="Bertemu tenant lain, komunitas, dan calon pelanggan dalam satu tempat.",
                  sort_order=2).save()
        ReasonItem(title="Proses pendaftaran mudah",
                  description="Daftar dan bayar online, pantau status kapan saja lewat halaman status.",
                  sort_order=3).save()
    if KeynoteSection.objects.count() == 0:
        KeynoteSection(
            title="Membangun masa depan kewirausahaan kampus",
            body="Sesi pembuka SATRIA 2026 mengangkat cerita nyata dari tenant-tenant yang "
                 "tumbuh dari booth kecil di kampus menjadi bisnis yang berkelanjutan. Panitia "
                 "mengundang seluruh peserta untuk hadir sejak sesi pertama.",
        ).save()


# ---------- halaman publik ----------

@app.route("/")
def index():
    booth_types = BoothType.objects(is_active=True).order_by("sort_order")
    photos = GalleryPhoto.objects(is_active=True).order_by("sort_order", "id")
    speakers = Speaker.objects(is_active=True).order_by("sort_order", "id")
    add_ons = AddOn.objects(is_active=True).order_by("sort_order", "id")
    highlight_items = HighlightItem.objects(is_active=True).order_by("sort_order", "id")
    agenda_items = AgendaItem.objects.order_by("sort_order", "id")
    reason_items = ReasonItem.objects.order_by("sort_order", "id")
    return render_template("index.html",
                           booth_types=booth_types,
                           photos=photos,
                           speakers=speakers,
                           add_ons=add_ons,
                           highlight_items=highlight_items,
                           agenda_items=agenda_items,
                           reason_items=reason_items,
                           keynote_section=KeynoteSection.get_or_create(),
                           event_info=EventInfo.get_or_create(),
                           total_remaining=sum(b.slots_remaining for b in booth_types),
                           booth_colors=BOOTH_COLORS)


@app.route("/daftar")
def registration_form():
    """Halaman formulir pendaftaran tenant - terpisah dari landing page acara."""
    booth_types = BoothType.objects(is_active=True).order_by("sort_order")
    add_ons = AddOn.objects(is_active=True).order_by("sort_order", "id")
    return render_template("register.html",
                           booth_types=booth_types,
                           add_ons=add_ons,
                           event_info=EventInfo.get_or_create())


@app.route("/api/register", methods=["POST"])
def api_register():
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({"error": "Payload pendaftaran tidak valid."}), 400

    required = ["institution_name", "pic_name", "email", "phone", "booth_type_id"]
    values = {f: data.get(f, "") for f in required}
    missing = [f for f in required if not isinstance(values[f], str) or not values[f].strip()]
    if missing:
        return jsonify({"error": f"Field wajib belum diisi: {', '.join(missing)}"}), 400

    institution_name = values["institution_name"].strip()
    pic_name = values["pic_name"].strip()
    email = values["email"].strip()
    phone = values["phone"].strip()
    booth_type_id = values["booth_type_id"].strip()
    if len(institution_name) > 200 or len(pic_name) > 150 or len(email) > 150 or len(phone) > 30:
        return jsonify({"error": "Data pendaftaran melebihi batas panjang yang diizinkan."}), 400
    if not valid_email(email):
        return jsonify({"error": "Format email tidak valid."}), 400

    booth = get_or_none(BoothType, booth_type_id)
    if not booth or not booth.is_active:
        return jsonify({"error": "Jenis booth tidak ditemukan atau tidak aktif."}), 400
    if booth.slots_remaining <= 0:
        return jsonify({"error": "Kuota booth ini sudah penuh."}), 400

    requested_addon_ids = data.get("add_on_ids") or []
    if not isinstance(requested_addon_ids, list):
        return jsonify({"error": "Pilihan opsi tambahan tidak valid."}), 400
    valid_addon_ids = valid_object_ids(requested_addon_ids)
    if (len(valid_addon_ids) != len(requested_addon_ids)
            or len(set(valid_addon_ids)) != len(requested_addon_ids)):
        return jsonify({"error": "Pilihan opsi tambahan tidak valid."}), 400
    requested_addon_ids = valid_addon_ids
    selected_add_ons = []
    if requested_addon_ids:
        selected_add_ons = list(AddOn.objects(id__in=requested_addon_ids, is_active=True))
        if len(selected_add_ons) != len(set(requested_addon_ids)):
            return jsonify({"error": "Ada opsi tambahan yang tidak tersedia."}), 400

    description = data.get("description", "")
    if not isinstance(description, str):
        return jsonify({"error": "Deskripsi tidak valid."}), 400
    if len(description.strip()) > 2000:
        return jsonify({"error": "Deskripsi terlalu panjang."}), 400

    order_id = Tenant.generate_order_id()
    tenant = Tenant(
        order_id=order_id,
        institution_name=institution_name,
        pic_name=pic_name,
        email=email,
        phone=phone,
        booth_type=booth,
        price_at_registration=booth.price,
        description=description.strip(),
        payment_status="pending",
        selected_add_ons=[SelectedAddOn(add_on=a, name=a.name, price=a.price) for a in selected_add_ons],
    )
    tenant.save()

    item_details = [{"id": f"booth-{booth.id}", "price": booth.price, "quantity": 1, "name": booth.name[:50]}]
    for addon in selected_add_ons:
        item_details.append({"id": f"addon-{addon.id}", "price": addon.price, "quantity": 1, "name": addon.name[:50]})

    try:
        result = create_transaction(
            order_id=order_id,
            gross_amount=tenant.total_amount,
            customer={
                "first_name": tenant.pic_name,
                "email": tenant.email,
                "phone": tenant.phone,
            },
            item_name=f"Pendaftaran {booth.name} - SATRIA 2026",
            item_details=item_details,
        )
    except Exception as exc:
        return jsonify({"error": f"Gagal membuat transaksi Midtrans: {exc}"}), 502

    tenant.snap_token = result.get("token", "")
    tenant.midtrans_order_id = order_id
    tenant.save()

    send_registration_received(tenant, url_for("registration_status", order_id=order_id, _external=True))

    return jsonify({
        "order_id": order_id,
        "snap_token": result.get("token"),
        "redirect_url": result.get("redirect_url"),
    })


def refresh_pending_tenant_status(tenant):
    """
    Tanyakan status terkini ke Midtrans untuk pendaftaran yang masih "pending".
    Menangkap kasus transaksi yang sudah kedaluwarsa/gagal di sisi Midtrans
    tapi notifikasi webhook-nya belum sampai, supaya pendaftar tidak terus
    disodori tombol "Lanjutkan pembayaran" untuk transaksi yang sudah mati.
    """
    if tenant.payment_status != "pending" or not tenant.midtrans_order_id:
        return
    info = get_transaction_status(tenant.midtrans_order_id)
    if not info or not info.get("transaction_status"):
        return
    sync_tenant_payment_status(
        tenant, info.get("transaction_status"), info.get("fraud_status"),
        payment_type=info.get("payment_type"), transaction_id=info.get("transaction_id"),
    )


@app.route("/status/<order_id>")
def registration_status(order_id):
    tenant = get_by_field_or_404(Tenant, order_id=order_id)
    refresh_pending_tenant_status(tenant)
    return render_template("status.html", tenant=tenant)


@app.route("/api/pay/<order_id>", methods=["POST"])
def api_resume_payment(order_id):
    """
    Buka kembali jendela pembayaran untuk pendaftaran yang belum lunas.
    Token lama dipakai ulang; bila sudah tidak berlaku, dibuatkan yang baru.
    """
    tenant = get_by_field_or_404(Tenant, order_id=order_id)
    refresh_pending_tenant_status(tenant)

    if tenant.payment_status == "paid":
        return jsonify({"error": "Pendaftaran ini sudah lunas."}), 400
    if tenant.payment_status != "pending":
        return jsonify({"error": "Transaksi ini sudah tidak berlaku. Silakan muat ulang halaman."}), 400

    if tenant.snap_token:
        return jsonify({"snap_token": tenant.snap_token, "order_id": tenant.order_id})

    # Midtrans menolak order_id yang sudah pernah dipakai, jadi transaksi baru
    # memakai nomor baru. Nomor pendaftaran (order_id) sengaja TIDAK diubah
    # agar tautan status yang sudah disalin pendaftar tetap berlaku.
    new_midtrans_id = Tenant.generate_order_id()
    item_details = [{"id": f"booth-{tenant.booth_type.id}", "price": tenant.price_at_registration,
                      "quantity": 1, "name": tenant.booth_type.name[:50]}]
    for sel in tenant.selected_add_ons:
        item_details.append({"id": f"addon-{sel.add_on.id if sel.add_on else sel.name}", "price": sel.price,
                             "quantity": 1, "name": sel.name[:50]})
    try:
        result = create_transaction(
            order_id=new_midtrans_id,
            gross_amount=tenant.total_amount,
            customer={"first_name": tenant.pic_name,
                      "email": tenant.email,
                      "phone": tenant.phone},
            item_name=f"Pendaftaran {tenant.booth_type.name} - SATRIA 2026",
            item_details=item_details,
        )
    except Exception as exc:
        return jsonify({"error": f"Gagal membuat transaksi: {exc}"}), 502

    tenant.midtrans_order_id = new_midtrans_id
    tenant.snap_token = result.get("token", "")
    tenant.save()
    return jsonify({"snap_token": tenant.snap_token, "order_id": tenant.order_id})


@app.route("/api/payment/<order_id>/confirm", methods=["POST"])
def api_confirm_payment(order_id):
    """Segarkan status pembayaran setelah Snap melaporkan pembayaran sukses."""
    tenant = get_by_field_or_404(Tenant, order_id=order_id)
    refresh_pending_tenant_status(tenant)
    return jsonify({"paid": tenant.payment_status == "paid"})


@app.route("/ticket/<order_id>/qr.svg")
def ticket_qr(order_id):
    """Gambar QR tiket masuk. Isinya token acak, bukan nomor pendaftaran."""
    tenant = get_by_field_or_404(Tenant, order_id=order_id)
    if tenant.payment_status != "paid" or not tenant.checkin_token:
        abort(404)

    import qrcode
    from qrcode.image.svg import SvgPathImage

    qr = qrcode.QRCode(version=None, box_size=10, border=2,
                       error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(tenant.checkin_token)
    qr.make(fit=True)

    buf = io.BytesIO()
    qr.make_image(image_factory=SvgPathImage).save(buf)
    return Response(buf.getvalue(), mimetype="image/svg+xml",
                    headers={"Cache-Control": "no-store"})


@app.route("/ticket/<order_id>")
def ticket_preview(order_id):
    """Pratinjau ID card peserta - hanya untuk pendaftaran yang sudah lunas."""
    tenant = get_by_field_or_404(Tenant, order_id=order_id)
    if tenant.payment_status != "paid":
        flash("Kartu peserta terbit setelah pembayaran lunas.", "error")
        return redirect(url_for("registration_status", order_id=order_id))
    tenant.ensure_checkin_token()
    tenant.save()
    return render_template("ticket.html", tenant=tenant,
                           event_info=EventInfo.get_or_create())


def sync_tenant_payment_status(tenant, transaction_status, fraud_status,
                               payment_type=None, transaction_id=None):
    """
    Terapkan status transaksi dari Midtrans ke satu tenant. Dipakai baik oleh
    webhook maupun oleh pengecekan manual (halaman status / lanjutkan
    pembayaran) supaya keduanya konsisten. Mengembalikan True bila status
    baru saja berubah jadi "paid" (dipakai untuk memicu email bukti bayar).
    """
    new_status = map_transaction_status(transaction_status, fraud_status)
    was_paid = tenant.payment_status == "paid"
    status_changed = new_status != tenant.payment_status

    tenant.payment_status = new_status
    if payment_type:
        tenant.payment_type = payment_type
    if transaction_id:
        tenant.midtrans_transaction_id = transaction_id
    if new_status == "paid" and not tenant.paid_at:
        tenant.paid_at = datetime.utcnow()
    if new_status == "paid":
        tenant.ensure_checkin_token()
    elif new_status in ("expired", "cancelled", "failed") and status_changed:
        # Token Snap lama sudah tidak berlaku, jangan ditawarkan lagi untuk dibayar.
        tenant.snap_token = ""
    tenant.save()

    return new_status == "paid" and not was_paid


@app.route("/webhook/midtrans", methods=["POST"])
def midtrans_webhook():
    """Endpoint notifikasi HTTP dari Midtrans. Daftarkan URL ini di dashboard Midtrans."""
    payload = request.get_json(force=True, silent=True) or {}

    order_id = payload.get("order_id")
    status_code = payload.get("status_code")
    gross_amount = payload.get("gross_amount")
    signature_key = payload.get("signature_key")
    transaction_status = payload.get("transaction_status")
    fraud_status = payload.get("fraud_status")
    payment_type = payload.get("payment_type")

    if not all([order_id, status_code, gross_amount, signature_key, transaction_status]):
        return jsonify({"error": "Payload tidak lengkap"}), 400

    if not verify_notification_signature(order_id, status_code, gross_amount, signature_key):
        return jsonify({"error": "Signature tidak valid"}), 403

    # Midtrans mengirim nomor transaksi yang sedang berjalan. Untuk pendaftaran
    # yang pembayarannya pernah diulang, nomor itu ada di midtrans_order_id.
    tenant = (Tenant.objects(midtrans_order_id=order_id).first()
              or Tenant.objects(order_id=order_id).first())
    if not tenant:
        return jsonify({"error": "Order tidak ditemukan"}), 404

    just_paid = sync_tenant_payment_status(
        tenant, transaction_status, fraud_status,
        payment_type=payment_type, transaction_id=payload.get("transaction_id"),
    )

    # Midtrans dapat mengirim notifikasi yang sama berulang kali;
    # email lunas hanya dikirim pada perubahan status pertama ke "paid".
    if just_paid:
        send_payment_success(tenant, url_for("registration_status",
                                             order_id=tenant.order_id, _external=True))

    return jsonify({"ok": True})


# ---------- admin ----------

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        user = AdminUser.objects(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            session.clear()
            session["admin_id"] = str(user.id)
            session["last_activity"] = datetime.utcnow().isoformat()
            session.permanent = True
            return redirect(url_for("admin_dashboard"))
        flash("Username atau password salah.", "error")
    return render_template("admin/login.html")


@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))


@app.route("/admin/idle-logout")
def admin_idle_logout():
    """Dipanggil dari sisi klien saat admin tidak aktif selama 5 menit."""
    session.clear()
    flash("Sesi admin berakhir karena tidak ada aktivitas.", "error")
    return redirect(url_for("index"))


@app.route("/admin")
@admin_required
def admin_dashboard():
    """Ringkasan - halaman awal admin, hanya statistik dan pintasan."""
    tenants = Tenant.objects.only("payment_status", "price_at_registration", "selected_add_ons")
    total_paid = sum(t.total_amount for t in tenants if t.payment_status == "paid")
    total_pending = sum(1 for t in tenants if t.payment_status == "pending")
    total_registrations = tenants.count()

    return render_template(
        "admin/ringkasan.html",
        active_nav="ringkasan",
        total_paid=total_paid,
        total_pending=total_pending,
        total_registrations=total_registrations,
    )


@app.route("/admin/hero")
@admin_required
def admin_hero():
    """Halaman pengaturan sambutan (hero) di landing page."""
    return render_template("admin/hero.html", active_nav="hero", event_info=EventInfo.get_or_create())


@app.route("/admin/lokasi")
@admin_required
def admin_lokasi():
    """Halaman pengaturan lokasi dan catatan acara."""
    return render_template("admin/lokasi.html", active_nav="lokasi", event_info=EventInfo.get_or_create())


@app.route("/admin/summit")
@admin_required
def admin_summit():
    """Halaman pengaturan konten summit: intro, keynote, sorotan, agenda, alasan hadir."""
    return render_template(
        "admin/summit.html",
        active_nav="summit",
        event_info=EventInfo.get_or_create(),
        keynote_section=KeynoteSection.get_or_create(),
        highlight_items=HighlightItem.objects.order_by("sort_order", "id"),
        agenda_items=AgendaItem.objects.order_by("sort_order", "id"),
        reason_items=ReasonItem.objects.order_by("sort_order", "id"),
    )


@app.route("/admin/foto")
@admin_required
def admin_foto():
    """Halaman pengelolaan foto carousel."""
    return render_template(
        "admin/foto.html",
        active_nav="foto",
        photos=GalleryPhoto.objects.order_by("sort_order", "id"),
    )


@app.route("/admin/pembicara")
@admin_required
def admin_pembicara():
    """Halaman pengelolaan pembicara acara."""
    return render_template(
        "admin/pembicara.html",
        active_nav="pembicara",
        event_info=EventInfo.get_or_create(),
        speakers=Speaker.objects.order_by("sort_order", "id"),
    )


@app.route("/admin/booth")
@admin_required
def admin_booth():
    """Halaman pengaturan jenis booth."""
    return render_template(
        "admin/booth.html",
        active_nav="booth",
        booth_types=BoothType.objects.order_by("sort_order"),
    )


@app.route("/admin/tambahan")
@admin_required
def admin_tambahan():
    """Halaman pengaturan opsi tambahan pendaftaran."""
    return render_template(
        "admin/tambahan.html",
        active_nav="tambahan",
        add_ons=AddOn.objects.order_by("sort_order", "id"),
    )


@app.route("/admin/email")
@admin_required
def admin_email():
    """Halaman pengiriman email broadcast ke pendaftar."""
    tenants = list(Tenant.objects.order_by("-created_at"))
    return render_template(
        "admin/email.html",
        active_nav="email",
        tenants=tenants,
        broadcasts=Broadcast.objects.order_by("-created_at").limit(10),
        email_ready=email_is_configured(),
        count_all=len(tenants),
        count_paid=sum(1 for t in tenants if t.payment_status == "paid"),
        count_pending=sum(1 for t in tenants if t.payment_status == "pending"),
    )


@app.route("/admin/pendaftaran")
@admin_required
def admin_pendaftaran():
    """Halaman daftar pendaftaran tenant."""
    return render_template(
        "admin/pendaftaran.html",
        active_nav="pendaftaran",
        tenants=Tenant.objects.order_by("-created_at"),
    )


@app.route("/admin/akun")
@admin_required
def admin_akun():
    """Halaman ubah password admin."""
    return render_template("admin/akun.html", active_nav="akun")


@app.route("/admin/tenants/export.csv")
@admin_required
def admin_export_tenants_csv():
    """Unduh seluruh daftar pendaftaran sebagai berkas CSV."""
    tenants = Tenant.objects.order_by("-created_at")

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "No. Pendaftaran", "Institusi", "PIC", "Email", "Telepon", "Booth",
        "Karya / Produk", "Harga Booth", "Opsi Tambahan", "Total Pembayaran",
        "Status Pembayaran", "Tipe Pembayaran",
        "Tanggal Daftar", "Tanggal Lunas", "Waktu Check-in",
    ])
    for t in tenants:
        addon_text = "; ".join(f"{sel.name} (Rp{sel.price:,})".replace(",", ".")
                               for sel in t.selected_add_ons) or "-"
        writer.writerow([
            t.order_id,
            t.institution_name,
            t.pic_name,
            t.email,
            t.phone,
            t.booth_type.name if t.booth_type else "",
            t.description,
            t.price_at_registration,
            addon_text,
            t.total_amount,
            t.payment_status,
            t.payment_type or "",
            t.created_at.strftime("%Y-%m-%d %H:%M"),
            t.paid_at.strftime("%Y-%m-%d %H:%M") if t.paid_at else "",
            t.checked_in_at.strftime("%Y-%m-%d %H:%M") if t.checked_in_at else "",
        ])

    # BOM di depan agar Excel membaca karakter non-ASCII (mis. nama institusi) dengan benar.
    csv_data = "﻿" + output.getvalue()
    filename = f"pendaftaran-satria-{datetime.utcnow().strftime('%Y%m%d-%H%M')}.csv"
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.route("/admin/scan")
@admin_required
def admin_scan():
    """Halaman pemindai QR untuk validasi peserta di hari pelaksanaan."""
    checked_in = (Tenant.objects(checked_in_at__ne=None)
                  .order_by("-checked_in_at")
                  .limit(15))
    total_paid = Tenant.objects(payment_status="paid").count()
    total_in = Tenant.objects(checked_in_at__ne=None).count()
    return render_template("admin/scan.html",
                           active_nav="scan",
                           checked_in=checked_in,
                           total_paid=total_paid,
                           total_in=total_in)


@app.route("/admin/scan/verify", methods=["POST"])
@admin_required
def admin_scan_verify():
    """
    Memvalidasi token hasil pindaian.
    Mengembalikan JSON agar halaman scan bisa menampilkan hasil tanpa muat ulang.
    """
    payload = request.get_json(silent=True) or {}
    token = str(payload.get("token", "")).strip()
    if not token:
        return jsonify({"status": "invalid", "message": "Kode kosong."}), 400

    tenant = Tenant.objects(checkin_token=token).first()
    if not tenant:
        return jsonify({"status": "invalid",
                        "message": "Kode tidak dikenali. Kartu ini tidak sah."}), 404

    if tenant.payment_status != "paid":
        return jsonify({"status": "unpaid",
                        "message": "Pendaftaran ini belum lunas.",
                        "institution": tenant.institution_name}), 409

    already = tenant.is_checked_in
    if not already:
        tenant.checked_in_at = datetime.utcnow()
        tenant.save()

    return jsonify({
        "status": "repeat" if already else "ok",
        "message": ("Peserta ini sudah masuk sebelumnya."
                    if already else "Validasi berhasil."),
        "order_id": tenant.order_id,
        "institution": tenant.institution_name,
        "pic": tenant.pic_name,
        "booth": tenant.booth_type.name if tenant.booth_type else "-",
        "checked_in_at": tenant.checked_in_at.strftime("%d %b %Y %H:%M"),
    })


@app.route("/admin/scan/reset/<tenant_id>", methods=["POST"])
@admin_required
def admin_scan_reset(tenant_id):
    """Batalkan status hadir, misalnya bila salah pindai."""
    tenant = get_or_404(Tenant, tenant_id)
    tenant.checked_in_at = None
    tenant.save()
    flash(f"Status hadir {tenant.order_id} dibatalkan.", "success")
    return redirect(url_for("admin_scan"))


@app.route("/admin/booth/<booth_id>/update", methods=["POST"])
@admin_required
def admin_update_booth(booth_id):
    booth = get_or_404(BoothType, booth_id)
    name = form_text("name", booth.name)
    price = nonnegative_int(request.form.get("price", booth.price))
    quota = nonnegative_int(request.form.get("quota", booth.quota))
    if not name:
        flash("Nama jenis booth wajib diisi.", "error")
        return redirect(url_for("admin_booth"))
    if price is None or quota is None:
        flash("Harga dan kuota harus berupa angka.", "error")
        return redirect(url_for("admin_booth"))
    booth.name = name
    booth.description = form_text("description", booth.description)
    booth.price = price
    booth.quota = quota
    booth.is_active = request.form.get("is_active") == "on"
    booth.save()
    flash(f"Pengaturan '{booth.name}' berhasil disimpan.", "success")
    return redirect(url_for("admin_booth"))


@app.route("/admin/booth/new", methods=["POST"])
@admin_required
def admin_new_booth():
    price = nonnegative_int(request.form.get("price"))
    quota = nonnegative_int(request.form.get("quota"))
    if price is None or quota is None:
        flash("Harga dan kuota harus berupa angka.", "error")
        return redirect(url_for("admin_booth"))
    name = form_text("name")
    if not name:
        flash("Nama jenis booth wajib diisi.", "error")
        return redirect(url_for("admin_booth"))
    BoothType(
        name=name,
        description=form_text("description"),
        price=price,
        quota=quota,
        sort_order=next_sort_order(BoothType),
    ).save()
    flash(f"Jenis booth '{name}' ditambahkan.", "success")
    return redirect(url_for("admin_booth"))


@app.route("/admin/addon/<addon_id>/update", methods=["POST"])
@admin_required
def admin_update_addon(addon_id):
    """Ubah nama, deskripsi, harga, atau status aktif satu opsi tambahan."""
    addon = get_or_404(AddOn, addon_id)
    name = form_text("name")
    if not name:
        flash("Nama opsi tambahan wajib diisi.", "error")
        return redirect(url_for("admin_tambahan"))
    price = nonnegative_int(request.form.get("price", addon.price))
    if price is None:
        flash("Harga harus berupa angka.", "error")
        return redirect(url_for("admin_tambahan"))
    addon.name = name
    addon.description = form_text("description")
    addon.price = price
    addon.is_active = request.form.get("is_active") == "on"
    addon.save()
    flash(f"Opsi tambahan '{addon.name}' berhasil disimpan.", "success")
    return redirect(url_for("admin_tambahan"))


@app.route("/admin/addon/new", methods=["POST"])
@admin_required
def admin_new_addon():
    """Tambah opsi tambahan baru (mis. dinner, cetak poster)."""
    name = form_text("name")
    if not name:
        flash("Nama opsi tambahan wajib diisi.", "error")
        return redirect(url_for("admin_tambahan"))
    price = nonnegative_int(request.form.get("price"))
    if price is None:
        flash("Harga harus berupa angka.", "error")
        return redirect(url_for("admin_tambahan"))
    AddOn(
        name=name,
        description=form_text("description"),
        price=price,
        sort_order=next_sort_order(AddOn),
    ).save()
    flash(f"Opsi tambahan '{name}' ditambahkan.", "success")
    return redirect(url_for("admin_tambahan"))


@app.route("/admin/password", methods=["POST"])
@admin_required
def admin_change_password():
    """Ubah password admin yang sedang login. Wajib memasukkan password lama."""
    old_password = request.form.get("old_password", "")
    new_password = request.form.get("new_password", "")
    new_password_confirm = request.form.get("new_password_confirm", "")

    user = get_or_404(AdminUser, session["admin_id"])

    if not check_password_hash(user.password_hash, old_password):
        flash("Password lama tidak sesuai.", "error")
    elif len(new_password) < 8:
        flash("Password baru minimal 8 karakter.", "error")
    elif new_password != new_password_confirm:
        flash("Konfirmasi password baru tidak cocok.", "error")
    else:
        user.password_hash = generate_password_hash(new_password)
        user.save()
        flash("Password berhasil diubah.", "success")

    return redirect(url_for("admin_akun"))


ADMIN_EVENT_SECTION_ENDPOINTS = {
    "hero": "admin_hero",
    "lokasi": "admin_lokasi",
    "summit": "admin_summit",
    "pembicara": "admin_pembicara",
}


@app.route("/admin/event", methods=["POST"])
@admin_required
def admin_update_event():
    """Perbarui informasi acara. Setiap form kirim hanya kolom miliknya sendiri."""
    info = EventInfo.get_or_create()

    if "venue_name" in request.form:
        info.venue_name = request.form.get("venue_name", "").strip()
    if "address" in request.form:
        info.address = request.form.get("address", "").strip()
    if "event_date" in request.form:
        info.event_date = request.form.get("event_date", "").strip()

    if "maps_url" in request.form:
        maps_url = request.form.get("maps_url", "").strip()
        if maps_url and not maps_url.startswith(("http://", "https://")):
            maps_url = "https://" + maps_url
        info.maps_url = maps_url

    for field in ("hero_eyebrow", "hero_title_before", "hero_title_accent",
                  "hero_title_after", "hero_lead", "hero_note", "hero_note_prefix",
                  "subtitle", "hero_video_url", "intro_title", "intro_body"):
        if field in request.form:
            setattr(info, field, request.form.get(field, "").strip())

    if "speakers_eyebrow" in request.form:
        info.speakers_eyebrow = request.form.get("speakers_eyebrow", "").strip()
    if "speakers_title" in request.form:
        info.speakers_title = request.form.get("speakers_title", "").strip()
    if "speakers_subtitle" in request.form:
        info.speakers_subtitle = request.form.get("speakers_subtitle", "").strip()

    if "event_notes" in request.form:
        info.event_notes = request.form.get("event_notes", "").strip()

    info.save()
    flash("Informasi acara berhasil disimpan.", "success")
    endpoint = ADMIN_EVENT_SECTION_ENDPOINTS.get(request.form.get("section"), "admin_dashboard")
    return redirect(url_for(endpoint))


@app.route("/admin/keynote", methods=["POST"])
@admin_required
def admin_update_keynote():
    """Ubah judul dan isi bagian keynote pada halaman depan."""
    keynote = KeynoteSection.get_or_create()
    keynote.title = form_text("title")
    keynote.body = form_text("body")
    keynote.save()
    flash("Konten keynote berhasil disimpan.", "success")
    return redirect(url_for("admin_summit"))


@app.route("/admin/highlight/new", methods=["POST"])
@admin_required
def admin_new_highlight():
    """Tambah sorotan acara baru pada halaman depan."""
    title = form_text("title")
    description = form_text("description")
    if not title or not description:
        flash("Judul dan deskripsi sorotan wajib diisi.", "error")
        return redirect(url_for("admin_summit"))
    HighlightItem(
        title=title,
        description=description,
        sort_order=next_sort_order(HighlightItem),
    ).save()
    flash(f"Sorotan '{title}' ditambahkan.", "success")
    return redirect(url_for("admin_summit"))


@app.route("/admin/highlight/<highlight_id>/update", methods=["POST"])
@admin_required
def admin_update_highlight(highlight_id):
    """Ubah satu sorotan acara pada halaman depan."""
    item = get_or_404(HighlightItem, highlight_id)
    title = form_text("title")
    if not title:
        flash("Judul sorotan wajib diisi.", "error")
        return redirect(url_for("admin_summit"))
    item.title = title
    item.description = form_text("description")
    item.sort_order = nonnegative_int(request.form.get("sort_order"), item.sort_order)
    item.is_active = request.form.get("is_active") == "on"
    item.save()
    flash(f"Sorotan '{item.title}' berhasil disimpan.", "success")
    return redirect(url_for("admin_summit"))


@app.route("/admin/highlight/<highlight_id>/delete", methods=["POST"])
@admin_required
def admin_delete_highlight(highlight_id):
    """Hapus satu sorotan acara."""
    item = get_or_404(HighlightItem, highlight_id)
    item.delete()
    flash("Sorotan dihapus.", "success")
    return redirect(url_for("admin_summit"))


@app.route("/admin/agenda/new", methods=["POST"])
@admin_required
def admin_new_agenda():
    """Tambah satu item jadwal baru pada agenda acara."""
    time_label = form_text("time_label")
    activity = form_text("activity")
    if not time_label or not activity:
        flash("Waktu dan aktivitas agenda wajib diisi.", "error")
        return redirect(url_for("admin_summit"))
    AgendaItem(
        time_label=time_label,
        activity=activity,
        sort_order=next_sort_order(AgendaItem),
    ).save()
    flash("Item agenda ditambahkan.", "success")
    return redirect(url_for("admin_summit"))


@app.route("/admin/agenda/<agenda_id>/update", methods=["POST"])
@admin_required
def admin_update_agenda(agenda_id):
    """Ubah satu item jadwal pada agenda acara."""
    item = get_or_404(AgendaItem, agenda_id)
    time_label = form_text("time_label")
    activity = form_text("activity")
    if not time_label or not activity:
        flash("Waktu dan aktivitas agenda wajib diisi.", "error")
        return redirect(url_for("admin_summit"))
    item.time_label = time_label
    item.activity = activity
    item.sort_order = nonnegative_int(request.form.get("sort_order"), item.sort_order)
    item.save()
    flash("Item agenda berhasil disimpan.", "success")
    return redirect(url_for("admin_summit"))


@app.route("/admin/agenda/<agenda_id>/delete", methods=["POST"])
@admin_required
def admin_delete_agenda(agenda_id):
    """Hapus satu item jadwal pada agenda acara."""
    item = get_or_404(AgendaItem, agenda_id)
    item.delete()
    flash("Item agenda dihapus.", "success")
    return redirect(url_for("admin_summit"))


@app.route("/admin/reason/new", methods=["POST"])
@admin_required
def admin_new_reason():
    """Tambah alasan baru untuk bergabung sebagai tenant."""
    title = form_text("title")
    description = form_text("description")
    if not title or not description:
        flash("Judul dan deskripsi alasan wajib diisi.", "error")
        return redirect(url_for("admin_summit"))
    ReasonItem(
        title=title,
        description=description,
        sort_order=next_sort_order(ReasonItem),
    ).save()
    flash(f"Alasan '{title}' ditambahkan.", "success")
    return redirect(url_for("admin_summit"))


@app.route("/admin/reason/<reason_id>/update", methods=["POST"])
@admin_required
def admin_update_reason(reason_id):
    """Ubah satu alasan bergabung sebagai tenant."""
    item = get_or_404(ReasonItem, reason_id)
    title = form_text("title")
    if not title:
        flash("Judul alasan wajib diisi.", "error")
        return redirect(url_for("admin_summit"))
    item.title = title
    item.description = form_text("description")
    item.sort_order = nonnegative_int(request.form.get("sort_order"), item.sort_order)
    item.save()
    flash(f"Alasan '{item.title}' berhasil disimpan.", "success")
    return redirect(url_for("admin_summit"))


@app.route("/admin/reason/<reason_id>/delete", methods=["POST"])
@admin_required
def admin_delete_reason(reason_id):
    """Hapus satu alasan bergabung sebagai tenant."""
    item = get_or_404(ReasonItem, reason_id)
    item.delete()
    flash("Alasan dihapus.", "success")
    return redirect(url_for("admin_summit"))


@app.route("/admin/photo/upload", methods=["POST"])
@admin_required
def admin_upload_photo():
    """Unggah satu atau beberapa foto ke carousel halaman depan."""
    files = [f for f in request.files.getlist("photos") if f and f.filename]
    if not files:
        flash("Pilih minimal satu berkas foto terlebih dahulu.", "error")
        return redirect(url_for("admin_foto"))

    caption = request.form.get("caption", "").strip()
    max_order = next_sort_order(GalleryPhoto) - 1

    saved, rejected = 0, 0
    for f in files:
        filename = save_uploaded_photo(f)
        if not filename:
            rejected += 1
            continue
        max_order += 1
        GalleryPhoto(
            filename=filename,
            caption=caption if len(files) == 1 else "",
            sort_order=max_order,
        ).save()
        saved += 1

    if saved:
        flash(f"{saved} foto berhasil diunggah.", "success")
    if rejected:
        flash(f"{rejected} berkas ditolak - hanya JPG, PNG, WEBP, atau GIF yang diterima.", "error")
    return redirect(url_for("admin_foto"))


@app.route("/admin/photo/<photo_id>/update", methods=["POST"])
@admin_required
def admin_update_photo(photo_id):
    """Ubah keterangan, urutan, atau status tampil satu foto."""
    photo = get_or_404(GalleryPhoto, photo_id)
    sort_order = nonnegative_int(request.form.get("sort_order", photo.sort_order))
    if sort_order is None:
        flash("Urutan harus berupa angka.", "error")
        return redirect(url_for("admin_foto"))
    photo.caption = form_text("caption")
    photo.sort_order = sort_order
    photo.is_active = request.form.get("is_active") == "on"

    fit = request.form.get("fit_mode", photo.fit_mode)
    photo.fit_mode = fit if fit in ("contain", "cover") else "contain"
    for field in ("pos_x", "pos_y"):
        try:
            value = int(request.form.get(field, getattr(photo, field) or 50))
        except (TypeError, ValueError):
            value = 50
        setattr(photo, field, max(0, min(100, value)))
    photo.save()
    flash("Foto berhasil diperbarui.", "success")
    return redirect(url_for("admin_foto"))


@app.route("/admin/photo/<photo_id>/delete", methods=["POST"])
@admin_required
def admin_delete_photo(photo_id):
    """Hapus foto dari carousel beserta berkasnya."""
    photo = get_or_404(GalleryPhoto, photo_id)
    delete_photo_file(photo.filename)
    photo.delete()
    flash("Foto berhasil dihapus.", "success")
    return redirect(url_for("admin_foto"))


def _tenants_for_audience(audience, selected_ids=None):
    """
    Kembalikan daftar tenant sesuai kelompok penerima yang dipilih admin.
    Untuk audience "custom", hanya tenant yang id-nya ada di selected_ids.
    """
    if audience == "custom":
        ids = valid_object_ids(selected_ids)
        if not ids:
            return []
        return list(Tenant.objects(id__in=ids).order_by("created_at"))

    q = Tenant.objects
    if audience == "paid":
        q = q.filter(payment_status="paid")
    elif audience == "pending":
        q = q.filter(payment_status="pending")
    return list(q.order_by("created_at"))


@app.route("/admin/broadcast", methods=["POST"])
@admin_required
def admin_send_broadcast():
    """Kirim informasi tambahan lewat email ke sekelompok pendaftar."""
    subject = request.form.get("subject", "").strip()
    message = request.form.get("message", "").strip()
    audience = request.form.get("audience", "paid")

    if audience not in ("all", "paid", "pending", "custom"):
        audience = "paid"
    if not subject or not message:
        flash("Judul dan isi pesan wajib diisi.", "error")
        return redirect(url_for("admin_email"))
    if not email_is_configured():
        flash("Pengiriman email belum dikonfigurasi. Isi SMTP_USER dan SMTP_PASS di berkas .env.", "error")
        return redirect(url_for("admin_email"))

    recipients = _tenants_for_audience(audience, request.form.getlist("tenant_ids"))
    if not recipients:
        if audience == "custom":
            flash("Pilih minimal satu penerima terlebih dahulu.", "error")
        else:
            flash("Tidak ada penerima pada kelompok yang dipilih.", "error")
        return redirect(url_for("admin_email"))

    sent = 0
    for tenant in recipients:
        status_url = url_for("registration_status", order_id=tenant.order_id, _external=True)
        if send_broadcast(tenant, subject, message, status_url):
            sent += 1
    failed = len(recipients) - sent

    Broadcast(
        subject=subject,
        body=message,
        audience=audience,
        total_recipients=len(recipients),
        total_sent=sent,
        total_failed=failed,
    ).save()

    if failed:
        flash(f"Email terkirim ke {sent} dari {len(recipients)} penerima. {failed} gagal dikirim.", "error")
    else:
        flash(f"Email berhasil dikirim ke {sent} penerima.", "success")
    return redirect(url_for("admin_email"))


@app.route("/admin/speaker/new", methods=["POST"])
@admin_required
def admin_new_speaker():
    """Tambah pembicara baru beserta fotonya."""
    name = form_text("name")
    if not name:
        flash("Nama pembicara wajib diisi.", "error")
        return redirect(url_for("admin_pembicara"))

    filename = ""
    upload = request.files.get("photo")
    if upload and upload.filename:
        filename = save_uploaded_photo(upload) or ""
        if not filename:
            flash("Foto ditolak - hanya JPG, PNG, WEBP, atau GIF yang diterima.", "error")

    Speaker(
        name=name,
        institution=form_text("institution"),
        topic=form_text("topic"),
        photo=filename,
        sort_order=next_sort_order(Speaker),
    ).save()
    flash(f"Pembicara '{name}' ditambahkan.", "success")
    return redirect(url_for("admin_pembicara"))


@app.route("/admin/speaker/<speaker_id>/update", methods=["POST"])
@admin_required
def admin_update_speaker(speaker_id):
    """Perbarui data pembicara; foto lama diganti hanya bila ada unggahan baru."""
    speaker = get_or_404(Speaker, speaker_id)
    name = form_text("name", speaker.name)
    sort_order = nonnegative_int(request.form.get("sort_order", speaker.sort_order))
    if not name:
        flash("Nama pembicara wajib diisi.", "error")
        return redirect(url_for("admin_pembicara"))
    if sort_order is None:
        flash("Urutan harus berupa angka.", "error")
        return redirect(url_for("admin_pembicara"))
    speaker.name = name
    speaker.institution = form_text("institution")
    speaker.topic = form_text("topic")
    speaker.sort_order = sort_order
    speaker.is_active = request.form.get("is_active") == "on"

    for field in ("pos_x", "pos_y"):
        try:
            value = int(request.form.get(field, getattr(speaker, field) or 50))
        except (TypeError, ValueError):
            value = 50
        setattr(speaker, field, max(0, min(100, value)))

    upload = request.files.get("photo")
    if upload and upload.filename:
        filename = save_uploaded_photo(upload)
        if filename:
            delete_photo_file(speaker.photo)
            speaker.photo = filename
        else:
            flash("Foto ditolak - hanya JPG, PNG, WEBP, atau GIF yang diterima.", "error")

    speaker.save()
    flash(f"Data pembicara '{speaker.name}' disimpan.", "success")
    return redirect(url_for("admin_pembicara"))


@app.route("/admin/speaker/<speaker_id>/delete", methods=["POST"])
@admin_required
def admin_delete_speaker(speaker_id):
    """Hapus pembicara beserta fotonya."""
    speaker = get_or_404(Speaker, speaker_id)
    delete_photo_file(speaker.photo)
    name = speaker.name
    speaker.delete()
    flash(f"Pembicara '{name}' dihapus.", "success")
    return redirect(url_for("admin_pembicara"))


@app.route("/admin/tenant/<tenant_id>/status", methods=["POST"])
@admin_required
def admin_update_tenant_status(tenant_id):
    """Override manual status pembayaran, misalnya untuk pembayaran offline/khusus."""
    tenant = get_or_404(Tenant, tenant_id)
    new_status = request.form.get("payment_status")
    confirm_password = request.form.get("confirm_password", "")

    admin = get_or_404(AdminUser, session["admin_id"])
    if not check_password_hash(admin.password_hash, confirm_password):
        flash("Password salah. Status pembayaran tidak diubah.", "error")
        return redirect(url_for("admin_pendaftaran"))

    if new_status not in ("pending", "paid", "expired", "cancelled", "failed", "refunded"):
        flash("Status pembayaran tidak valid.", "error")
        return redirect(url_for("admin_pendaftaran"))

    was_paid = tenant.payment_status == "paid"
    tenant.payment_status = new_status
    if new_status == "paid" and not tenant.paid_at:
        tenant.paid_at = datetime.utcnow()
    if new_status == "paid":
        tenant.ensure_checkin_token()
    tenant.save()
    flash(f"Status pendaftaran {tenant.order_id} diperbarui menjadi '{new_status}'.", "success")

    # Pembayaran offline/khusus yang di-acc manual juga dikirimi bukti lunas.
    if new_status == "paid" and not was_paid:
        if send_payment_success(tenant, url_for("registration_status",
                                                order_id=tenant.order_id, _external=True)):
            flash(f"Email bukti lunas dikirim ke {tenant.email}.", "success")
    return redirect(url_for("admin_pendaftaran"))


@app.route("/admin/tenant/<tenant_id>/delete", methods=["POST"])
@admin_required
def admin_delete_tenant(tenant_id):
    """
    Hapus satu pendaftaran secara permanen.

    Dipakai untuk membersihkan data uji atau pendaftaran ganda. Riwayat
    pembayaran di Midtrans tidak ikut terhapus - pengembalian dana, bila perlu,
    tetap dilakukan lewat dasbor Midtrans.
    """
    tenant = get_or_404(Tenant, tenant_id)
    order_id = tenant.order_id
    tenant.delete()
    flash(f"Pendaftaran {order_id} telah dihapus.", "success")
    return redirect(url_for("admin_pendaftaran"))


@app.errorhandler(413)
def file_too_large(e):
    flash("Ukuran berkas terlalu besar. Maksimal 5 MB per foto.", "error")
    return redirect(url_for("admin_dashboard"))


seed_defaults()


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
