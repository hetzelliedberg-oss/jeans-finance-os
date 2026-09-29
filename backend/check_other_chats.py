import asyncio
import sys
import os
from telethon import TelegramClient
from telethon.sessions import StringSession
from datetime import timezone, timedelta

sys.stdout.reconfigure(encoding='utf-8')
sys.path.append('C:/Users/PAWIN/.gemini/antigravity/scratch/jeans-around-finance-os')
from backend.database import get_settings

TZ_TH = timezone(timedelta(hours=7))

CHATS_TO_CHECK = [
    (-4231674892, "Jeans around ยีนส์แฟชั่นพร้อมส่ง (-4231674892)"),
    (-1002216847523, "Jeans around ยีนส์แฟชั่นพร้อมส่ง (-1002216847523)"),
    (-4787571087, "Jeans Arounds พรีเมี่ยม10฿ (-4787571087)"),
    (-5059272766, "Jeans around Brand (-5059272766)"),
    (-834262801, "ออเดอร์ shoppy/lasada/tiktok (-834262801)"),
    (-667705550, "LINE @ เสื้อผ้า (-667705550)")
]

async def main():
    settings = get_settings()
    client = TelegramClient(StringSession(settings['TELETHON_STRING_SESSION']), 2040, 'b18441a1ff607e10a989891a5462e627')
    await client.connect()
    
    for chat_id, title in CHATS_TO_CHECK:
        print(f"\n=== CHECKING: {title} ===")
        msg_count = 0
        latest_date = None
        sample_msg = ""
        try:
            async for msg in client.iter_messages(chat_id, limit=20):
                msg_count += 1
                dt = msg.date.astimezone(TZ_TH)
                if not latest_date:
                    latest_date = dt.strftime("%Y-%m-%d %H:%M:%S")
                text = msg.text or msg.message or ""
                if text.strip() and not sample_msg:
                    sample_msg = text.strip()[:100]
            print(f"  Messages found: {msg_count}, Latest date: {latest_date}")
            if sample_msg:
                print(f"  Sample: {repr(sample_msg)}")
        except Exception as e:
            print(f"  Error reading {chat_id}: {e}")
            
    await client.disconnect()

asyncio.run(main())
