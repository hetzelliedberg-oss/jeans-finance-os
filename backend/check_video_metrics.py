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
    "fields": "campaign_name,spend,reach,impressions,clicks,inline_link_clicks,cpc,cpm,ctr,video_thruplay_watched_actions,video_p25_watched_actions,video_p50_watched_actions,video_p75_watched_actions,video_p100_watched_actions,cost_per_thruplay",
    "limit": 500
}

res = requests.get(url, params=params, timeout=25).json()

print("=========================================================================")
print("  DEEP METRICS FOR NEW CAMPAIGNS (VIDEO & CLICKS: 2026-09-23 to 2026-09-27)")
print("=========================================================================")

for row in res.get("data", []):
    cname = row.get("campaign_name", "")
    if "ขอนแก่น" in cname:
        sp = float(row.get("spend", 0.0))
        rc = int(row.get("reach", 0))
        im = int(row.get("impressions", 0))
        cl = int(row.get("clicks", 0))
        lcl = int(row.get("inline_link_clicks", 0))
        cpc = float(row.get("cpc", 0.0)) if row.get("cpc") else 0.0
        ctr = float(row.get("ctr", 0.0)) if row.get("ctr") else 0.0
        cpm = float(row.get("cpm", 0.0)) if row.get("cpm") else 0.0
        
        thru = sum(int(x.get("value", 0)) for x in row.get("video_thruplay_watched_actions", []))
        p25 = sum(int(x.get("value", 0)) for x in row.get("video_p25_watched_actions", []))
        p50 = sum(int(x.get("value", 0)) for x in row.get("video_p50_watched_actions", []))
        p75 = sum(int(x.get("value", 0)) for x in row.get("video_p75_watched_actions", []))
        p100 = sum(int(x.get("value", 0)) for x in row.get("video_p100_watched_actions", []))
        
        cp_thru = float(row.get("cost_per_thruplay", [{}])[0].get("value", 0.0)) if row.get("cost_per_thruplay") else 0.0
        
        print(f"\nแคมเปญ: {cname}")
        print(f"  - งบที่ใช้ (Spend):           {sp:8.2f} บาท")
        print(f"  - การเข้าถึง (Reach):          {rc:8,d} คน")
        print(f"  - CPM (ต้นทุนต่อ 1,000 วิว):    {cpm:8.2f} บาท")
        print(f"  - คลิกทั้งหมด (Clicks):         {cl:8,d} คลิก (CPC: {cpc:.2f} บ.)")
        print(f"  - คลิกลิงก์ (Link Clicks):      {lcl:8,d} คลิก (ต้นทุน/คลิกลิงก์: {sp/lcl if lcl>0 else 0:.2f} บ.)")
        print(f"  - อัตราการคลิก (CTR):          {ctr:8.2f}%")
        print(f"  - ดู 25% ของคลิป:              {p25:8,d} ครั้ง")
        print(f"  - ดู 50% ของคลิป:              {p50:8,d} ครั้ง")
        print(f"  - ดู 75% ของคลิป:              {p75:8,d} ครั้ง")
        print(f"  - ดูคลิปจนจบ 100%:             {p100:8,d} ครั้ง")
        print(f"  - ThruPlay (ดู 15 วิ หรือจบ):   {thru:8,d} ครั้ง")
        print(f"  - ต้นทุนต่อ ThruPlay:          {cp_thru:8.4f} บาท/ครั้ง (หรือ {cp_thru*100:.2f} สตางค์)")
