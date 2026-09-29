import sqlite3, requests, json, sys
sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('data/finance_hub.db')
c = conn.cursor()
c.execute("SELECT value FROM settings WHERE key = 'FB_ACCESS_TOKEN'")
token = c.fetchone()[0]
c.execute("SELECT value FROM settings WHERE key = 'AD_ACCOUNT_ID'")
act_id = c.fetchone()[0]
conn.close()

url = f"https://graph.facebook.com/v20.0/{act_id}/insights"

params = {
    "access_token": token,
    "level": "campaign",
    "time_range": json.dumps({"since": "2026-09-23", "until": "2026-09-27"}),
    "fields": "campaign_name,spend,reach,impressions,clicks,inline_link_clicks,actions",
    "limit": 500
}

res = requests.get(url, params=params, timeout=25)
data = res.json()
entries = data.get("data", [])

print("=== ALL CAMPAIGNS (2026-09-23 to 2026-09-27) ===")
for item in entries:
    c_name = item.get("campaign_name", "")
    spend = float(item.get("spend", 0.0))
    reach = int(item.get("reach", 0))
    clicks = int(item.get("clicks", 0))
    link_clicks = int(item.get("inline_link_clicks", 0))
    
    actions = item.get("actions", [])
    msg = 0
    purch = 0
    for a in actions:
        if a.get("action_type") in ["onsite_conversion.messaging_conversation_started_7d", "onsite_conversion.total_messaging_connection"]:
            msg = max(msg, int(a.get("value", 0)))
        if "purchase" in a.get("action_type"):
            purch = max(purch, int(a.get("value", 0)))
            
    print(f"• {c_name:40s} | Spend: {spend:8.2f} บ. | Reach: {reach:6,d} | Clicks: {clicks:5,d} | LinkClicks: {link_clicks:4,d} | Msg: {msg:3d} | Purch: {purch:2d}")
