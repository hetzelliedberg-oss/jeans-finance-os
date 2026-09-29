import sqlite3, sys
sys.stdout.reconfigure(encoding='utf-8')
conn = sqlite3.connect('data/finance_hub.db')
c = conn.cursor()
c.execute("SELECT message_id, order_time, total_sales, raw_text FROM orders WHERE source_channel='online' AND substr(order_time, 12, 2) IN ('00','01','02','03','04','05') ORDER BY order_time")
rows = c.fetchall()
print(f"Orders between 00:00 and 06:00: {len(rows)}")
for r in rows:
    first_line = r[3].strip().split('\n')[0] if r[3] else ''
    print(f"Msg {r[0]} | {r[1]} | {first_line}")
conn.close()
