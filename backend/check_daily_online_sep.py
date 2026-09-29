import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
conn = sqlite3.connect('data/finance_hub.db')
c = conn.cursor()

c.execute("""
    SELECT order_date, count(*), sum(total_pieces), sum(total_sales)
    FROM orders
    WHERE source_channel = 'online' AND order_date LIKE '2026-09%'
    GROUP BY order_date
    ORDER BY order_date
""")
print(f"{'Date':<10} | {'Orders':<7} | {'Pieces':<7} | {'Sales (THB)':<12}")
print("-" * 45)
tot_o = 0
tot_p = 0
tot_s = 0.0
for r in c.fetchall():
    tot_o += r[1]
    tot_p += r[2]
    tot_s += r[3]
    print(f"{r[0]:<10} | {r[1]:<7} | {r[2]:<7} | {r[3]:>10,.2f}")
print("-" * 45)
print(f"{'TOTAL':<10} | {tot_o:<7} | {tot_p:<7} | {tot_s:>10,.2f}")
