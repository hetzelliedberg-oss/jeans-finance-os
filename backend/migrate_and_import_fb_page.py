import os
import sys
import json
import re
from datetime import datetime
from typing import Dict, Any, List

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

from backend.database import get_db_connection, get_sku_cost_map
from backend.parser import normalize_sku

FB_ORDERS_FILE = os.path.join(
    os.path.dirname(BASE_DIR), "fb-sales-ai-engine", "orders_database.json"
)

def setup_schema_and_import_fb_page():
    conn = get_db_connection()
    cur = conn.cursor()

    # Add columns if they don't exist
    cur.execute("PRAGMA table_info(orders)")
    existing_cols = [c[1] for c in cur.fetchall()]

    if "customer_name" not in existing_cols:
        cur.execute("ALTER TABLE orders ADD COLUMN customer_name TEXT DEFAULT ''")
    if "phone" not in existing_cols:
        cur.execute("ALTER TABLE orders ADD COLUMN phone TEXT DEFAULT ''")
    if "platform" not in existing_cols:
        cur.execute("ALTER TABLE orders ADD COLUMN platform TEXT DEFAULT 'telegram'")
    conn.commit()

    if not os.path.exists(FB_ORDERS_FILE):
        print(f"[!] File not found: {FB_ORDERS_FILE}")
        conn.close()
        return {"success": False, "error": "FB orders file not found"}

    with open(FB_ORDERS_FILE, "r", encoding="utf-8") as f:
        fb_orders = json.load(f)

    sku_cost_map = get_sku_cost_map()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    imported = 0
    updated = 0

    for o in fb_orders:
        order_id = o.get("order_id", "")
        customer = o.get("customer_name", "")
        phone = o.get("phone", "")
        created_at = o.get("created_at", "")
        order_date = created_at[:10] if created_at else datetime.now().strftime("%Y-%m-%d")
        
        raw_model = o.get("item_model", "")
        # Extract SKU from item_model, e.g. 'XRP67เข้ม/L' -> 'XRP67'
        sku_match = re.search(r"(AR|XRP)[-_ ]?(\d+)", raw_model, re.IGNORECASE)
        sku = normalize_sku(sku_match.group(0)) if sku_match else "XRP67"
        
        size = o.get("size", "")
        amount = float(o.get("amount", 590.0))
        payment_method = "ปลายทาง" if "ปลายทาง" in o.get("payment_method", "") or "COD" in o.get("payment_method", "").upper() else "โอน"
        cod_val = amount if payment_method == "ปลายทาง" else 0.0
        transfer_val = amount if payment_method != "ปลายทาง" else 0.0

        admin = o.get("admin", "miw")
        if admin == "miw":
            admin = "mew" # Standardize spelling requested by user

        unit_cost = sku_cost_map.get(sku, 495.0)
        cogs = unit_cost * 1 # default 1 piece per model

        # Check if already in DB
        cur.execute("SELECT id FROM orders WHERE message_id = ?", (f"fb_{order_id}",))
        row = cur.fetchone()

        if row:
            # Update
            cur.execute("""
                UPDATE orders SET
                    customer_name = ?, phone = ?, platform = 'facebook_page',
                    sender_name = ?, order_date = ?, order_time = ?,
                    total_sales = ?, payment_method = ?, cod_amount = ?, transfer_amount = ?,
                    cogs_total = ?, commission_amount = 10.0
                WHERE id = ?
            """, (customer, phone, admin, order_date, created_at, amount, payment_method, cod_val, transfer_val, cogs, row["id"]))
            updated += 1
        else:
            cur.execute("""
                INSERT INTO orders (
                    source_channel, message_id, sender_name, order_date, order_time,
                    raw_text, total_pieces, total_sales, payment_method, cod_amount,
                    transfer_amount, cogs_total, commission_amount, status, created_at,
                    customer_name, phone, platform
                ) VALUES (
                    'online', ?, ?, ?, ?,
                    ?, 1, ?, ?, ?,
                    ?, ?, 10.0, 'completed', ?,
                    ?, ?, 'facebook_page'
                )
            """, (
                f"fb_{order_id}", admin, order_date, created_at,
                f"FB Page: {customer} ({phone}) รหัส {sku} ไซส์ {size} {payment_method} {int(amount)} [Admin: {admin}]",
                amount, payment_method, cod_val,
                transfer_val, cogs, now_str,
                customer, phone
            ))
            new_oid = cur.lastrowid
            # Add item
            cur.execute("""
                INSERT INTO order_items (order_id, sku, size, color, quantity, unit_cost, total_cost)
                VALUES (?, ?, ?, '', 1, ?, ?)
            """, (new_oid, sku, size, unit_cost, cogs))
            imported += 1

    conn.commit()
    conn.close()

    return {
        "success": True,
        "total_fb_orders": len(fb_orders),
        "newly_imported": imported,
        "updated": updated
    }


def audit_page_vs_telegram(start_date: str = "2026-08-01", end_date: str = "2026-09-13") -> Dict[str, Any]:
    """
    Audit and reconcile orders between Facebook Page chat and Telegram group.
    """
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT * FROM orders
        WHERE order_date >= ? AND order_date <= ? AND source_channel = 'online'
        ORDER BY order_date DESC, id DESC
    """, (start_date, end_date))
    orders = [dict(r) for r in cur.fetchall()]

    fb_orders = [o for o in orders if o.get("platform") == "facebook_page"]
    tg_orders = [o for o in orders if o.get("platform") != "facebook_page"]

    # Admin breakdown for both
    fb_admins = {}
    for o in fb_orders:
        adm = o.get("sender_name", "unknown")
        fb_admins[adm] = fb_admins.get(adm, 0) + 1

    tg_admins = {}
    for o in tg_orders:
        adm = o.get("sender_name", "unknown")
        tg_admins[adm] = tg_admins.get(adm, 0) + 1

    conn.close()

    return {
        "period": {"start": start_date, "end": end_date},
        "summary": {
            "total_fb_page_orders": len(fb_orders),
            "total_fb_page_sales": sum(o["total_sales"] for o in fb_orders),
            "fb_page_admins": fb_admins,
            "total_telegram_orders": len(tg_orders),
            "total_telegram_sales": sum(o["total_sales"] for o in tg_orders),
            "telegram_admins": tg_admins
        },
        "fb_page_orders": fb_orders
    }


if __name__ == "__main__":
    print("Running migration and import of FB Page orders...")
    res = setup_schema_and_import_fb_page()
    print("Import Result:", res)
    audit = audit_page_vs_telegram("2026-08-01", "2026-09-13")
    print("Audit Summary:", json.dumps(audit["summary"], ensure_ascii=False, indent=2))
