import asyncio
import sys
import os
import re
from telethon import TelegramClient
from telethon.sessions import StringSession
from datetime import timezone, timedelta

sys.stdout.reconfigure(encoding='utf-8')
sys.path.append('C:/Users/PAWIN/.gemini/antigravity/scratch/jeans-around-finance-os')
from backend.database import get_settings, get_sku_cost_map
from backend.parser import parse_order_message

ONLINE_CHAT_ID = -4242902075
TZ_TH = timezone(timedelta(hours=7))

async def main():
    settings = get_settings()
    client = TelegramClient(StringSession(settings['TELETHON_STRING_SESSION']), 2040, 'b18441a1ff607e10a989891a5462e627')
    await client.connect()
    
    sku_map = get_sku_cost_map()
    
    print("=== SCANNING ALL MESSAGES IN ONLINE CHAT (SEP 1 - SEP 22) ===")
    
    order_like_msgs = []
    parsed_ok = []
    parsed_failed = []
    
    async for msg in client.iter_messages(ONLINE_CHAT_ID, limit=1200):
        dt = msg.date.astimezone(TZ_TH)
        date_str = dt.strftime('%Y-%m-%d')
        if date_str < '2026-09-01':
            break
        text = msg.text or msg.message or ""
        if not text.strip():
            continue
            
        # Is it order-like?
        is_order_like = (
            "สรุปออเดอร์" in text 
            or "จำนวน :" in text 
            or ("โอน :" in text and "ปลายทาง :" in text)
            or ("ชื่อ :" in text and ("รหัส :" in text or "เบอร์ :" in text))
        )
        
        if is_order_like:
            order_like_msgs.append((msg.id, date_str, text))
            parsed = parse_order_message(text=text, source_channel="online", sku_cost_map=sku_map)
            if parsed:
                parsed_ok.append((msg.id, date_str, parsed))
            else:
                parsed_failed.append((msg.id, date_str, text))

    print(f"Total order-like messages in TG chat: {len(order_like_msgs)}")
    print(f"Parsed OK: {len(parsed_ok)}")
    print(f"Parsed FAILED: {len(parsed_failed)}")
    
    # Check by date
    from collections import Counter
    by_d = Counter(m[1] for m in order_like_msgs)
    print("\nOrder-like messages by date in Telegram:")
    for d, c in sorted(by_d.items()):
        print(f"  {d}: {c} orders")
        
    if parsed_failed:
        print(f"\nFailed messages sample (first 3):")
        for f in parsed_failed[:3]:
            print(f"Msg {f[0]} on {f[1]}:\n{repr(f[2][:100])}\n")
            
    await client.disconnect()

asyncio.run(main())
