import asyncio
import sqlite3
import sys
from datetime import datetime, timezone, timedelta
from telethon import TelegramClient
from telethon.sessions import StringSession
from backend.parser import parse_order_message
from backend.database import get_sku_cost_map

sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('data/finance_hub.db')
c = conn.cursor()
c.execute("SELECT value FROM settings WHERE key = 'TELETHON_STRING_SESSION'")
session_str = c.fetchone()[0]
conn.close()

api_id = 2040
api_hash = 'b18441a1ff607e10a989891a5462e627'

ONLINE_CHAT_ID = -4242902075
KKC_ORDERS_CHAT_ID = -5366638194
KKC_SUMMARY_CHAT_ID = -5383851414

async def main():
    client = TelegramClient(StringSession(session_str), api_id, api_hash)
    await client.connect()
    
    tz_th = timezone(timedelta(hours=7))
    start_utc = datetime(2026, 9, 24, 0, 0, 0, tzinfo=tz_th).astimezone(timezone.utc)
    end_utc = datetime(2026, 9, 24, 23, 59, 59, tzinfo=tz_th).astimezone(timezone.utc)
    
    sku_cost_map = get_sku_cost_map()
    
    print("==================================================")
    print("AUDITING TODAY (2026-09-24) LIVE FROM TELEGRAM")
    print("==================================================")
    
    # 1. KKC Summary Chat
    print("\n--- 1. KKC Manager Daily Report (Chat -5383851414) ---")
    try:
        sum_entity = await client.get_entity(KKC_SUMMARY_CHAT_ID)
        reports = []
        async for msg in client.iter_messages(sum_entity, limit=10):
            th_dt = msg.date.astimezone(tz_th).strftime('%Y-%m-%d %H:%M:%S')
            if msg.text:
                reports.append((msg.id, th_dt, msg.text))
        for mid, mtime, mtext in reports:
            print(f"Msg {mid} ({mtime}):\n{mtext.strip()}\n" + "-"*40)
    except Exception as e:
        print(f"Error fetching KKC summary: {e}")
        
    # 2. Online Orders
    print("\n--- 2. ONLINE ORDERS (Chat -4242902075) ---")
    online_entity = await client.get_entity(ONLINE_CHAT_ID)
    online_msgs = []
    async for msg in client.iter_messages(online_entity, offset_date=end_utc):
        if msg.date < start_utc:
            break
        if msg.text and any(k in msg.text for k in ["สรุปออเดอร์", "ปลายทาง", "โอน"]):
            th_dt = msg.date.astimezone(tz_th).strftime("%Y-%m-%d %H:%M:%S")
            edit_dt = msg.edit_date.astimezone(tz_th).strftime("%Y-%m-%d %H:%M:%S") if msg.edit_date else ""
            p = parse_order_message(
                text=msg.text,
                source_channel="online",
                sku_cost_map=sku_cost_map,
                order_date="2026-09-24",
                order_time=th_dt,
                message_id=str(msg.id)
            )
            online_msgs.append({
                "id": msg.id,
                "time": th_dt,
                "edit_time": edit_dt,
                "parsed": p,
                "text": msg.text
            })
            
    online_msgs.reverse()
    tot_online_sales = sum(m["parsed"].get("total_sales", 0.0) for m in online_msgs if m["parsed"])
    tot_online_pcs = sum(m["parsed"].get("total_pieces", 1) for m in online_msgs if m["parsed"])
    tot_online_cod = sum(m["parsed"].get("cod_amount", 0.0) for m in online_msgs if m["parsed"] and m["parsed"].get("payment_method") == "COD")
    tot_online_trans = sum(m["parsed"].get("transfer_amount", 0.0) for m in online_msgs if m["parsed"] and m["parsed"].get("payment_method") != "COD")
    
    print(f"Total Online Orders: {len(online_msgs)} orders | {tot_online_pcs} pcs | {tot_online_sales:,.2f} THB (COD: {tot_online_cod:,.2f}, Transfer: {tot_online_trans:,.2f})")
    for idx, m in enumerate(online_msgs, 1):
        p = m["parsed"]
        lines = [l.strip() for l in m["text"].split("\n") if l.strip()]
        hdr = lines[0] if lines else ""
        cust = ""
        for l in lines:
            if "ชื่อ" in l:
                cust = l.split(":", 1)[-1].strip()
                break
        ed = f" [EDITED {m['edit_time'][11:]}]" if m["edit_time"] else ""
        print(f"#{idx:2d} | Msg {m['id']} ({m['time'][11:]}){ed} | {p.get('total_pieces',1)} pcs | {p.get('total_sales',0.0):7.2f} THB | {p.get('payment_method')} | {hdr[:15]} | {cust[:20]}")

    # 3. KKC Storefront Orders
    print("\n--- 3. KKC STOREFRONT ORDERS (Chat -5366638194) ---")
    kkc_entity = await client.get_entity(KKC_ORDERS_CHAT_ID)
    kkc_msgs = []
    async for msg in client.iter_messages(kkc_entity, offset_date=end_utc):
        if msg.date < start_utc:
            break
        if msg.text and any(k in msg.text for k in ["รหัสสินค้า", "โอน", "เงินสด"]):
            th_dt = msg.date.astimezone(tz_th).strftime("%Y-%m-%d %H:%M:%S")
            edit_dt = msg.edit_date.astimezone(tz_th).strftime("%Y-%m-%d %H:%M:%S") if msg.edit_date else ""
            p = parse_order_message(
                text=msg.text,
                source_channel="kkc",
                sku_cost_map=sku_cost_map,
                order_date="2026-09-24",
                order_time=th_dt,
                message_id=str(msg.id)
            )
            kkc_msgs.append({
                "id": msg.id,
                "time": th_dt,
                "edit_time": edit_dt,
                "parsed": p,
                "text": msg.text
            })
            
    kkc_msgs.reverse()
    tot_kkc_sales = sum(m["parsed"].get("total_sales", 0.0) for m in kkc_msgs if m["parsed"])
    tot_kkc_pcs = sum(m["parsed"].get("total_pieces", 1) for m in kkc_msgs if m["parsed"])
    tot_kkc_cash = sum(m["parsed"].get("total_sales", 0.0) for m in kkc_msgs if m["parsed"] and m["parsed"].get("payment_method") == "cash")
    tot_kkc_trans = sum(m["parsed"].get("total_sales", 0.0) for m in kkc_msgs if m["parsed"] and m["parsed"].get("payment_method") != "cash")
    
    print(f"Total KKC Orders: {len(kkc_msgs)} orders | {tot_kkc_pcs} pcs | {tot_kkc_sales:,.2f} THB (Cash: {tot_kkc_cash:,.2f}, Transfer: {tot_kkc_trans:,.2f})")
    for idx, m in enumerate(kkc_msgs, 1):
        p = m["parsed"]
        ed = f" [EDITED {m['edit_time'][11:]}]" if m["edit_time"] else ""
        first_line = m["text"].split("\n")[0].strip()
        print(f"#{idx:2d} | Msg {m['id']} ({m['time'][11:]}){ed} | {p.get('total_pieces',1)} pcs | {p.get('total_sales',0.0):7.2f} THB | {p.get('payment_method')} | {first_line[:30]}")

    # 4. Compare with Database
    print("\n--- 4. COMPARISON WITH DATABASE TODAY ---")
    conn = sqlite3.connect('data/finance_hub.db')
    c = conn.cursor()
    c.execute("""
        SELECT source_channel, count(*), sum(total_pieces), sum(total_sales)
        FROM orders
        WHERE order_date = '2026-09-24'
        GROUP BY source_channel
    """)
    db_rows = c.fetchall()
    print("Database currently holds for 2026-09-24:")
    for r in db_rows:
        print(f"  Channel '{r[0]}': {r[1]} orders | {r[2]} pcs | {r[3]:,.2f} THB")
    conn.close()

    await client.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
