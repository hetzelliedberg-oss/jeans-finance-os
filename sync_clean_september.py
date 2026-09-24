import asyncio
import sqlite3
import sys
from datetime import datetime, timezone, timedelta
from telethon import TelegramClient
from telethon.sessions import StringSession
from backend.parser import parse_order_message, extract_business_date
from backend.database import get_sku_cost_map, get_db_connection
from backend.order_importer import save_order_to_db

sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('data/finance_hub.db')
c = conn.cursor()
c.execute("SELECT value FROM settings WHERE key = 'TELETHON_STRING_SESSION'")
session_str = c.fetchone()[0]
conn.close()

api_id = 2040
api_hash = "b18441a1ff607e10a989891a5462e627"

ONLINE_CHAT_ID = -4242902075
KKC_ORDERS_CHAT_ID = -5366638194

async def main():
    client = TelegramClient(StringSession(session_str), api_id, api_hash)
    await client.connect()
    
    tz_th = timezone(timedelta(hours=7))
    start_utc = datetime(2026, 9, 1, 0, 0, 0, tzinfo=tz_th).astimezone(timezone.utc)
    end_utc = datetime(2026, 9, 24, 23, 59, 59, tzinfo=tz_th).astimezone(timezone.utc)
    
    sku_cost_map = get_sku_cost_map()
    sender_cache = {}
    
    # 1. Fetch Online
    online_entity = await client.get_entity(ONLINE_CHAT_ID)
    online_orders = []
    async for msg in client.iter_messages(online_entity, offset_date=end_utc):
        if msg.date < start_utc:
            break
        if msg.text and any(k in msg.text for k in ["สรุปออเดอร์", "ปลายทาง", "โอน"]):
            th_dt_obj = msg.date.astimezone(tz_th)
            th_dt = th_dt_obj.strftime("%Y-%m-%d %H:%M:%S")
            d_str = extract_business_date(th_dt_obj, msg.text or "")
            sender = "unknown"
            if msg.sender_id:
                if msg.sender_id not in sender_cache:
                    try:
                        s = await client.get_entity(msg.sender_id)
                        sender_cache[msg.sender_id] = getattr(s, 'first_name', '') or getattr(s, 'title', 'unknown')
                    except:
                        sender_cache[msg.sender_id] = "unknown"
                sender = sender_cache[msg.sender_id]
                
            p = parse_order_message(
                text=msg.text,
                source_channel="online",
                sku_cost_map=sku_cost_map,
                sender_name=sender,
                order_date=d_str,
                order_time=th_dt,
                message_id=str(msg.id)
            )
            if p:
                online_orders.append((msg.id, p))
                
    # 2. Fetch KKC
    kkc_entity = await client.get_entity(KKC_ORDERS_CHAT_ID)
    kkc_orders = []
    async for msg in client.iter_messages(kkc_entity, offset_date=end_utc):
        if msg.date < start_utc:
            break
        if msg.text and any(k in msg.text for k in ["รหัสสินค้า", "โอน", "เงินสด"]):
            th_dt = msg.date.astimezone(tz_th).strftime("%Y-%m-%d %H:%M:%S")
            d_str = th_dt.split()[0]
            sender = "unknown"
            if msg.sender_id:
                if msg.sender_id not in sender_cache:
                    try:
                        s = await client.get_entity(msg.sender_id)
                        sender_cache[msg.sender_id] = getattr(s, 'first_name', '') or getattr(s, 'title', 'unknown')
                    except:
                        sender_cache[msg.sender_id] = "unknown"
                sender = sender_cache[msg.sender_id]
                
            p = parse_order_message(
                text=msg.text,
                source_channel="kkc",
                sku_cost_map=sku_cost_map,
                sender_name=sender,
                order_date=d_str,
                order_time=th_dt,
                message_id=str(msg.id)
            )
            if p:
                p["order_date"] = d_str
                p["order_time"] = th_dt
                kkc_orders.append((msg.id, p))
                
    # 3. Synchronize cleanly into DB
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Clean September orders & items
    cur.execute("DELETE FROM order_items WHERE order_id IN (SELECT id FROM orders WHERE order_date >= '2026-09-01')")
    cur.execute("DELETE FROM orders WHERE order_date >= '2026-09-01'")
    conn.commit()
    conn.close()
    
    # Save all orders
    for _, ord_data in online_orders:
        save_order_to_db(ord_data)
        
    for _, ord_data in kkc_orders:
        save_order_to_db(ord_data)
        
    print(f"Successfully synced {len(online_orders)} online orders and {len(kkc_orders)} KKC storefront orders for September 2026.")
    
    await client.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
