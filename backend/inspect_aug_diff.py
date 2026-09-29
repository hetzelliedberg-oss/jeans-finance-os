import sqlite3, sys
sys.stdout.reconfigure(encoding='utf-8')
conn = sqlite3.connect('data/finance_hub.db')
c = conn.cursor()
print("=== 2026-08-17 Orders in DB ===")
c.execute("SELECT message_id, order_time, total_pieces, total_sales, payment_method, raw_text FROM orders WHERE source_channel='kkc' AND order_date='2026-08-17'")
for r in c.fetchall():
    first_line = r[5].strip().split('\n')[0]
    print(f"Msg {r[0]} | {r[1]} | {r[2]} pcs | {r[3]} THB | {r[4]} | {first_line}")

print("\n=== 2026-08-29 Orders in DB ===")
c.execute("SELECT message_id, order_time, total_pieces, total_sales, payment_method, raw_text FROM orders WHERE source_channel='kkc' AND order_date='2026-08-29'")
for r in c.fetchall():
    first_line = r[5].strip().split('\n')[0]
    print(f"Msg {r[0]} | {r[1]} | {r[2]} pcs | {r[3]} THB | {r[4]} | {first_line}")
