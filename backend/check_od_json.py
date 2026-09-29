import sqlite3
import json

conn = sqlite3.connect('data/finance_hub.db')
c = conn.cursor()
c.execute("SELECT raw_json FROM onedrive_closings WHERE raw_json != '' LIMIT 1")
row = c.fetchone()
if row:
    print(json.dumps(json.loads(row[0]), ensure_ascii=False, indent=2))
