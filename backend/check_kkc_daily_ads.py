import sqlite3, requests, json, sys
sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('data/finance_hub.db')
c = conn.cursor()
c.execute("SELECT value FROM settings WHERE key = 'FB_ACCESS_TOKEN'")
token = c.fetchone()[0]
c.execute("SELECT value FROM settings WHERE key = 'AD_ACCOUNT_ID'")
act_id = c.fetchone()[0]
conn.close()

url = f'https://graph.facebook.com/v20.0/{act_id}/insights'

params = {
    'access_token': token,
    'level': 'campaign',
    'time_range': json.dumps({'since': '2026-09-23', 'until': '2026-09-27'}),
    'time_increment': 1,
    'fields': 'campaign_name,spend,reach,clicks,inline_link_clicks,actions,date_start',
    'limit': 500
}
res = requests.get(url, params=params, timeout=25).json()
print("=== DAILY BREAKDOWN OF KKC ADS (SEP 23 - SEP 27) ===")
for row in sorted(res.get('data', []), key=lambda x: (x.get('date_start', ''), x.get('campaign_name', ''))):
    if 'ขอนแก่น' in row.get('campaign_name', ''):
        cname = row['campaign_name']
        d = row['date_start']
        sp = float(row.get('spend', 0))
        cl = int(row.get('clicks', 0))
        rc = int(row.get('reach', 0))
        actions = {a['action_type']: a['value'] for a in row.get('actions', [])}
        msg = actions.get('onsite_conversion.total_messaging_connection', 0)
        print(f"{d} | {cname:42s} | Spend: {sp:6.2f} บ. | Reach: {rc:5,d} | Clicks: {cl:3,d} | Msg: {msg}")
