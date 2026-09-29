import asyncio
import sys
import os
from telethon import TelegramClient
from telethon.sessions import StringSession

sys.stdout.reconfigure(encoding='utf-8')
sys.path.append('C:/Users/PAWIN/.gemini/antigravity/scratch/jeans-around-finance-os')
from backend.database import get_settings

async def main():
    settings = get_settings()
    client = TelegramClient(StringSession(settings['TELETHON_STRING_SESSION']), 2040, 'b18441a1ff607e10a989891a5462e627')
    await client.connect()
    
    msg = await client.get_messages(-4242902075, ids=194417)
    print("=== ORDER #43 DETAILS ===")
    print(msg.text)
    
    await client.disconnect()

asyncio.run(main())
