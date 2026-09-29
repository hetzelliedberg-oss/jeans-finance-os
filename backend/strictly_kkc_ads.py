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

print("==========================================================================")
print("  FACT DATA: เฉพาะแคมเปญที่มีชื่อว่า 'ขอนแก่น' เท่านั้น (STRICTLY 'ขอนแก่น')")
print("==========================================================================")

# 1. Compare August vs September (Full Month)
for m_num, m_name, s_date, e_date in [
    (8, "สิงหาคม 2026", "2026-08-01", "2026-08-31"),
    (9, "กันยายน 2026 (1-27 ก.ย.)", "2026-09-01", "2026-09-27"),
    ("recent", "ช่วง 4 วันล่าสุด (24-27 ก.ย.)", "2026-09-24", "2026-09-27")
]:
    params = {
        "access_token": token,
        "level": "campaign",
        "time_range": json.dumps({"since": s_date, "until": e_date}),
        "fields": "campaign_name,objective,spend,reach,impressions,clicks,inline_link_clicks,actions",
        "limit": 500
    }
    res = requests.get(url, params=params, timeout=25).json()
    entries = res.get("data", [])
    
    kkc_entries = [e for e in entries if "ขอนแก่น" in e.get("campaign_name", "")]
    
    print(f"\n>>> ช่วงเวลา: {m_name} ({s_date} ถึง {e_date})")
    print(f"จำนวนแคมเปญที่มีชื่อ 'ขอนแก่น': {len(kkc_entries)} แคมเปญ")
    
    tot_sp = 0.0
    tot_rc = 0
    tot_im = 0
    tot_cl = 0
    tot_lcl = 0
    tot_msg = 0
    tot_eng = 0
    
    for row in sorted(kkc_entries, key=lambda x: float(x.get("spend", 0)), reverse=True):
        cname = row.get("campaign_name", "")
        sp = float(row.get("spend", 0.0))
        rc = int(row.get("reach", 0))
        im = int(row.get("impressions", 0))
        cl = int(row.get("clicks", 0))
        lcl = int(row.get("inline_link_clicks", 0))
        
        actions = row.get("actions", [])
        msg = 0
        eng = 0
        for a in actions:
            atype = a.get("action_type", "")
            aval = int(a.get("value", 0))
            if atype in ["onsite_conversion.total_messaging_connection", "onsite_conversion.messaging_conversation_started_7d"]:
                msg = max(msg, aval)
            if "engagement" in atype:
                eng += aval
                
        tot_sp += sp
        tot_rc += rc
        tot_im += im
        tot_cl += cl
        tot_lcl += lcl
        tot_msg += msg
        tot_eng += eng
        
        cpc = (sp / cl) if cl > 0 else 0.0
        cpm = (sp / im * 1000) if im > 0 else 0.0
        cost_msg = (sp / msg) if msg > 0 else 0.0
        
        print(f"• {cname}")
        print(f"    Spend: {sp:8.2f} บ. | Reach: {rc:6,d} | Clicks: {cl:5,d} (Link: {lcl:4,d}) | ทักแชท: {msg:3d} คน | Eng: {eng:6,d} | ต้นทุน/ทัก: {cost_msg:6.2f} บ.")
        
    print(f"  ------------------------------------------------------------------------")
    print(f"  รวมทั้งช่วง ({m_name}):")
    print(f"    - ยอดใช้จ่าย (Spend):        {tot_sp:12,.2f} บาท")
    print(f"    - การเข้าถึง (Reach):         {tot_rc:12,d} คน")
    print(f"    - คลิกทั้งหมด (Clicks):       {tot_cl:12,d} คลิก")
    print(f"    - คลิกลิงก์ (Link Clicks):    {tot_lcl:12,d} คลิก")
    print(f"    - มีส่วนร่วม (Engagement):    {tot_eng:12,d} ครั้ง")
    print(f"    - คนทักแชทข้อความ (Messaging): {tot_msg:12,d} คน")
    if tot_msg > 0:
        print(f"    - ต้นทุนเฉลี่ยต่อคนทัก:        {tot_sp/tot_msg:12.2f} บาท/คนทัก")
    if tot_cl > 0:
        print(f"    - ต้นทุนเฉลี่ยต่อคลิก (CPC):    {tot_sp/tot_cl:12.2f} บาท/คลิก")
