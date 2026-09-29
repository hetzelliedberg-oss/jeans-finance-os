import sqlite3
import requests
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('C:/Users/PAWIN/.gemini/antigravity/scratch/jeans-around-finance-os/data/finance_hub.db')
c = conn.cursor()
c.execute("SELECT value FROM settings WHERE key = 'FB_ACCESS_TOKEN'")
token = c.fetchone()[0]
c.execute("SELECT value FROM settings WHERE key = 'AD_ACCOUNT_ID'")
act_id = c.fetchone()[0]

url = f"https://graph.facebook.com/v20.0/{act_id}/insights"

for d in ['2026-09-27', '2026-09-28']:
    params = {
        'access_token': token,
        'level': 'campaign',
        'time_range': json.dumps({'since': d, 'until': d}),
        'fields': 'campaign_name,spend',
        'limit': 500
    }
    res = requests.get(url, params=params, timeout=20)
    data = res.json()
    entries = data.get('data', [])
    online_spend = 0.0
    kkc_spend = 0.0
    for e in entries:
        sp = float(e.get('spend', 0.0))
        cname = e.get('campaign_name', '')
        if 'ขอนแก่น' in cname:
            kkc_spend += sp
        else:
            online_spend += sp
    print(f"Date {d}: Online Ads = {online_spend:,.2f}, KKC Ads = {kkc_spend:,.2f}, Total Ads = {online_spend+kkc_spend:,.2f}")
    
    c.execute("""
        INSERT INTO daily_fb_ads (date, online_spend, kkc_spend, total_spend, campaign_details, updated_at)
        VALUES (?, ?, ?, ?, ?, datetime('now', '+7 hours'))
        ON CONFLICT(date) DO UPDATE SET 
            online_spend=excluded.online_spend,
            kkc_spend=excluded.kkc_spend,
            total_spend=excluded.total_spend,
            campaign_details=excluded.campaign_details,
            updated_at=excluded.updated_at
    """, (d, online_spend, kkc_spend, online_spend+kkc_spend, json.dumps(entries, ensure_ascii=False)))

conn.commit()
print("Successfully saved daily_fb_ads for 27 and 28 Sep!")
