import asyncio, sqlite3, sys
from telethon import TelegramClient
from telethon.sessions import StringSession
from datetime import datetime, timezone, timedelta
import re

sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('data/finance_hub.db')
c = conn.cursor()
c.execute("SELECT value FROM settings WHERE key = 'TELETHON_STRING_SESSION'")
session_str = c.fetchone()[0]
conn.close()

async def main():
    client = TelegramClient(StringSession(session_str), 2040, 'b18441a1ff607e10a989891a5462e627')
    await client.connect()
    entity_sum = await client.get_entity(-5383851414)
    
    tz_th = timezone(timedelta(hours=7))
    print("=== ALL KKC MANAGER REPORTS FOR AUGUST & SEPTEMBER 2026 ===")
    
    reports = {}
    async for msg in client.iter_messages(entity_sum, limit=250):
        if not msg.text:
            continue
        t = msg.text.strip()
        # Look for date pattern like 27 กันยายน 69 or 12/9/69 or สิงหาคม
        m_date = re.search(r'(\d{1,2})\s*(กันยายน|ก\.ย\.|สิงหาคม|ส\.ค\.)\s*(?:25)?(69|2026)?', t)
        if m_date:
            day = int(m_date.group(1))
            mo_str = m_date.group(2)
            month = 9 if 'กันยา' in mo_str or 'ก.ย.' in mo_str else 8
            date_key = f"2026-{month:02d}-{day:02d}"
            
            # Extract transfer, cash, total
            m_tr = re.search(r'(?:โอน|ยอดขายโอน)\s*[:=]?\s*([0-9,]+)', t)
            m_cs = re.search(r'(?:สด|ยอดขายเงินสด|เงินสด)\s*[:=]?\s*([0-9,]+)', t)
            m_tot = re.search(r'(?:ยอดรวม|รวม)\s*[:=]?\s*([0-9,]+)', t)
            
            tr = float(m_tr.group(1).replace(',', '')) if m_tr else 0.0
            cs = float(m_cs.group(1).replace(',', '')) if m_cs else 0.0
            tot = float(m_tot.group(1).replace(',', '')) if m_tot else (tr + cs)
            
            if date_key not in reports:
                reports[date_key] = {
                    "msg_id": msg.id,
                    "date": date_key,
                    "transfer": tr,
                    "cash": cs,
                    "total": tot,
                    "raw": t
                }
                
    for d in sorted(reports.keys()):
        r = reports[d]
        print(f"{d} | รวม: {r['total']:8.2f} บ. (โอน: {r['transfer']:8.2f}, สด: {r['cash']:8.2f}) | Msg {r['msg_id']}")
        
    await client.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
