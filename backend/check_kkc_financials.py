import sqlite3, sys
sys.stdout.reconfigure(encoding='utf-8')
conn = sqlite3.connect('data/finance_hub.db')
c = conn.cursor()

c.execute("SELECT name FROM sqlite_master WHERE type='table'")
print("Tables:", [r[0] for r in c.fetchall()])

# Check KKC sales & COGS by month
c.execute("""
    SELECT substr(order_date, 1, 7) as mo,
           count(*) as orders,
           sum(total_pieces) as pieces,
           sum(total_sales) as sales,
           sum(cogs_total) as cogs,
           sum(total_sales - cogs_total) as gross_profit,
           avg((total_sales - cogs_total) / total_sales) * 100 as avg_gross_margin_pct
    FROM orders
    WHERE source_channel = 'kkc'
    GROUP BY mo
    ORDER BY mo
""")
for r in c.fetchall():
    print(f"Month {r[0]}: {r[1]} orders | {r[2]} pcs | Sales: {r[3]:,.2f} | COGS: {r[4]:,.2f} | GP: {r[5]:,.2f} | Margin: {r[6]:.1f}%")

conn.close()
