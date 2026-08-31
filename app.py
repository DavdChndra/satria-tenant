import io
import os
import secrets
from functools import wraps
from datetime import datetime

from dotenv import load_dotenv
from flask import (Flask, render_template, request, jsonify, redirect,
                   url_for, session, flash, Response, abort)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

from models import (db, BoothType, Tenant, AdminUser, EventInfo,
                    GalleryPhoto, Broadcast, Speaker)
from midtrans_service import create_transaction, verify_notification_signature, map_transaction_status
from email_service import (send_registration_received, send_payment_success,
                           send_broadcast, is_configured as email_is_configured)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{os.path.join(BASE_DIR, 'satria.db')}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-ganti-di-produksi")
app.config["MIDTRANS_CLIENT_KEY"] = os.environ.get("MIDTRANS_CLIENT_KEY", "")
app.config["MIDTRANS_IS_PRODUCTION"] = os.environ.get("MIDTRANS_IS_PRODUCTION", "false").lower() == "true"

UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
ALLOWED_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # batas unggahan 5 MB
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Warna penanda tiap jenis booth pada kartu pratinjau di halaman depan
BOOTH_COLORS = ["#2563EB", "#1F8A5B", "#E0722F", "#6D28D9"]

db.init_app(app)


# ---------- helper ----------

def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin_id"):
            return redirect(url_for("admin_login"))
        return view(*args, **kwargs)
    return wrapped


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
    if BoothType.query.count() == 0:
        db.session.add_all([
            BoothType(name="Booth standar", description="Ruang pameran 2x2 meter, meja, dua kursi.",
                       price=1500000, quota=20, sort_order=1),
            BoothType(name="Booth premium", description="Ruang pameran 3x3 meter, signage, slot demo panggung utama.",
                       price=2750000, quota=10, sort_order=2),
        ])
    if EventInfo.query.count() == 0:
        db.session.add(EventInfo(
            venue_name="Gedung Serbaguna Telkom University",
            address="Jl. Telekomunikasi No. 1, Terusan Buahbatu, Bandung, Jawa Barat 40257",
            event_date="15 - 17 Mei 2026",
            maps_url="https://maps.google.com/?q=Telkom+University+Bandung",
        ))
    if AdminUser.query.count() == 0:
        db.session.add(AdminUser(
            username="admin",
            password_hash=generate_password_hash("ubah-password-ini"),
        ))
    db.session.commit()


# ---------- halaman publik ----------

@app.route("/")
def index():
    booth_types = (BoothType.query
                   .filter_by(is_active=True)
                   .order_by(BoothType.sort_order)
                   .all())
    photos = (GalleryPhoto.query
              .filter_by(is_active=True)
              .order_by(GalleryPhoto.sort_order, GalleryPhoto.id)
              .all())
    speakers = (Speaker.query
                .filter_by(is_active=True)
                .order_by(Speaker.sort_order, Speaker.id)
                .all())
    return render_template("index.html",
                           booth_types=booth_types,
                           photos=photos,
                           speakers=speakers,
                           event_info=EventInfo.get_or_create(),
                           total_remaining=sum(b.slots_remaining for b in booth_types),
                           booth_colors=BOOTH_COLORS)


@app.route("/api/register", methods=["POST"])
def api_register():
    data = request.get_json(force=True) or {}

    required = ["institution_name", "pic_name", "email", "phone", "booth_type_id"]
    missing = [f for f in required if not str(data.get(f, "")).strip()]
    if missing:
        return jsonify({"error": f"Field wajib belum diisi: {', '.join(missing)}"}), 400

    booth = BoothType.query.get(data["booth_type_id"])
    if not booth or not booth.is_active:
        return jsonify({"error": "Jenis booth tidak ditemukan atau tidak aktif."}), 400
    if booth.slots_remaining <= 0:
        return jsonify({"error": "Kuota booth ini sudah penuh."}), 400

    order_id = Tenant.generate_order_id()
    tenant = Tenant(
        order_id=order_id,
        institution_name=data["institution_name"].strip(),
        pic_name=data["pic_name"].strip(),
        email=data["email"].strip(),
        phone=data["phone"].strip(),
        booth_type_id=booth.id,
        price_at_registration=booth.price,
        description=str(data.get("description", "")).strip(),
        payment_status="pending",
    )
    db.session.add(tenant)
    db.session.commit()

    try:
        result = create_transaction(
            order_id=order_id,
            gross_amount=booth.price,
            customer={
                "first_name": tenant.pic_name,
                "email": tenant.email,
                "phone": tenant.phone,
            },
            item_name=f"Pendaftaran {booth.name} - SATRIA 2026",
        )
    except Exception as exc:
        return jsonify({"error": f"Gagal membuat transaksi Midtrans: {exc}"}), 502

    tenant.snap_token = result.get("token", "")
    tenant.midtrans_order_id = order_id
    db.session.commit()

    send_registration_received(tenant, url_for("registration_status", order_id=order_id, _external=True))

    return jsonify({
        "order_id": order_id,
        "snap_token": result.get("token"),
        "redirect_url": result.get("redirect_url"),
    })


@app.route("/status/<order_id>")
def registration_status(order_id):
    tenant = Tenant.query.filter_by(order_id=order_id).first_or_404()
    return render_template("status.html", tenant=tenant)


@app.route("/api/pay/<order_id>", methods=["POST"])
def api_resume_payment(order_id):
    """
    Buka kembali jendela pembayaran untuk pendaftaran yang belum lunas.
    Token lama dipakai ulang; bila sudah tidak berlaku, dibuatkan yang baru.
    """
    tenant = Tenant.query.filter_by(order_id=order_id).first_or_404()

    if tenant.payment_status == "paid":
        return jsonify({"error": "Pendaftaran ini sudah lunas."}), 400
    if tenant.payment_status in ("cancelled", "refunded"):
        return jsonify({"error": "Pendaftaran ini sudah dibatalkan."}), 400

    if tenant.snap_token:
        return jsonify({"snap_token": tenant.snap_token, "order_id": tenant.order_id})

    # Midtrans menolak order_id yang sudah pernah dipakai, jadi transaksi baru
    # memakai nomor baru. Nomor pendaftaran (order_id) sengaja TIDAK diubah
    # agar tautan status yang sudah disalin pendaftar tetap berlaku.
    new_midtrans_id = Tenant.generate_order_id()
    try:
        result = create_transaction(
            order_id=new_midtrans_id,
            gross_amount=tenant.price_at_registration,
            customer={"first_name": tenant.pic_name,
                      "email": tenant.email,
                      "phone": tenant.phone},
            item_name=f"Pendaftaran {tenant.booth_type.name} - SATRIA 2026",
        )
    except Exception as exc:
        return jsonify({"error": f"Gagal membuat transaksi: {exc}"}), 502

    tenant.midtrans_order_id = new_midtrans_id
    tenant.snap_token = result.get("token", "")
    db.session.commit()
    return jsonify({"snap_token": tenant.snap_token, "order_id": tenant.order_id})


@app.route("/ticket/<order_id>/qr.svg")
def ticket_qr(order_id):
    """Gambar QR tiket masuk. Isinya token acak, bukan nomor pendaftaran."""
    tenant = Tenant.query.filter_by(order_id=order_id).first_or_404()
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
    """Pratinjau ID card peserta — hanya untuk pendaftaran yang sudah lunas."""
    tenant = Tenant.query.filter_by(order_id=order_id).first_or_404()
    if tenant.payment_status != "paid":
        flash("Kartu peserta terbit setelah pembayaran lunas.")
        return redirect(url_for("registration_status", order_id=order_id))
    tenant.ensure_checkin_token()
    db.session.commit()
    return render_template("ticket.html", tenant=tenant,
                           event_info=EventInfo.get_or_create())


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

    if not all([order_id, status_code, gross_amount, signature_key]):
        return jsonify({"error": "Payload tidak lengkap"}), 400

    if not verify_notification_signature(order_id, status_code, gross_amount, signature_key):
        return jsonify({"error": "Signature tidak valid"}), 403

    # Midtrans mengirim nomor transaksi yang sedang berjalan. Untuk pendaftaran
    # yang pembayarannya pernah diulang, nomor itu ada di midtrans_order_id.
    tenant = (Tenant.query.filter_by(midtrans_order_id=order_id).first()
              or Tenant.query.filter_by(order_id=order_id).first())
    if not tenant:
        return jsonify({"error": "Order tidak ditemukan"}), 404

    new_status = map_transaction_status(transaction_status, fraud_status)
    was_paid = tenant.payment_status == "paid"
    tenant.payment_status = new_status
    tenant.payment_type = payment_type
    tenant.midtrans_transaction_id = payload.get("transaction_id")
    if new_status == "paid" and not tenant.paid_at:
        tenant.paid_at = datetime.utcnow()
    if new_status == "paid":
        tenant.ensure_checkin_token()
    db.session.commit()

    # Midtrans dapat mengirim notifikasi yang sama berulang kali;
    # email lunas hanya dikirim pada perubahan status pertama ke "paid".
    if new_status == "paid" and not was_paid:
        send_payment_success(tenant, url_for("registration_status",
                                             order_id=tenant.order_id, _external=True))

    return jsonify({"ok": True})


# ---------- admin ----------

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        user = AdminUser.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            session["admin_id"] = user.id
            return redirect(url_for("admin_dashboard"))
        flash("Username atau password salah.")
    return render_template("admin/login.html")


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_id", None)
    return redirect(url_for("admin_login"))


@app.route("/admin")
@admin_required
def admin_dashboard():
    tenants = Tenant.query.order_by(Tenant.created_at.desc()).all()
    booth_types = BoothType.query.order_by(BoothType.sort_order).all()

    total_paid = sum(t.price_at_registration for t in tenants if t.payment_status == "paid")
    total_pending = sum(1 for t in tenants if t.payment_status == "pending")
    total_registrations = len(tenants)

    photos = GalleryPhoto.query.order_by(GalleryPhoto.sort_order, GalleryPhoto.id).all()
    broadcasts = Broadcast.query.order_by(Broadcast.created_at.desc()).limit(10).all()
    speakers = Speaker.query.order_by(Speaker.sort_order, Speaker.id).all()

    return render_template(
        "admin/dashboard.html",
        tenants=tenants,
        booth_types=booth_types,
        photos=photos,
        speakers=speakers,
        broadcasts=broadcasts,
        email_ready=email_is_configured(),
        count_all=len(tenants),
        count_paid=sum(1 for t in tenants if t.payment_status == "paid"),
        count_pending=total_pending,
        event_info=EventInfo.get_or_create(),
        total_paid=total_paid,
        total_pending=total_pending,
        total_registrations=total_registrations,
    )


@app.route("/admin/scan")
@admin_required
def admin_scan():
    """Halaman pemindai QR untuk validasi peserta di hari pelaksanaan."""
    checked_in = (Tenant.query
                  .filter(Tenant.checked_in_at.isnot(None))
                  .order_by(Tenant.checked_in_at.desc())
                  .limit(15)
                  .all())
    total_paid = Tenant.query.filter_by(payment_status="paid").count()
    total_in = Tenant.query.filter(Tenant.checked_in_at.isnot(None)).count()
    return render_template("admin/scan.html",
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

    tenant = Tenant.query.filter_by(checkin_token=token).first()
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
        db.session.commit()

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


@app.route("/admin/scan/reset/<int:tenant_id>", methods=["POST"])
@admin_required
def admin_scan_reset(tenant_id):
    """Batalkan status hadir, misalnya bila salah pindai."""
    tenant = Tenant.query.get_or_404(tenant_id)
    tenant.checked_in_at = None
    db.session.commit()
    flash(f"Status hadir {tenant.order_id} dibatalkan.")
    return redirect(url_for("admin_scan"))


@app.route("/admin/booth/<int:booth_id>/update", methods=["POST"])
@admin_required
def admin_update_booth(booth_id):
    booth = BoothType.query.get_or_404(booth_id)
    booth.name = request.form.get("name", booth.name).strip()
    booth.description = request.form.get("description", booth.description)
    try:
        booth.price = int(request.form.get("price", booth.price))
        booth.quota = int(request.form.get("quota", booth.quota))
    except ValueError:
        flash("Harga dan kuota harus berupa angka.")
        return redirect(url_for("admin_dashboard"))
    booth.is_active = request.form.get("is_active") == "on"
    db.session.commit()
    flash(f"Pengaturan '{booth.name}' berhasil disimpan.")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/booth/new", methods=["POST"])
@admin_required
def admin_new_booth():
    try:
        price = int(request.form.get("price", 0))
        quota = int(request.form.get("quota", 0))
    except ValueError:
        flash("Harga dan kuota harus berupa angka.")
        return redirect(url_for("admin_dashboard"))
    name = request.form.get("name", "").strip()
    if not name:
        flash("Nama jenis booth wajib diisi.")
        return redirect(url_for("admin_dashboard"))
    max_order = db.session.query(db.func.max(BoothType.sort_order)).scalar() or 0
    db.session.add(BoothType(
        name=name,
        description=request.form.get("description", ""),
        price=price,
        quota=quota,
        sort_order=max_order + 1,
    ))
    db.session.commit()
    flash(f"Jenis booth '{name}' ditambahkan.")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/event", methods=["POST"])
@admin_required
def admin_update_event():
    """Perbarui informasi lokasi dan tanggal acara."""
    info = EventInfo.get_or_create()
    info.venue_name = request.form.get("venue_name", "").strip()
    info.address = request.form.get("address", "").strip()
    info.event_date = request.form.get("event_date", "").strip()

    maps_url = request.form.get("maps_url", "").strip()
    if maps_url and not maps_url.startswith(("http://", "https://")):
        maps_url = "https://" + maps_url
    info.maps_url = maps_url

    for field in ("hero_eyebrow", "hero_title_before", "hero_title_accent",
                  "hero_title_after", "hero_lead", "hero_note", "hero_note_prefix"):
        setattr(info, field, request.form.get(field, "").strip())

    info.speakers_eyebrow = request.form.get("speakers_eyebrow", "").strip()
    info.speakers_title = request.form.get("speakers_title", "").strip()
    info.speakers_subtitle = request.form.get("speakers_subtitle", "").strip()

    db.session.commit()
    flash("Informasi lokasi acara berhasil disimpan.")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/photo/upload", methods=["POST"])
@admin_required
def admin_upload_photo():
    """Unggah satu atau beberapa foto ke carousel halaman depan."""
    files = [f for f in request.files.getlist("photos") if f and f.filename]
    if not files:
        flash("Pilih minimal satu berkas foto terlebih dahulu.")
        return redirect(url_for("admin_dashboard"))

    caption = request.form.get("caption", "").strip()
    max_order = db.session.query(db.func.max(GalleryPhoto.sort_order)).scalar() or 0

    saved, rejected = 0, 0
    for f in files:
        filename = save_uploaded_photo(f)
        if not filename:
            rejected += 1
            continue
        max_order += 1
        db.session.add(GalleryPhoto(
            filename=filename,
            caption=caption if len(files) == 1 else "",
            sort_order=max_order,
        ))
        saved += 1
    db.session.commit()

    if saved:
        flash(f"{saved} foto berhasil diunggah.")
    if rejected:
        flash(f"{rejected} berkas ditolak — hanya JPG, PNG, WEBP, atau GIF yang diterima.")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/photo/<int:photo_id>/update", methods=["POST"])
@admin_required
def admin_update_photo(photo_id):
    """Ubah keterangan, urutan, atau status tampil satu foto."""
    photo = GalleryPhoto.query.get_or_404(photo_id)
    photo.caption = request.form.get("caption", "").strip()
    try:
        photo.sort_order = int(request.form.get("sort_order", photo.sort_order))
    except ValueError:
        flash("Urutan harus berupa angka.")
        return redirect(url_for("admin_dashboard"))
    photo.is_active = request.form.get("is_active") == "on"

    fit = request.form.get("fit_mode", photo.fit_mode)
    photo.fit_mode = fit if fit in ("contain", "cover") else "contain"
    for field in ("pos_x", "pos_y"):
        try:
            value = int(request.form.get(field, getattr(photo, field) or 50))
        except (TypeError, ValueError):
            value = 50
        setattr(photo, field, max(0, min(100, value)))
    db.session.commit()
    flash("Foto berhasil diperbarui.")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/photo/<int:photo_id>/delete", methods=["POST"])
@admin_required
def admin_delete_photo(photo_id):
    """Hapus foto dari carousel beserta berkasnya."""
    photo = GalleryPhoto.query.get_or_404(photo_id)
    delete_photo_file(photo.filename)
    db.session.delete(photo)
    db.session.commit()
    flash("Foto berhasil dihapus.")
    return redirect(url_for("admin_dashboard"))


def _tenants_for_audience(audience, selected_ids=None):
    """
    Kembalikan daftar tenant sesuai kelompok penerima yang dipilih admin.
    Untuk audience "custom", hanya tenant yang id-nya ada di selected_ids.
    """
    if audience == "custom":
        ids = [i for i in (selected_ids or []) if str(i).isdigit()]
        if not ids:
            return []
        return (Tenant.query
                .filter(Tenant.id.in_([int(i) for i in ids]))
                .order_by(Tenant.created_at)
                .all())

    q = Tenant.query
    if audience == "paid":
        q = q.filter_by(payment_status="paid")
    elif audience == "pending":
        q = q.filter_by(payment_status="pending")
    return q.order_by(Tenant.created_at).all()


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
        flash("Judul dan isi pesan wajib diisi.")
        return redirect(url_for("admin_dashboard"))
    if not email_is_configured():
        flash("Pengiriman email belum dikonfigurasi. Isi SMTP_USER dan SMTP_PASS di berkas .env.")
        return redirect(url_for("admin_dashboard"))

    recipients = _tenants_for_audience(audience, request.form.getlist("tenant_ids"))
    if not recipients:
        if audience == "custom":
            flash("Pilih minimal satu penerima terlebih dahulu.")
        else:
            flash("Tidak ada penerima pada kelompok yang dipilih.")
        return redirect(url_for("admin_dashboard"))

    sent = 0
    for tenant in recipients:
        status_url = url_for("registration_status", order_id=tenant.order_id, _external=True)
        if send_broadcast(tenant, subject, message, status_url):
            sent += 1
    failed = len(recipients) - sent

    db.session.add(Broadcast(
        subject=subject,
        body=message,
        audience=audience,
        total_recipients=len(recipients),
        total_sent=sent,
        total_failed=failed,
    ))
    db.session.commit()

    if failed:
        flash(f"Email terkirim ke {sent} dari {len(recipients)} penerima. {failed} gagal dikirim.")
    else:
        flash(f"Email berhasil dikirim ke {sent} penerima.")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/speaker/new", methods=["POST"])
@admin_required
def admin_new_speaker():
    """Tambah pembicara baru beserta fotonya."""
    name = request.form.get("name", "").strip()
    if not name:
        flash("Nama pembicara wajib diisi.")
        return redirect(url_for("admin_dashboard"))

    filename = ""
    upload = request.files.get("photo")
    if upload and upload.filename:
        filename = save_uploaded_photo(upload) or ""
        if not filename:
            flash("Foto ditolak — hanya JPG, PNG, WEBP, atau GIF yang diterima.")

    max_order = db.session.query(db.func.max(Speaker.sort_order)).scalar() or 0
    db.session.add(Speaker(
        name=name,
        institution=request.form.get("institution", "").strip(),
        topic=request.form.get("topic", "").strip(),
        photo=filename,
        sort_order=max_order + 1,
    ))
    db.session.commit()
    flash(f"Pembicara '{name}' ditambahkan.")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/speaker/<int:speaker_id>/update", methods=["POST"])
@admin_required
def admin_update_speaker(speaker_id):
    """Perbarui data pembicara; foto lama diganti hanya bila ada unggahan baru."""
    speaker = Speaker.query.get_or_404(speaker_id)
    speaker.name = request.form.get("name", speaker.name).strip()
    speaker.institution = request.form.get("institution", "").strip()
    speaker.topic = request.form.get("topic", "").strip()
    try:
        speaker.sort_order = int(request.form.get("sort_order", speaker.sort_order))
    except ValueError:
        flash("Urutan harus berupa angka.")
        return redirect(url_for("admin_dashboard"))
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
            flash("Foto ditolak — hanya JPG, PNG, WEBP, atau GIF yang diterima.")

    db.session.commit()
    flash(f"Data pembicara '{speaker.name}' disimpan.")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/speaker/<int:speaker_id>/delete", methods=["POST"])
@admin_required
def admin_delete_speaker(speaker_id):
    """Hapus pembicara beserta fotonya."""
    speaker = Speaker.query.get_or_404(speaker_id)
    delete_photo_file(speaker.photo)
    name = speaker.name
    db.session.delete(speaker)
    db.session.commit()
    flash(f"Pembicara '{name}' dihapus.")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/tenant/<int:tenant_id>/status", methods=["POST"])
@admin_required
def admin_update_tenant_status(tenant_id):
    """Override manual status pembayaran, misalnya untuk pembayaran offline/khusus."""
    tenant = Tenant.query.get_or_404(tenant_id)
    new_status = request.form.get("payment_status")
    if new_status in ("pending", "paid", "expired", "cancelled", "failed", "refunded"):
        was_paid = tenant.payment_status == "paid"
        tenant.payment_status = new_status
        if new_status == "paid" and not tenant.paid_at:
            tenant.paid_at = datetime.utcnow()
        if new_status == "paid":
            tenant.ensure_checkin_token()
        db.session.commit()
        flash(f"Status pendaftaran {tenant.order_id} diperbarui menjadi '{new_status}'.")

        # Pembayaran offline/khusus yang di-acc manual juga dikirimi bukti lunas.
        if new_status == "paid" and not was_paid:
            if send_payment_success(tenant, url_for("registration_status",
                                                    order_id=tenant.order_id, _external=True)):
                flash(f"Email bukti lunas dikirim ke {tenant.email}.")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/tenant/<int:tenant_id>/delete", methods=["POST"])
@admin_required
def admin_delete_tenant(tenant_id):
    """
    Hapus satu pendaftaran secara permanen.

    Dipakai untuk membersihkan data uji atau pendaftaran ganda. Riwayat
    pembayaran di Midtrans tidak ikut terhapus — pengembalian dana, bila perlu,
    tetap dilakukan lewat dasbor Midtrans.
    """
    tenant = Tenant.query.get_or_404(tenant_id)
    order_id = tenant.order_id
    db.session.delete(tenant)
    db.session.commit()
    flash(f"Pendaftaran {order_id} telah dihapus.")
    return redirect(url_for("admin_dashboard"))


@app.errorhandler(413)
def file_too_large(e):
    flash("Ukuran berkas terlalu besar. Maksimal 5 MB per foto.")
    return redirect(url_for("admin_dashboard"))


with app.app_context():
    db.create_all()
    seed_defaults()


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
