import requests
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('data/finance_hub.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()
cur.execute("SELECT * FROM orders WHERE order_date LIKE '2026-10%' ORDER BY id")
local_orders = {r['id']: dict(r) for r in cur.fetchall()}

r = requests.get('https://jeans-finance-os.onrender.com/api/orders', params={'limit': 1000}, timeout=15)
render_orders = {o['id']: o for o in r.json().get('orders', []) if o.get('order_date', '').startswith('2026-10')}

print(f"Local Oct orders: {len(local_orders)}, Render Oct orders: {len(render_orders)}")

diffs = []
for oid, lo in local_orders.items():
    if oid not in render_orders:
        diffs.append(f"Order {oid} missing on Render")
    else:
        ro = render_orders[oid]
        fields = ['order_date', 'total_pieces', 'total_sales', 'cogs_total']
        mismatches = []
        for f in fields:
            if f in ['total_sales', 'cogs_total']:
                if abs(float(lo[f] or 0) - float(ro[f] or 0)) > 0.01:
                    mismatches.append(f"{f}: local={lo[f]} vs render={ro[f]}")
            else:
                if str(lo[f]) != str(ro[f]):
                    mismatches.append(f"{f}: local={lo[f]} vs render={ro[f]}")
        if mismatches:
            diffs.append(f"Order {oid} mismatches: {mismatches}")

for roid, ro in render_orders.items():
    if roid not in local_orders:
        diffs.append(f"Order {roid} on Render but NOT in local (status={ro.get('status')})")

print(f"Total differences: {len(diffs)}")
for d in diffs:
    print(d)
