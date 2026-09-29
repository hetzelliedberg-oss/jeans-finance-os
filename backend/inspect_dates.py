import sqlite3, sys
sys.stdout.reconfigure(encoding='utf-8')
conn = sqlite3.connect('data/finance_hub.db')
c = conn.cursor()
print("=== Last 5 online orders on 2026-09-23 ===")
c.execute("SELECT message_id, order_time, total_sales, total_pieces, raw_text FROM orders WHERE source_channel='online' AND order_date='2026-09-23' ORDER BY order_time DESC LIMIT 5")
for r in c.fetchall():
    first_line = r[4].strip().split('\n')[0] if r[4] else ''
    print(f"Msg {r[0]} | {r[1]} | {r[2]} THB | {first_line}")

print("\n=== All online orders on 2026-09-24 in DB ===")
c.execute("SELECT message_id, order_time, total_sales, total_pieces, raw_text FROM orders WHERE source_channel='online' AND order_date='2026-09-24' ORDER BY order_time ASC")
rows = c.fetchall()
print(f"Count in DB: {len(rows)}")
for idx, r in enumerate(rows, 1):
    first_line = r[4].strip().split('\n')[0] if r[4] else ''
    print(f"#{idx:2d} | Msg {r[0]} | {r[1]} | {r[2]} THB | {first_line}")
conn.close()
