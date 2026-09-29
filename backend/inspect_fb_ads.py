import sqlite3, sys, json
sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('data/finance_hub.db')
c = conn.cursor()

c.execute("SELECT date, online_spend, kkc_spend, total_spend, campaign_details FROM daily_fb_ads WHERE date >= '2026-08-01' ORDER BY date LIMIT 10")
rows = c.fetchall()
for r in rows:
    print(f"Date {r[0]} | Online: {r[1]} | KKC: {r[2]} | Total: {r[3]}")
    if r[4]:
        try:
            details = json.loads(r[4])
            print("  Campaign Details Sample:", json.dumps(details, ensure_ascii=False)[:300])
        except Exception as e:
            print("  Raw details:", r[4][:200])

conn.close()
