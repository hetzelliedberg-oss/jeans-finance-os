import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
conn = sqlite3.connect('data/finance_hub.db')
c = conn.cursor()

c.execute("SELECT id, message_id, order_time, total_sales, raw_text FROM orders WHERE source_channel = 'online' AND order_date = '2026-09-22' ORDER BY id")
rows = c.fetchall()
print(f"Total rows in DB for 2026-09-22: {len(rows)}")
for r in rows:
    first_line = r[4].split('\n')[0] if r[4] else ''
    print(f"ID {r[0]} | Msg {str(r[1]):<15} | Sales: {r[3]:>6.1f} | Line 1: {repr(first_line)}")
