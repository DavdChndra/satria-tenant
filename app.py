import csv
import io
import os
import secrets
from functools import wraps
from datetime import datetime

import mongoengine as me
from bson.errors import InvalidId
from dotenv import load_dotenv
from flask import (Flask, render_template, request, jsonify, redirect,
                   url_for, session, flash, Response, abort)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

from models import (BoothType, Tenant, AdminUser, EventInfo,
                    GalleryPhoto, Broadcast, Speaker, AddOn, SelectedAddOn)
from midtrans_service import (create_transaction, verify_notification_signature,
                              map_transaction_status, get_transaction_status)
from email_service import (send_registration_received, send_payment_success,
                           send_broadcast, is_configured as email_is_configured)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

app = Flask(__name__)
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

MONGODB_URI = os.environ.get("MONGODB_URI")
if not MONGODB_URI:
    raise RuntimeError(
        "MONGODB_URI belum diisi di .env. Contoh: "
        "mongodb+srv://user:password@cluster.mongodb.net/satria"
    )
me.connect(host=MONGODB_URI)


# ---------- helper ----------

def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin_id"):
            return redirect(url_for("admin_login"))
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


# ---------- halaman publik ----------

@app.route("/")
def index():
    booth_types = BoothType.objects(is_active=True).order_by("sort_order")
    photos = GalleryPhoto.objects(is_active=True).order_by("sort_order", "id")
    speakers = Speaker.objects(is_active=True).order_by("sort_order", "id")
    add_ons = AddOn.objects(is_active=True).order_by("sort_order", "id")
    return render_template("index.html",
                           booth_types=booth_types,
                           photos=photos,
                           speakers=speakers,
                           add_ons=add_ons,
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

    booth = get_or_none(BoothType, data["booth_type_id"])
    if not booth or not booth.is_active:
        return jsonify({"error": "Jenis booth tidak ditemukan atau tidak aktif."}), 400
    if booth.slots_remaining <= 0:
        return jsonify({"error": "Kuota booth ini sudah penuh."}), 400

    requested_addon_ids = valid_object_ids(data.get("add_on_ids") or [])
    selected_add_ons = []
    if requested_addon_ids:
        selected_add_ons = list(AddOn.objects(id__in=requested_addon_ids, is_active=True))

    order_id = Tenant.generate_order_id()
    tenant = Tenant(
        order_id=order_id,
        institution_name=data["institution_name"].strip(),
        pic_name=data["pic_name"].strip(),
        email=data["email"].strip(),
        phone=data["phone"].strip(),
        booth_type=booth,
        price_at_registration=booth.price,
        description=str(data.get("description", "")).strip(),
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
    """Pratinjau ID card peserta — hanya untuk pendaftaran yang sudah lunas."""
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

    if not all([order_id, status_code, gross_amount, signature_key]):
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
            session["admin_id"] = str(user.id)
            return redirect(url_for("admin_dashboard"))
        flash("Username atau password salah.", "error")
    return render_template("admin/login.html")


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_id", None)
    return redirect(url_for("admin_login"))


@app.route("/admin")
@admin_required
def admin_dashboard():
    tenants = list(Tenant.objects.order_by("-created_at"))
    booth_types = BoothType.objects.order_by("sort_order")

    total_paid = sum(t.total_amount for t in tenants if t.payment_status == "paid")
    total_pending = sum(1 for t in tenants if t.payment_status == "pending")
    total_registrations = len(tenants)

    photos = GalleryPhoto.objects.order_by("sort_order", "id")
    broadcasts = Broadcast.objects.order_by("-created_at").limit(10)
    speakers = Speaker.objects.order_by("sort_order", "id")
    add_ons = AddOn.objects.order_by("sort_order", "id")

    return render_template(
        "admin/dashboard.html",
        tenants=tenants,
        booth_types=booth_types,
        photos=photos,
        speakers=speakers,
        add_ons=add_ons,
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
    booth.name = request.form.get("name", booth.name).strip()
    booth.description = request.form.get("description", booth.description)
    try:
        booth.price = int(request.form.get("price", booth.price))
        booth.quota = int(request.form.get("quota", booth.quota))
    except ValueError:
        flash("Harga dan kuota harus berupa angka.", "error")
        return redirect(url_for("admin_dashboard"))
    booth.is_active = request.form.get("is_active") == "on"
    booth.save()
    flash(f"Pengaturan '{booth.name}' berhasil disimpan.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/booth/new", methods=["POST"])
@admin_required
def admin_new_booth():
    try:
        price = int(request.form.get("price", 0))
        quota = int(request.form.get("quota", 0))
    except ValueError:
        flash("Harga dan kuota harus berupa angka.", "error")
        return redirect(url_for("admin_dashboard"))
    name = request.form.get("name", "").strip()
    if not name:
        flash("Nama jenis booth wajib diisi.", "error")
        return redirect(url_for("admin_dashboard"))
    BoothType(
        name=name,
        description=request.form.get("description", ""),
        price=price,
        quota=quota,
        sort_order=next_sort_order(BoothType),
    ).save()
    flash(f"Jenis booth '{name}' ditambahkan.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/addon/<addon_id>/update", methods=["POST"])
@admin_required
def admin_update_addon(addon_id):
    """Ubah nama, deskripsi, harga, atau status aktif satu opsi tambahan."""
    addon = get_or_404(AddOn, addon_id)
    name = request.form.get("name", "").strip()
    if not name:
        flash("Nama opsi tambahan wajib diisi.", "error")
        return redirect(url_for("admin_dashboard", _anchor="panel-tambahan"))
    try:
        addon.price = int(request.form.get("price", addon.price))
    except ValueError:
        flash("Harga harus berupa angka.", "error")
        return redirect(url_for("admin_dashboard", _anchor="panel-tambahan"))
    addon.name = name
    addon.description = request.form.get("description", "").strip()
    addon.is_active = request.form.get("is_active") == "on"
    addon.save()
    flash(f"Opsi tambahan '{addon.name}' berhasil disimpan.", "success")
    return redirect(url_for("admin_dashboard", _anchor="panel-tambahan"))


@app.route("/admin/addon/new", methods=["POST"])
@admin_required
def admin_new_addon():
    """Tambah opsi tambahan baru (mis. dinner, cetak poster)."""
    name = request.form.get("name", "").strip()
    if not name:
        flash("Nama opsi tambahan wajib diisi.", "error")
        return redirect(url_for("admin_dashboard", _anchor="panel-tambahan"))
    try:
        price = int(request.form.get("price", 0))
    except ValueError:
        flash("Harga harus berupa angka.", "error")
        return redirect(url_for("admin_dashboard", _anchor="panel-tambahan"))
    AddOn(
        name=name,
        description=request.form.get("description", "").strip(),
        price=price,
        sort_order=next_sort_order(AddOn),
    ).save()
    flash(f"Opsi tambahan '{name}' ditambahkan.", "success")
    return redirect(url_for("admin_dashboard", _anchor="panel-tambahan"))


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

    return redirect(url_for("admin_dashboard", _anchor="panel-akun"))


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

    info.event_notes = request.form.get("event_notes", "").strip()

    info.save()
    flash("Informasi lokasi acara berhasil disimpan.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/photo/upload", methods=["POST"])
@admin_required
def admin_upload_photo():
    """Unggah satu atau beberapa foto ke carousel halaman depan."""
    files = [f for f in request.files.getlist("photos") if f and f.filename]
    if not files:
        flash("Pilih minimal satu berkas foto terlebih dahulu.", "error")
        return redirect(url_for("admin_dashboard"))

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
        flash(f"{rejected} berkas ditolak — hanya JPG, PNG, WEBP, atau GIF yang diterima.", "error")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/photo/<photo_id>/update", methods=["POST"])
@admin_required
def admin_update_photo(photo_id):
    """Ubah keterangan, urutan, atau status tampil satu foto."""
    photo = get_or_404(GalleryPhoto, photo_id)
    photo.caption = request.form.get("caption", "").strip()
    try:
        photo.sort_order = int(request.form.get("sort_order", photo.sort_order))
    except ValueError:
        flash("Urutan harus berupa angka.", "error")
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
    photo.save()
    flash("Foto berhasil diperbarui.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/photo/<photo_id>/delete", methods=["POST"])
@admin_required
def admin_delete_photo(photo_id):
    """Hapus foto dari carousel beserta berkasnya."""
    photo = get_or_404(GalleryPhoto, photo_id)
    delete_photo_file(photo.filename)
    photo.delete()
    flash("Foto berhasil dihapus.", "success")
    return redirect(url_for("admin_dashboard"))


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
        return redirect(url_for("admin_dashboard"))
    if not email_is_configured():
        flash("Pengiriman email belum dikonfigurasi. Isi SMTP_USER dan SMTP_PASS di berkas .env.", "error")
        return redirect(url_for("admin_dashboard"))

    recipients = _tenants_for_audience(audience, request.form.getlist("tenant_ids"))
    if not recipients:
        if audience == "custom":
            flash("Pilih minimal satu penerima terlebih dahulu.", "error")
        else:
            flash("Tidak ada penerima pada kelompok yang dipilih.", "error")
        return redirect(url_for("admin_dashboard"))

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
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/speaker/new", methods=["POST"])
@admin_required
def admin_new_speaker():
    """Tambah pembicara baru beserta fotonya."""
    name = request.form.get("name", "").strip()
    if not name:
        flash("Nama pembicara wajib diisi.", "error")
        return redirect(url_for("admin_dashboard"))

    filename = ""
    upload = request.files.get("photo")
    if upload and upload.filename:
        filename = save_uploaded_photo(upload) or ""
        if not filename:
            flash("Foto ditolak — hanya JPG, PNG, WEBP, atau GIF yang diterima.", "error")

    Speaker(
        name=name,
        institution=request.form.get("institution", "").strip(),
        topic=request.form.get("topic", "").strip(),
        photo=filename,
        sort_order=next_sort_order(Speaker),
    ).save()
    flash(f"Pembicara '{name}' ditambahkan.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/speaker/<speaker_id>/update", methods=["POST"])
@admin_required
def admin_update_speaker(speaker_id):
    """Perbarui data pembicara; foto lama diganti hanya bila ada unggahan baru."""
    speaker = get_or_404(Speaker, speaker_id)
    speaker.name = request.form.get("name", speaker.name).strip()
    speaker.institution = request.form.get("institution", "").strip()
    speaker.topic = request.form.get("topic", "").strip()
    try:
        speaker.sort_order = int(request.form.get("sort_order", speaker.sort_order))
    except ValueError:
        flash("Urutan harus berupa angka.", "error")
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
            flash("Foto ditolak — hanya JPG, PNG, WEBP, atau GIF yang diterima.", "error")

    speaker.save()
    flash(f"Data pembicara '{speaker.name}' disimpan.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/speaker/<speaker_id>/delete", methods=["POST"])
@admin_required
def admin_delete_speaker(speaker_id):
    """Hapus pembicara beserta fotonya."""
    speaker = get_or_404(Speaker, speaker_id)
    delete_photo_file(speaker.photo)
    name = speaker.name
    speaker.delete()
    flash(f"Pembicara '{name}' dihapus.", "success")
    return redirect(url_for("admin_dashboard"))


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
        return redirect(url_for("admin_dashboard", _anchor="panel-pendaftaran"))

    if new_status in ("pending", "paid", "expired", "cancelled", "failed", "refunded"):
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
    return redirect(url_for("admin_dashboard", _anchor="panel-pendaftaran"))


@app.route("/admin/tenant/<tenant_id>/delete", methods=["POST"])
@admin_required
def admin_delete_tenant(tenant_id):
    """
    Hapus satu pendaftaran secara permanen.

    Dipakai untuk membersihkan data uji atau pendaftaran ganda. Riwayat
    pembayaran di Midtrans tidak ikut terhapus — pengembalian dana, bila perlu,
    tetap dilakukan lewat dasbor Midtrans.
    """
    tenant = get_or_404(Tenant, tenant_id)
    order_id = tenant.order_id
    tenant.delete()
    flash(f"Pendaftaran {order_id} telah dihapus.", "success")
    return redirect(url_for("admin_dashboard"))


@app.errorhandler(413)
def file_too_large(e):
    flash("Ukuran berkas terlalu besar. Maksimal 5 MB per foto.", "error")
    return redirect(url_for("admin_dashboard"))


seed_defaults()


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
