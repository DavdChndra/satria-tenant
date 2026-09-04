"""
Migrasi data dari satria.db (SQLite/versi lama) ke MongoDB Atlas.

Jalankan SEKALI setelah MONGODB_URI di .env sudah benar dan bisa dikoneksi.
Script ini tidak menghapus/mengubah satria.db — aman dijalankan berulang,
tapi setiap kali dijalankan akan membuat data BARU di MongoDB (jangan
dijalankan dua kali pada database Mongo yang sama tanpa mengosongkannya
dulu, supaya tidak dobel).

    python migrate_to_mongo.py
"""
import os
import sqlite3

import mongoengine as me
from dotenv import load_dotenv

from models import (BoothType, AddOn, SelectedAddOn, Tenant, AdminUser,
                    EventInfo, GalleryPhoto, Broadcast, Speaker)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))
DB_PATH = os.path.join(BASE_DIR, "satria.db")


def rows(con, table):
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.execute(f"SELECT * FROM {table}")
    return [dict(r) for r in cur.fetchall()]


def table_exists(con, table):
    cur = con.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
    return cur.fetchone() is not None


def parse_dt(value):
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            from datetime import datetime
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def main():
    if not os.path.exists(DB_PATH):
        print(f"'{DB_PATH}' tidak ditemukan — tidak ada yang dimigrasikan.")
        return

    mongodb_uri = os.environ.get("MONGODB_URI")
    if not mongodb_uri:
        raise RuntimeError("MONGODB_URI belum diisi di .env.")
    me.connect(host=mongodb_uri)

    con = sqlite3.connect(DB_PATH)

    # --- booth_types ---
    booth_id_map = {}
    if table_exists(con, "booth_types"):
        for r in rows(con, "booth_types"):
            doc = BoothType(
                name=r["name"], description=r.get("description") or "",
                price=r["price"], quota=r["quota"],
                is_active=bool(r["is_active"]), sort_order=r.get("sort_order") or 0,
                created_at=parse_dt(r.get("created_at")),
            ).save()
            booth_id_map[r["id"]] = doc
        print(f"BoothType: {len(booth_id_map)} dimigrasikan.")

    # --- add_ons ---
    addon_id_map = {}
    if table_exists(con, "add_ons"):
        for r in rows(con, "add_ons"):
            doc = AddOn(
                name=r["name"], description=r.get("description") or "",
                price=r["price"], is_active=bool(r["is_active"]),
                sort_order=r.get("sort_order") or 0,
                created_at=parse_dt(r.get("created_at")),
            ).save()
            addon_id_map[r["id"]] = doc
        print(f"AddOn: {len(addon_id_map)} dimigrasikan.")

    # --- tenant_add_ons (dikelompokkan per tenant_id agar bisa di-embed) ---
    addons_by_tenant = {}
    if table_exists(con, "tenant_add_ons"):
        for r in rows(con, "tenant_add_ons"):
            addon = addon_id_map.get(r["add_on_id"])
            if not addon:
                continue
            addons_by_tenant.setdefault(r["tenant_id"], []).append(
                SelectedAddOn(add_on=addon, name=addon.name, price=r["price"])
            )

    # --- tenants ---
    tenant_count = 0
    if table_exists(con, "tenants"):
        for r in rows(con, "tenants"):
            booth = booth_id_map.get(r["booth_type_id"])
            if not booth:
                print(f"  lewati tenant order_id={r.get('order_id')}: booth_type tidak ditemukan.")
                continue
            Tenant(
                order_id=r["order_id"],
                institution_name=r["institution_name"],
                pic_name=r["pic_name"],
                email=r["email"],
                phone=r["phone"],
                booth_type=booth,
                price_at_registration=r["price_at_registration"],
                description=r.get("description") or "",
                payment_status=r.get("payment_status") or "pending",
                midtrans_transaction_id=r.get("midtrans_transaction_id"),
                payment_type=r.get("payment_type"),
                paid_at=parse_dt(r.get("paid_at")),
                snap_token=r.get("snap_token") or "",
                midtrans_order_id=r.get("midtrans_order_id"),
                checkin_token=r.get("checkin_token") or None,
                checked_in_at=parse_dt(r.get("checked_in_at")),
                selected_add_ons=addons_by_tenant.get(r["id"], []),
                created_at=parse_dt(r.get("created_at")),
                updated_at=parse_dt(r.get("updated_at")),
            ).save()
            tenant_count += 1
        print(f"Tenant: {tenant_count} dimigrasikan.")

    # --- admin_users ---
    if table_exists(con, "admin_users"):
        n = 0
        for r in rows(con, "admin_users"):
            if AdminUser.objects(username=r["username"]).first():
                continue
            AdminUser(username=r["username"], password_hash=r["password_hash"]).save()
            n += 1
        print(f"AdminUser: {n} dimigrasikan.")

    # --- event_info (baris tunggal) ---
    if table_exists(con, "event_info"):
        data = rows(con, "event_info")
        if data and EventInfo.objects.count() == 0:
            r = data[0]
            EventInfo(
                venue_name=r.get("venue_name") or "", address=r.get("address") or "",
                event_date=r.get("event_date") or "", maps_url=r.get("maps_url") or "",
                hero_eyebrow=r.get("hero_eyebrow") or "SATRIA 2026 · Exhibition",
                hero_title_before=r.get("hero_title_before") or "Pamerkan",
                hero_title_accent=r.get("hero_title_accent") or "karya terbaik",
                hero_title_after=r.get("hero_title_after") or "mu disini",
                hero_lead=r.get("hero_lead") or "",
                hero_note=r.get("hero_note") or "PT Nusa Inspira Teknologi",
                hero_note_prefix=r.get("hero_note_prefix") or "In collaboration with",
                speakers_eyebrow=r.get("speakers_eyebrow") or "Narasumber",
                speakers_title=r.get("speakers_title") or "Pembicara acara",
                speakers_subtitle=r.get("speakers_subtitle") or "",
                event_notes=r.get("event_notes") or "",
                updated_at=parse_dt(r.get("updated_at")),
            ).save()
            print("EventInfo: 1 dimigrasikan.")

    # --- gallery_photos ---
    if table_exists(con, "gallery_photos"):
        n = 0
        for r in rows(con, "gallery_photos"):
            GalleryPhoto(
                filename=r["filename"], caption=r.get("caption") or "",
                sort_order=r.get("sort_order") or 0, is_active=bool(r.get("is_active", 1)),
                created_at=parse_dt(r.get("created_at")),
                fit_mode=r.get("fit_mode") or "contain",
                pos_x=r.get("pos_x") if r.get("pos_x") is not None else 50,
                pos_y=r.get("pos_y") if r.get("pos_y") is not None else 50,
            ).save()
            n += 1
        print(f"GalleryPhoto: {n} dimigrasikan.")

    # --- speakers ---
    if table_exists(con, "speakers"):
        n = 0
        for r in rows(con, "speakers"):
            Speaker(
                name=r["name"], institution=r.get("institution") or "",
                topic=r.get("topic") or "", photo=r.get("photo") or "",
                sort_order=r.get("sort_order") or 0, is_active=bool(r.get("is_active", 1)),
                created_at=parse_dt(r.get("created_at")),
                pos_x=r.get("pos_x") if r.get("pos_x") is not None else 50,
                pos_y=r.get("pos_y") if r.get("pos_y") is not None else 50,
            ).save()
            n += 1
        print(f"Speaker: {n} dimigrasikan.")

    # --- broadcasts ---
    if table_exists(con, "broadcasts"):
        n = 0
        for r in rows(con, "broadcasts"):
            Broadcast(
                subject=r["subject"], body=r["body"], audience=r["audience"],
                total_recipients=r.get("total_recipients") or 0,
                total_sent=r.get("total_sent") or 0, total_failed=r.get("total_failed") or 0,
                created_at=parse_dt(r.get("created_at")),
            ).save()
            n += 1
        print(f"Broadcast: {n} dimigrasikan.")

    con.close()
    print("Migrasi selesai.")


if __name__ == "__main__":
    main()
