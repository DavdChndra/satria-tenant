"""
Pengiriman email notifikasi lewat SMTP (mis. Gmail).

Konfigurasi lewat .env:
    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, SMTP_FROM_NAME

Bila SMTP_USER/SMTP_PASS kosong, seluruh fungsi di sini tidak melakukan apa-apa
dan mengembalikan False — aplikasi tetap berjalan normal tanpa email.
"""
import os
import smtplib
import logging
from email.message import EmailMessage
from email.utils import formataddr

logger = logging.getLogger(__name__)


def is_configured() -> bool:
    """True bila kredensial SMTP sudah diisi di .env."""
    return bool(os.environ.get("SMTP_USER") and os.environ.get("SMTP_PASS"))


def send_email(to_email: str, subject: str, html_body: str, text_body: str = "") -> bool:
    """
    Kirim satu email. Mengembalikan True bila terkirim.

    Kegagalan sengaja tidak dilempar sebagai exception: notifikasi email
    tidak boleh menggagalkan proses pendaftaran atau webhook pembayaran.
    """
    if not is_configured():
        logger.info("SMTP belum dikonfigurasi, email ke %s dilewati.", to_email)
        return False

    host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ["SMTP_USER"]
    password = os.environ["SMTP_PASS"]
    from_name = os.environ.get("SMTP_FROM_NAME", "Panitia SATRIA 2026")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((from_name, user))
    msg["To"] = to_email
    msg.set_content(text_body or "Buka email ini dengan tampilan HTML untuk membacanya.")
    msg.add_alternative(html_body, subtype="html")

    try:
        with smtplib.SMTP(host, port, timeout=20) as server:
            server.ehlo()
            # Port 587 memakai STARTTLS; server tanpa dukungan TLS tetap dilayani
            # agar pengujian lokal bisa berjalan.
            if server.has_extn("starttls"):
                server.starttls()
                server.ehlo()
            server.login(user, password)
            server.send_message(msg)
        logger.info("Email terkirim ke %s (%s)", to_email, subject)
        return True
    except Exception as exc:
        logger.warning("Gagal mengirim email ke %s: %s", to_email, exc)
        return False


def _rupiah(amount: int) -> str:
    return "Rp {:,}".format(amount).replace(",", ".")


def _layout(title: str, accent: str, lines_html: str, footer_note: str = "") -> str:
    """Kerangka HTML email — gaya selaras dengan situs (crimson, Inter)."""
    return f"""\
<div style="background:#FAFAFA;padding:28px 16px;font-family:Segoe UI,Roboto,Helvetica,Arial,sans-serif;">
  <div style="max-width:520px;margin:0 auto;background:#fff;border:1px solid #E8E8EC;border-radius:14px;overflow:hidden;">
    <div style="background:{accent};padding:20px 26px;">
      <div style="color:#fff;font-size:17px;font-weight:700;">SATRIA 2026</div>
      <div style="color:rgba(255,255,255,0.85);font-size:12.5px;margin-top:2px;">Pendaftaran tenant pameran</div>
    </div>
    <div style="padding:26px;">
      <h1 style="margin:0 0 14px;font-size:19px;color:#0F1115;">{title}</h1>
      {lines_html}
    </div>
    <div style="padding:16px 26px;border-top:1px solid #E8E8EC;color:#6B7280;font-size:11.5px;line-height:1.6;">
      {footer_note or "Email ini dikirim otomatis. Balas email ini bila ada pertanyaan."}
    </div>
  </div>
</div>"""


def _detail_table(tenant) -> str:
    rows = [
        ("Nomor pendaftaran", tenant.order_id),
        ("Institusi", tenant.institution_name),
        ("Penanggung jawab", tenant.pic_name),
        ("Jenis booth", tenant.booth_type.name if tenant.booth_type else "-"),
        ("Nominal", _rupiah(tenant.price_at_registration)),
    ]
    cells = "".join(
        f'<tr>'
        f'<td style="padding:7px 0;color:#6B7280;font-size:13px;">{k}</td>'
        f'<td style="padding:7px 0;color:#0F1115;font-size:13px;font-weight:600;text-align:right;">{v}</td>'
        f'</tr>'
        for k, v in rows
    )
    return f'<table style="width:100%;border-collapse:collapse;margin:6px 0 18px;">{cells}</table>'


def send_registration_received(tenant, status_url: str) -> bool:
    """Dikirim tepat setelah pendaftaran dibuat (pembayaran belum selesai)."""
    body = f"""
      <p style="margin:0 0 6px;font-size:14px;color:#3A3F4A;line-height:1.65;">
        Halo <strong>{tenant.pic_name}</strong>, pendaftaran booth Anda sudah kami terima.
        Selesaikan pembayaran agar slot booth Anda terkunci.
      </p>
      {_detail_table(tenant)}
      <a href="{status_url}" style="display:inline-block;background:#A4123A;color:#fff;text-decoration:none;
         padding:12px 22px;border-radius:9px;font-size:14px;font-weight:600;">Lihat status pendaftaran</a>
      <p style="margin:18px 0 0;font-size:12.5px;color:#6B7280;line-height:1.6;">
        Simpan nomor pendaftaran <strong>{tenant.order_id}</strong> sebagai rujukan.
      </p>"""
    text = (f"Pendaftaran diterima.\nNomor: {tenant.order_id}\n"
            f"Institusi: {tenant.institution_name}\nNominal: {_rupiah(tenant.price_at_registration)}\n"
            f"Cek status: {status_url}")
    return send_email(tenant.email, f"Pendaftaran diterima — {tenant.order_id}",
                      _layout("Pendaftaran Anda sudah tercatat", "#A4123A", body), text)


def send_payment_success(tenant, status_url: str) -> bool:
    """Dikirim saat webhook Midtrans mengonfirmasi pembayaran lunas."""
    body = f"""
      <div style="display:inline-block;background:#EFF9F3;color:#1F8A5B;border:1px solid #BFE3D0;
           padding:6px 13px;border-radius:999px;font-size:12.5px;font-weight:700;margin-bottom:14px;">
        Pembayaran lunas
      </div>
      <p style="margin:0 0 6px;font-size:14px;color:#3A3F4A;line-height:1.65;">
        Terima kasih, <strong>{tenant.pic_name}</strong>. Pembayaran Anda sudah kami terima
        dan slot booth Anda resmi terkunci.
      </p>
      {_detail_table(tenant)}
      <a href="{status_url}" style="display:inline-block;background:#1F8A5B;color:#fff;text-decoration:none;
         padding:12px 22px;border-radius:9px;font-size:14px;font-weight:600;">Lihat bukti pendaftaran</a>
      <p style="margin:18px 0 0;font-size:12.5px;color:#6B7280;line-height:1.6;">
        Email ini berlaku sebagai bukti pembayaran. Informasi teknis pelaksanaan
        akan kami kirim menjelang acara.
      </p>"""
    text = (f"Pembayaran lunas.\nNomor: {tenant.order_id}\n"
            f"Institusi: {tenant.institution_name}\nNominal: {_rupiah(tenant.price_at_registration)}\n"
            f"Bukti: {status_url}")
    return send_email(tenant.email, f"Pembayaran lunas — {tenant.order_id}",
                      _layout("Pembayaran berhasil", "#1F8A5B", body), text)


def send_broadcast(tenant, subject: str, message: str, status_url: str) -> bool:
    """
    Kirim informasi tambahan dari panitia ke satu tenant.

    `message` adalah teks biasa yang diketik admin; baris kosong menjadi
    pemisah paragraf. Isinya di-escape agar tag HTML tidak ikut dieksekusi.
    """
    from html import escape

    paragraphs = "".join(
        f'<p style="margin:0 0 12px;font-size:14px;color:#3A3F4A;line-height:1.7;">'
        f'{escape(block.strip()).replace(chr(10), "<br>")}</p>'
        for block in message.split("\n\n") if block.strip()
    )

    body = f"""
      <p style="margin:0 0 14px;font-size:14px;color:#3A3F4A;line-height:1.65;">
        Halo <strong>{escape(tenant.pic_name)}</strong> &mdash; {escape(tenant.institution_name)},
      </p>
      {paragraphs}
      {_detail_table(tenant)}
      <a href="{status_url}" style="display:inline-block;background:#A4123A;color:#fff;text-decoration:none;
         padding:12px 22px;border-radius:9px;font-size:14px;font-weight:600;">Lihat status pendaftaran</a>"""

    text = f"{message}\n\nNomor pendaftaran: {tenant.order_id}\nStatus: {status_url}"
    return send_email(tenant.email, subject,
                      _layout(escape(subject), "#A4123A", body), text)
