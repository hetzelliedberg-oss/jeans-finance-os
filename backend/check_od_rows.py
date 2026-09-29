import sqlite3

conn = sqlite3.connect('data/finance_hub.db')
c = conn.cursor()
c.execute("SELECT id, report_date, channel, gross_sales, source_url FROM onedrive_closings ORDER BY report_date")
rows = c.fetchall()
print(f"Total onedrive_closings: {len(rows)}")
for r in rows:
    print(r)
