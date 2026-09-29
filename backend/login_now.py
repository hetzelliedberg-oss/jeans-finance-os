import asyncio
import sqlite3
import sys
from telethon import TelegramClient
from telethon.sessions import StringSession

api_id = 2040
api_hash = 'b18441a1ff607e10a989891a5462e627'
phone = '+66830789329'
code = '27610'
code_hash = 'dec5e166c2630502b5'

async def main():
    client = TelegramClient(StringSession(''), api_id, api_hash)
    await client.connect()
    
    user = await client.sign_in(phone=phone, code=code, phone_code_hash=code_hash)
    print('Successfully signed in!', getattr(user, 'first_name', ''), getattr(user, 'phone', ''))
    
    session_str = client.session.save()
    print('Generated new session string length:', len(session_str))
    
    conn = sqlite3.connect('C:/Users/PAWIN/.gemini/antigravity/scratch/jeans-around-finance-os/data/finance_hub.db')
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('TELETHON_STRING_SESSION', ?)", (session_str,))
    conn.commit()
    conn.close()
    print('Saved session string to data/finance_hub.db')

if __name__ == '__main__':
    asyncio.run(main())
