"""
Menambahkan tabel dan kolom baru ke satria.db tanpa menghapus data yang ada.

Jalankan sekali setiap kali ada pembaruan struktur database:
    python migrate.py
"""
import os
import sqlite3

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "satria.db")


def column_exists(cur, table, column):
    cur.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cur.fetchall())


def table_exists(cur, table):
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
    return cur.fetchone() is not None


def main():
    if not os.path.exists(DB_PATH):
        print("satria.db belum ada — jalankan 'python app.py' dulu, database akan dibuat otomatis.")
        return

    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    changes = []

    # Kolom pengaturan tampilan foto carousel
    if table_exists(cur, "gallery_photos"):
        for col, ddl in [
            ("fit_mode", "ALTER TABLE gallery_photos ADD COLUMN fit_mode VARCHAR(10) DEFAULT 'contain'"),
            ("pos_x", "ALTER TABLE gallery_photos ADD COLUMN pos_x INTEGER DEFAULT 50"),
            ("pos_y", "ALTER TABLE gallery_photos ADD COLUMN pos_y INTEGER DEFAULT 50"),
        ]:
            if not column_exists(cur, "gallery_photos", col):
                cur.execute(ddl)
                changes.append(f"kolom gallery_photos.{col}")

    # Keterangan karya/produk dari pendaftar
    if table_exists(cur, "tenants") and not column_exists(cur, "tenants", "description"):
        cur.execute("ALTER TABLE tenants ADD COLUMN description TEXT DEFAULT ''")
        changes.append("kolom tenants.description")

    # Bagian sambutan (hero)
    if table_exists(cur, "event_info"):
        for col, ddl in [
            ("hero_eyebrow",
             "ALTER TABLE event_info ADD COLUMN hero_eyebrow VARCHAR(80) "
             "DEFAULT 'SATRIA 2026 · Exhibition'"),
            ("hero_title_before",
             "ALTER TABLE event_info ADD COLUMN hero_title_before VARCHAR(120) DEFAULT 'Pamerkan'"),
            ("hero_title_accent",
             "ALTER TABLE event_info ADD COLUMN hero_title_accent VARCHAR(120) DEFAULT 'karya terbaik'"),
            ("hero_title_after",
             "ALTER TABLE event_info ADD COLUMN hero_title_after VARCHAR(120) DEFAULT 'mu disini'"),
            ("hero_lead", "ALTER TABLE event_info ADD COLUMN hero_lead TEXT DEFAULT ''"),
            ("hero_note",
             "ALTER TABLE event_info ADD COLUMN hero_note VARCHAR(200) DEFAULT 'PT Nusa Inspira Teknologi'"),
            ("hero_note_prefix",
             "ALTER TABLE event_info ADD COLUMN hero_note_prefix VARCHAR(80) DEFAULT 'In collaboration with'"),
        ]:
            if not column_exists(cur, "event_info", col):
                cur.execute(ddl)
                changes.append(f"kolom event_info.{col}")

        # hero_lead panjang, diisi terpisah agar tidak menyulitkan DDL
        cur.execute("UPDATE event_info SET hero_lead = ? WHERE hero_lead IS NULL OR hero_lead = ''",
                    ("Daftarkan booth untuk menampilkan karya, riset, dan inovasi Anda "
                     "di hadapan pengunjung SATRIA 2026. Slot terbatas sesuai kuota "
                     "masing-masing jenis booth.",))
        if cur.rowcount:
            changes.append(f"{cur.rowcount} baris event_info.hero_lead diisi")

    # Judul bagian pembicara
    if table_exists(cur, "event_info"):
        for col, ddl in [
            ("speakers_eyebrow",
             "ALTER TABLE event_info ADD COLUMN speakers_eyebrow VARCHAR(60) DEFAULT 'Narasumber'"),
            ("speakers_title",
             "ALTER TABLE event_info ADD COLUMN speakers_title VARCHAR(150) DEFAULT 'Pembicara acara'"),
            ("speakers_subtitle",
             "ALTER TABLE event_info ADD COLUMN speakers_subtitle VARCHAR(300) "
             "DEFAULT 'Menghadirkan praktisi dan akademisi di bidangnya.'"),
        ]:
            if not column_exists(cur, "event_info", col):
                cur.execute(ddl)
                changes.append(f"kolom event_info.{col}")

    # Tiket masuk & token pembayaran
    if table_exists(cur, "tenants"):
        for col, ddl in [
            ("snap_token", "ALTER TABLE tenants ADD COLUMN snap_token VARCHAR(120) DEFAULT ''"),
            ("checkin_token", "ALTER TABLE tenants ADD COLUMN checkin_token VARCHAR(64)"),
            ("checked_in_at", "ALTER TABLE tenants ADD COLUMN checked_in_at DATETIME"),
            ("midtrans_order_id", "ALTER TABLE tenants ADD COLUMN midtrans_order_id VARCHAR(64)"),
        ]:
            if not column_exists(cur, "tenants", col):
                cur.execute(ddl)
                changes.append(f"kolom tenants.{col}")

    # Pendaftaran lama: samakan midtrans_order_id dengan order_id
    if table_exists(cur, "tenants") and column_exists(cur, "tenants", "midtrans_order_id"):
        cur.execute("UPDATE tenants SET midtrans_order_id = order_id "
                    "WHERE midtrans_order_id IS NULL OR midtrans_order_id = ''")
        if cur.rowcount:
            changes.append(f"{cur.rowcount} baris tenants.midtrans_order_id diisi")

    # Tabel riwayat email massal
    if not table_exists(cur, "broadcasts"):
        cur.execute("""
            CREATE TABLE broadcasts (
                id INTEGER PRIMARY KEY,
                subject VARCHAR(200) NOT NULL,
                body TEXT NOT NULL,
                audience VARCHAR(30) NOT NULL,
                total_recipients INTEGER DEFAULT 0,
                total_sent INTEGER DEFAULT 0,
                total_failed INTEGER DEFAULT 0,
                created_at DATETIME
            )""")
        changes.append("tabel broadcasts")

    # Tabel pembicara
    if not table_exists(cur, "speakers"):
        cur.execute("""
            CREATE TABLE speakers (
                id INTEGER PRIMARY KEY,
                name VARCHAR(150) NOT NULL,
                institution VARCHAR(200) DEFAULT '',
                topic VARCHAR(300) DEFAULT '',
                photo VARCHAR(255) DEFAULT '',
                sort_order INTEGER DEFAULT 0,
                is_active BOOLEAN DEFAULT 1,
                created_at DATETIME
            )""")
        changes.append("tabel speakers")

    # Posisi foto pembicara
    if table_exists(cur, "speakers"):
        for col, ddl in [
            ("pos_x", "ALTER TABLE speakers ADD COLUMN pos_x INTEGER DEFAULT 50"),
            ("pos_y", "ALTER TABLE speakers ADD COLUMN pos_y INTEGER DEFAULT 50"),
        ]:
            if not column_exists(cur, "speakers", col):
                cur.execute(ddl)
                changes.append(f"kolom speakers.{col}")

    # Catatan/ketentuan acara di halaman depan
    if table_exists(cur, "event_info") and not column_exists(cur, "event_info", "event_notes"):
        cur.execute("ALTER TABLE event_info ADD COLUMN event_notes TEXT DEFAULT ''")
        changes.append("kolom event_info.event_notes")

    # Opsi tambahan pendaftaran (mis. dinner, cetak poster)
    if not table_exists(cur, "add_ons"):
        cur.execute("""
            CREATE TABLE add_ons (
                id INTEGER PRIMARY KEY,
                name VARCHAR(120) NOT NULL,
                description TEXT DEFAULT '',
                price INTEGER NOT NULL DEFAULT 0,
                is_active BOOLEAN DEFAULT 1,
                sort_order INTEGER DEFAULT 0,
                created_at DATETIME
            )""")
        changes.append("tabel add_ons")

    if not table_exists(cur, "tenant_add_ons"):
        cur.execute("""
            CREATE TABLE tenant_add_ons (
                id INTEGER PRIMARY KEY,
                tenant_id INTEGER NOT NULL REFERENCES tenants(id),
                add_on_id INTEGER NOT NULL REFERENCES add_ons(id),
                price INTEGER NOT NULL
            )""")
        changes.append("tabel tenant_add_ons")

    con.commit()
    con.close()

    if changes:
        print("Berhasil menambahkan:")
        for c in changes:
            print("  -", c)
    else:
        print("Database sudah mutakhir, tidak ada perubahan.")


if __name__ == "__main__":
    main()
