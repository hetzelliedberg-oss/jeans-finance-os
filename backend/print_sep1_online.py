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
    
    print("=== PRINTING MESSAGES ON 2026-09-01 IN ONLINE CHAT ===")
    async for msg in client.iter_messages(ONLINE_CHAT_ID, limit=800):
        dt = msg.date.astimezone(TZ_TH)
        date_str = dt.strftime('%Y-%m-%d')
        if date_str == '2026-09-01':
            text = msg.text or msg.message or ""
            has_media = bool(msg.media)
            print(f"Msg ID: {msg.id} ({dt.strftime('%H:%M:%S')}) | Media: {has_media}")
            if text.strip():
                print(f"Text:\n{text.strip()}")
            else:
                print("(No text / Media only)")
            print("-" * 50)
            
    await client.disconnect()

asyncio.run(main())
