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

print("=================================================================")
print("  INSPECTING META CAMPAIGNS FOR LAST 5 DAYS (2026-09-23 to 2026-09-27)")
print("=================================================================")

params = {
    "access_token": token,
    "level": "campaign",
    "time_range": json.dumps({"since": "2026-09-23", "until": "2026-09-27"}),
    "fields": "campaign_name,objective,spend,reach,impressions,clicks,inline_link_clicks,cpc,cpm,ctr,actions,cost_per_action_type",
    "limit": 500
}

res = requests.get(url, params=params, timeout=25)
data = res.json()

if "error" in data:
    print("Error:", data["error"])
    sys.exit(1)

entries = data.get("data", [])
print(f"Total active campaigns in last 5 days: {len(entries)}\n")

for item in entries:
    c_name = item.get("campaign_name", "")
    spend = float(item.get("spend", 0.0))
    reach = int(item.get("reach", 0))
    impr = int(item.get("impressions", 0))
    clicks = int(item.get("clicks", 0))
    link_clicks = int(item.get("inline_link_clicks", 0))
    cpc = float(item.get("cpc", 0.0)) if item.get("cpc") else 0.0
    cpm = float(item.get("cpm", 0.0)) if item.get("cpm") else 0.0
    ctr = float(item.get("ctr", 0.0)) if item.get("ctr") else 0.0
    
    actions = item.get("actions", [])
    action_types = {a.get("action_type"): a.get("value") for a in actions}
    cost_per_action = {a.get("action_type"): a.get("value") for a in item.get("cost_per_action_type", [])}
    
    print(f"CAMPAIGN: {c_name}")
    print(f"  Spend: {spend:,.2f} THB | Reach: {reach:,} | Impressions: {impr:,} | Clicks: {clicks:,} | Link Clicks: {link_clicks:,}")
    print(f"  CPC: {cpc:.2f} THB | CPM: {cpm:.2f} THB | CTR: {ctr:.2f}%")
    print(f"  Actions: {json.dumps(action_types, ensure_ascii=False)}")
    print(f"  Cost Per Action: {json.dumps(cost_per_action, ensure_ascii=False)}")
    print("-" * 65)

