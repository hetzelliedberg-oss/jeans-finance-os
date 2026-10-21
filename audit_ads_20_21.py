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
conn.close()

dates = ['2026-10-20', '2026-10-21']
all_results = {}

for date in dates:
    url = f"https://graph.facebook.com/v21.0/{act_id}/insights"
    params = {
        'access_token': token,
        'time_range': json.dumps({'since': date, 'until': date}),
        'fields': 'campaign_id,campaign_name,spend,impressions,reach,clicks,cpc,cpm,ctr,actions,cost_per_action_type',
        'level': 'campaign',
        'limit': 100
    }
    r = requests.get(url, params=params).json()
    all_results[date] = r

with open('ads_insights_20_21.json', 'w', encoding='utf-8') as f:
    json.dump(all_results, f, ensure_ascii=False, indent=2)

print("Saved ads insights to ads_insights_20_21.json")
