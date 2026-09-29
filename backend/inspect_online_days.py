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
    
    print("=== INSPECT ALL MESSAGES IN ONLINE CHAT SINCE SEP 15 ===")
    count_by_date = {}
    sample_texts = {}
    
    async for msg in client.iter_messages(ONLINE_CHAT_ID, limit=1000):
        dt = msg.date.astimezone(TZ_TH)
        date_str = dt.strftime('%Y-%m-%d')
        if date_str < '2026-09-01':
            break
        text = msg.text or msg.message or ""
        count_by_date[date_str] = count_by_date.get(date_str, 0) + 1
        if date_str not in sample_texts and text.strip():
            sample_texts[date_str] = text.strip()[:100]

    print(f"{'Date':<12} | Total Messages in TG Group")
    print("-" * 35)
    for d in sorted(count_by_date.keys()):
        print(f"{d:<12} | {count_by_date[d]}")
        
    await client.disconnect()

asyncio.run(main())
