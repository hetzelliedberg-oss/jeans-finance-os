import sqlite3, sys, re, asyncio
from datetime import datetime, timezone, timedelta
from telethon import TelegramClient
from telethon.sessions import StringSession

sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('data/finance_hub.db')
c = conn.cursor()
c.execute("SELECT value FROM settings WHERE key = 'TELETHON_STRING_SESSION'")
session_str = c.fetchone()[0]

# 1. Fetch DB totals by day for August & September
c.execute('''
    SELECT substr(order_date, 1, 10) as d, count(*), sum(total_pieces), sum(total_sales),
           sum(case when payment_method IN ('สด', 'เงินสด', 'cash') then total_sales else 0 end) as cash,
           sum(case when payment_method NOT IN ('สด', 'เงินสด', 'cash') then total_sales else 0 end) as trans
    FROM orders
    WHERE source_channel='kkc' AND (order_date LIKE '2026-08%' OR order_date LIKE '2026-09%')
    GROUP BY d
    ORDER BY d
''')
db_data = {r[0]: {"bills": r[1], "pcs": r[2], "sales": r[3], "cash": r[4], "trans": r[5]} for r in c.fetchall()}
conn.close()

async def get_manager_reports():
    client = TelegramClient(StringSession(session_str), 2040, 'b18441a1ff607e10a989891a5462e627')
    await client.connect()
    entity_sum = await client.get_entity(-5383851414)
    
    reports = {}
    async for msg in client.iter_messages(entity_sum, limit=300):
        if not msg.text:
            continue
        t = msg.text.strip()
        m_date = re.search(r'(\d{1,2})\s*(กันยายน|ก\.ย\.|สิงหาคม|ส\.ค\.)\s*(?:25)?(69|2026)?', t)
        if m_date:
            day = int(m_date.group(1))
            mo_str = m_date.group(2)
            month = 9 if 'กันยา' in mo_str or 'ก.ย.' in mo_str else 8
            date_key = f"2026-{month:02d}-{day:02d}"
            
            m_tr = re.search(r'(?:โอน|ยอดขายโอน)\s*[:=]?\s*([0-9,]+)', t)
            m_cs = re.search(r'(?:สด|ยอดขายเงินสด|เงินสด)\s*[:=]?\s*([0-9,]+)', t)
            m_tot = re.search(r'(?:ยอดรวม|รวม)\s*[:=]?\s*([0-9,]+)', t)
            
            tr = float(m_tr.group(1).replace(',', '')) if m_tr else 0.0
            cs = float(m_cs.group(1).replace(',', '')) if m_cs else 0.0
            tot = float(m_tot.group(1).replace(',', '')) if m_tot else (tr + cs)
            
            if date_key not in reports:
                reports[date_key] = {"total": tot, "trans": tr, "cash": cs, "msg_id": msg.id}
    await client.disconnect()
    return reports

async def main():
    mgr_reports = await get_manager_reports()
    
    for month_num, month_name in [(8, "สิงหาคม 2026"), (9, "กันยายน 2026")]:
        print(f"\n=======================================================")
        print(f"  ตาราง FACT สาขาขอนแก่น (KKC) - {month_name}")
        print(f"=======================================================")
        days_in_month = 31 if month_num == 8 else 27 # up to today 27 Sep
        
        tot_b = tot_p = tot_s = tot_c = tot_t = tot_mgr = 0
        
        for d in range(1, days_in_month + 1):
            d_str = f"2026-{month_num:02d}-{d:02d}"
            db_row = db_data.get(d_str, {"bills": 0, "pcs": 0, "sales": 0.0, "cash": 0.0, "trans": 0.0})
            mgr = mgr_reports.get(d_str, {"total": db_row["sales"], "trans": db_row["trans"], "cash": db_row["cash"]})
            
            diff = db_row["sales"] - mgr["total"]
            
            tot_b += db_row["bills"]
            tot_p += db_row["pcs"]
            tot_s += db_row["sales"]
            tot_c += db_row["cash"]
            tot_t += db_row["trans"]
            tot_mgr += mgr["total"]
            
            print(f"{d_str} | {db_row['bills']:2d} บิล | {db_row['pcs']:2d} ตัว | ขายจริง: {db_row['sales']:8.2f} บ. (สด: {db_row['cash']:7.2f}, โอน: {db_row['trans']:7.2f}) | ผจก.ปิดกะ: {mgr['total']:8.2f} บ. | Diff: {diff:5.2f}")
            
        print(f"-------------------------------------------------------")
        print(f"รวมทั้งเดือน: {tot_b} บิล | {tot_p} ตัว | ยอดรวม: {tot_s:,.2f} บ. (สด: {tot_c:,.2f}, โอน: {tot_t:,.2f}) | ผจก.: {tot_mgr:,.2f} บ. | รวม Diff: {tot_s - tot_mgr:.2f}")

if __name__ == '__main__':
    asyncio.run(main())
