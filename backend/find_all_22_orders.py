import asyncio
import sys
import os
from telethon import TelegramClient
from telethon.sessions import StringSession
from datetime import timezone, timedelta

sys.stdout.reconfigure(encoding='utf-8')
sys.path.append('C:/Users/PAWIN/.gemini/antigravity/scratch/jeans-around-finance-os')
from backend.database import get_settings

ONLINE_CHAT_ID = -4242902075
TZ_TH = timezone(timedelta(hours=7))

async def main():
    settings = get_settings()
    client = TelegramClient(StringSession(settings['TELETHON_STRING_SESSION']), 2040, 'b18441a1ff607e10a989891a5462e627')
    await client.connect()
    
    orders_22 = []
    
    async for msg in client.iter_messages(ONLINE_CHAT_ID, limit=300):
        dt = msg.date.astimezone(TZ_TH)
        date_str = dt.strftime('%Y-%m-%d')
        if date_str == '2026-09-22':
            text = msg.text or msg.message or ""
            if "สรุปออเดอร์" in text or "ปลายทาง :" in text or "โอน :" in text:
                orders_22.append((msg.id, dt.strftime('%H:%M:%S'), text.strip()))
                
    print(f"Total order messages found for 2026-09-22: {len(orders_22)}")
    # Sort chronologically
    for idx, (mid, t, txt) in enumerate(reversed(orders_22), 1):
        first_line = txt.split('\n')[0]
        second_line = txt.split('\n')[1] if len(txt.split('\n')) > 1 else ""
        print(f"[{idx:02d}] Msg {mid} at {t} | {repr(first_line)} | {repr(second_line)}")
        
    await client.disconnect()

asyncio.run(main())
