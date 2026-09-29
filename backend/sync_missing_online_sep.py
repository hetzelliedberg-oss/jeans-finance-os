import asyncio
import sys
import os
import sqlite3
from telethon import TelegramClient
from telethon.sessions import StringSession
from datetime import timezone, timedelta

sys.stdout.reconfigure(encoding='utf-8')
sys.path.append('C:/Users/PAWIN/.gemini/antigravity/scratch/jeans-around-finance-os')
from backend.database import get_settings, get_sku_cost_map
from backend.parser import parse_order_message
from backend.order_importer import save_order_to_db

ONLINE_CHAT_ID = -4242902075
TZ_TH = timezone(timedelta(hours=7))

async def main():
    settings = get_settings()
    client = TelegramClient(StringSession(settings['TELETHON_STRING_SESSION']), 2040, 'b18441a1ff607e10a989891a5462e627')
    await client.connect()
    
    sku_map = get_sku_cost_map()
    
    conn = sqlite3.connect('data/finance_hub.db')
    cur = conn.cursor()
    
    # Get all existing message_ids in orders for online
    cur.execute("SELECT message_id FROM orders WHERE source_channel = 'online'")
    existing_msg_ids = set(str(r[0]) for r in cur.fetchall() if r[0])
    
    print(f"Existing Online orders in DB: {len(existing_msg_ids)}")
    
    missing_msgs = []
    
    async for msg in client.iter_messages(ONLINE_CHAT_ID, limit=1200):
        dt = msg.date.astimezone(TZ_TH)
        date_str = dt.strftime('%Y-%m-%d')
        if date_str < '2026-09-01':
            break
            
        text = msg.text or msg.message or ""
        if not text.strip():
            continue
            
        if "สรุปออเดอร์" in text or "ปลายทาง :" in text or "โอน :" in text:
            msg_id = str(msg.id)
            if msg_id not in existing_msg_ids:
                missing_msgs.append((msg.id, date_str, dt.strftime('%H:%M:%S'), text.strip()))

    print(f"Total missing orders in September: {len(missing_msgs)}")
    
    newly_imported = 0
    for mid, d_str, t_str, txt in missing_msgs:
        parsed = parse_order_message(
            text=txt,
            source_channel="online",
            sku_cost_map=sku_map,
            order_date=d_str,
            order_time=f"{d_str} {t_str}",
            message_id=str(mid)
        )
        if parsed:
            # Force insert without duplicate blocking
            save_order_to_db(parsed)
            newly_imported += 1
            print(f"  + Imported Msg {mid} on {d_str} {t_str}: {parsed.get('customer_name', '')} ({parsed.get('total_sales', 0)} THB)")
        else:
            print(f"  FAILED to parse Msg {mid} on {d_str}: {repr(txt[:60])}")

    print(f"\nSuccessfully imported {newly_imported} missing online orders for September!")
    await client.disconnect()

asyncio.run(main())
