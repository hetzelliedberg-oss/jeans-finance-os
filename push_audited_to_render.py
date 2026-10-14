import requests
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('data/finance_hub.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()
cur.execute("SELECT * FROM orders WHERE order_date LIKE '2026-10%' ORDER BY id")
local_orders = {r['id']: dict(r) for r in cur.fetchall()}

url_base = 'https://jeans-finance-os.onrender.com/api'

# 1. Cancel duplicate order 9015 on Render
try:
    res_del = requests.delete(f"{url_base}/orders/9015", timeout=10).json()
    print("Delete/cancel 9015 on Render:", res_del)
except Exception as e:
    print("Error deleting 9015:", e)

# 2. Patch all differences to Render
patched_count = 0
for oid, lo in local_orders.items():
    payload = {
        'order_date': lo['order_date'],
        'total_pieces': lo['total_pieces'],
        'total_sales': lo['total_sales'],
        'cogs_total': lo['cogs_total']
    }
    try:
        res = requests.patch(f"{url_base}/orders/{oid}", json=payload, timeout=10).json()
        if res.get('success'):
            patched_count += 1
    except Exception as e:
        print(f"Error patching {oid}: {e}")

print(f"Successfully patched {patched_count} orders on Render!")

# 3. Check ads on Render
try:
    res_ads = requests.post(f"{url_base}/ads/sync", params={'days': 5}, timeout=20).json()
    print("Ads sync response:", res_ads)
except Exception as e:
    print("Ads sync error:", e)
