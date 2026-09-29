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

async def main():
    settings = get_settings()
    client = TelegramClient(StringSession(settings['TELETHON_STRING_SESSION']), 2040, 'b18441a1ff607e10a989891a5462e627')
    await client.connect()
    
    dialogs = await client.get_dialogs()
    print(f"Total dialogs: {len(dialogs)}")
    print("=== DIALOGS WITH ACTIVITY IN 2026 ===")
    for d in dialogs:
        if d.is_group or d.is_channel:
            # check latest message date
            if d.date:
                dt_th = d.date.astimezone(TZ_TH)
                if dt_th.year == 2026:
                    print(f"ID: {d.id:<18} | Name: {d.name:<40} | Latest: {dt_th.strftime('%Y-%m-%d %H:%M')}")
                    
    await client.disconnect()

asyncio.run(main())
