import sqlite3, requests, json, sys
sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('data/finance_hub.db')
c = conn.cursor()
c.execute("SELECT value FROM settings WHERE key = 'FB_ACCESS_TOKEN'")
token = c.fetchone()[0]
c.execute("SELECT value FROM settings WHERE key = 'AD_ACCOUNT_ID'")
act_id = c.fetchone()[0]
conn.close()

print(f"Ad Account ID: {act_id}")
print(f"Token length: {len(token)}")

# Query Meta Insights API
url = f"https://graph.facebook.com/v20.0/{act_id}/insights"

for month_num, month_name in [(8, "สิงหาคม 2026"), (9, "กันยายน 2026")]:
    since_date = f"2026-0{month_num}-01"
    until_date = f"2026-0{month_num}-31" if month_num == 8 else "2026-09-27"
    
    params = {
        "access_token": token,
        "level": "campaign",
        "time_range": json.dumps({"since": since_date, "until": until_date}),
        "fields": "campaign_name,spend,reach,impressions,clicks,inline_link_clicks,actions",
        "limit": 500
    }
    
    res = requests.get(url, params=params, timeout=25)
    data = res.json()
    
    if "error" in data:
        print(f"Error for {month_name}:", data["error"])
        continue
        
    entries = data.get("data", [])
    print(f"\n=======================================================")
    print(f"  FACT ADS: {month_name} ({since_date} ถึง {until_date})")
    print(f"=======================================================")
    
    kkc_campaigns = []
    tot_kkc_spend = 0.0
    tot_kkc_reach = 0
    tot_kkc_impr = 0
    tot_kkc_clicks = 0
    tot_kkc_link_clicks = 0
    tot_kkc_actions = 0
    tot_kkc_messaging = 0
    tot_kkc_post_eng = 0
    
    all_campaigns_count = len(entries)
    print(f"Total campaigns in account: {all_campaigns_count}")
    
    for item in entries:
        c_name = item.get("campaign_name", "")
        if "ขอนแก่น" in c_name:
            spend = float(item.get("spend", 0.0))
            reach = int(item.get("reach", 0))
            impr = int(item.get("impressions", 0))
            clicks = int(item.get("clicks", 0))
            link_clicks = int(item.get("inline_link_clicks", 0))
            
            actions = item.get("actions", [])
            msg_count = 0
            post_eng = 0
            for a in actions:
                a_type = a.get("action_type", "")
                a_val = int(a.get("value", 0))
                if "message" in a_type or "conversation" in a_type:
                    msg_count += a_val
                if "post_engagement" in a_type or "page_engagement" in a_type:
                    post_eng += a_val
                    
            tot_kkc_spend += spend
            tot_kkc_reach += reach
            tot_kkc_impr += impr
            tot_kkc_clicks += clicks
            tot_kkc_link_clicks += link_clicks
            tot_kkc_actions += len(actions)
            tot_kkc_messaging += msg_count
            tot_kkc_post_eng += post_eng
            
            kkc_campaigns.append({
                "name": c_name,
                "spend": spend,
                "reach": reach,
                "impr": impr,
                "clicks": clicks,
                "link_clicks": link_clicks,
                "messaging": msg_count,
                "post_eng": post_eng
            })
            
    print(f"\n--- แคมเปญขอนแก่น (KKC) ทั้งหมด {len(kkc_campaigns)} แคมเปญ ---")
    for c_info in sorted(kkc_campaigns, key=lambda x: x["spend"], reverse=True):
        print(f"• {c_info['name']} | ยอดเงิน: {c_info['spend']:,.2f} บ. | Reach: {c_info['reach']:,} | Clicks: {c_info['clicks']:,} | ทักข้อความ: {c_info['messaging']:,} | Engagement: {c_info['post_eng']:,}")
        
    print(f"\n>>> สรุปยอดรวม ADS ขอนแก่น {month_name}:")
    print(f"  - ยอดใช้จ่ายค่าแอด (Spend):        {tot_kkc_spend:12,.2f} บาท")
    print(f"  - จำนวนการเข้าถึง (Reach):           {tot_kkc_reach:12,d} คน")
    print(f"  - ยอดการแสดงผล (Impressions):       {tot_kkc_impr:12,d} ครั้ง")
    print(f"  - จำนวนคลิกทั้งหมด (Clicks):          {tot_kkc_clicks:12,d} คลิก")
    print(f"  - จำนวนคลิกลิงก์ (Link Clicks):      {tot_kkc_link_clicks:12,d} คลิก")
    print(f"  - การมีส่วนร่วมกับโพสต์ (Engagement):   {tot_kkc_post_eng:12,d} ครั้ง")
    print(f"  - จำนวนการทักข้อความ (Messaging):     {tot_kkc_messaging:12,d} ครั้ง")
    if tot_kkc_reach > 0:
        cpr = tot_kkc_spend / tot_kkc_reach
        print(f"  - ต้นทุนต่อการเข้าถึง 1 คน (CPR):     {cpr:12.4f} บาท/คน (หรือพันคนละ {cpr*1000:,.2f} บ.)")
    if tot_kkc_clicks > 0:
        print(f"  - ต้นทุนต่อคลิก (CPC):                {tot_kkc_spend / tot_kkc_clicks:12.2f} บาท/คลิก")
