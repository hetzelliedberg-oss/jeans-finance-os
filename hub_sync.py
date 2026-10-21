import argparse
import sqlite3
import requests
import sys
import os

sys.stdout.reconfigure(encoding='utf-8')

API_BASE = os.environ.get("JEANS_HUB_API", "https://jeans-finance-os.onrender.com/api")
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "finance_hub.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def check_status():
    print(f"📡 Checking Central Cloud Hub ({API_BASE}) vs Local DB ({DB_PATH})...\n")
    try:
        r = requests.get(f"{API_BASE}/pnl", params={'start_date': '2026-10-01', 'end_date': '2026-10-14', 'channel': 'consolidated'}, timeout=15)
        cloud_kpi = r.json().get('kpi', {})
    except Exception as e:
        print(f"❌ Failed to reach Cloud Hub: {e}")
        return

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*), SUM(total_sales), SUM(cogs_total) FROM orders WHERE order_date >= '2026-10-01' AND order_date <= '2026-10-14' AND status != 'cancelled'")
    local_orders, local_sales, local_cogs = c.fetchone()
    conn.close()

    print(f"📊 [Cloud Hub]   Orders: {cloud_kpi.get('orders_count', 0)} | Sales: ฿{cloud_kpi.get('sales', 0):,.2f} | Net Profit: ฿{cloud_kpi.get('net_profit', 0):,.2f}")
    print(f"💻 [Local Machine] Orders: {local_orders or 0} | Sales: ฿{(local_sales or 0):,.2f} | COGS: ฿{(local_cogs or 0):,.2f}")

    if cloud_kpi.get('orders_count') == local_orders and abs(cloud_kpi.get('sales', 0) - (local_sales or 0)) < 1.0:
        print("\n✅ STATUS: 100% IN SYNC! ทั้งเครื่องนี้และ Cloud Hub ตรงกันสมบูรณ์แบบ")
    else:
        print("\n⚠️ STATUS: มีความแตกต่างระหว่าง Local กับ Cloud Hub (แนะนำให้รัน pull หรือ push)")

def pull_from_cloud():
    print(f"⬇️ Pulling latest orders from Central Cloud Hub ({API_BASE})...")
    try:
        r = requests.get(f"{API_BASE}/orders", params={'limit': 1000}, timeout=20)
        orders = r.json().get('orders', [])
    except Exception as e:
        print(f"❌ Failed to fetch orders from Cloud Hub: {e}")
        return

    conn = get_db()
    c = conn.cursor()
    synced = 0
    updated = 0

    for o in orders:
        oid = o['id']
        c.execute("SELECT id FROM orders WHERE id = ?", (oid,))
        row = c.fetchone()
        if not row:
            c.execute("""
                INSERT INTO orders (
                    id, source_channel, message_id, sender_name, order_date, order_time,
                    raw_text, total_pieces, total_sales, payment_method, cod_amount,
                    transfer_amount, cogs_total, commission_amount, status, created_at,
                    customer_name, platform
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                oid, o.get('source_channel'), o.get('message_id'), o.get('sender_name'),
                o.get('order_date'), o.get('order_time'), o.get('raw_text'),
                o.get('total_pieces'), o.get('total_sales'), o.get('payment_method'),
                o.get('cod_amount'), o.get('transfer_amount'), o.get('cogs_total'),
                o.get('commission_amount'), o.get('status'), o.get('created_at'),
                o.get('customer_name'), o.get('platform')
            ))
            synced += 1
        else:
            c.execute("""
                UPDATE orders SET
                    order_date = ?, total_pieces = ?, total_sales = ?, cogs_total = ?, status = ?
                WHERE id = ?
            """, (o.get('order_date'), o.get('total_pieces'), o.get('total_sales'), o.get('cogs_total'), o.get('status'), oid))
            updated += 1

        # Sync items
        c.execute("DELETE FROM order_items WHERE order_id = ?", (oid,))
        for it in o.get('items', []):
            c.execute("""
                INSERT INTO order_items (order_id, sku, size, color, quantity, unit_cost, total_cost)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (oid, it.get('sku', ''), it.get('size', ''), it.get('color', ''), it.get('quantity', 1), it.get('unit_cost', 0.0), it.get('total_cost', 0.0)))


    conn.commit()
    conn.close()
    print(f"✅ Pull Completed: เพิ่มใหม่ {synced} บิล | อัปเดต {updated} บิล เรียบร้อยแล้ว!")

def push_to_cloud():
    print(f"⬆️ Pushing local audited orders to Central Cloud Hub ({API_BASE})...")
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM orders WHERE order_date >= '2026-10-01' ORDER BY id")
    orders = [dict(r) for r in c.fetchall()]
    conn.close()

    success = 0
    for o in orders:
        oid = o['id']
        payload = {
            'order_date': o['order_date'],
            'total_pieces': o['total_pieces'],
            'total_sales': o['total_sales'],
            'cogs_total': o['cogs_total'],
            'status': o['status']
        }
        try:
            r = requests.patch(f"{API_BASE}/orders/{oid}", json=payload, timeout=10).json()
            if r.get('success'):
                success += 1
        except Exception:
            pass

    print(f"✅ Push Completed: อัปเดตขึ้น Cloud สำเร็จ {success}/{len(orders)} บิล!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Jeans Finance Hub Cloud Sync Utility")
    parser.add_argument("action", choices=["status", "pull", "push"], default="status", nargs="?", help="Action to perform")
    args = parser.parse_args()

    if args.action == "status":
        check_status()
    elif args.action == "pull":
        pull_from_cloud()
    elif args.action == "push":
        push_to_cloud()
