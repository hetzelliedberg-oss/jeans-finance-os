import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
conn = sqlite3.connect('data/finance_hub.db')
c = conn.cursor()
c.execute("SELECT key, value FROM settings")
for k, v in c.fetchall():
    if k != "TELETHON_STRING_SESSION":
        print(f"{k}: {v}")
    else:
        print(f"{k}: (len={len(v)})")
