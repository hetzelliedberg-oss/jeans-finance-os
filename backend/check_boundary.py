import asyncio, sqlite3, sys
from telethon import TelegramClient
from telethon.sessions import StringSession
sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('data/finance_hub.db')
c = conn.cursor()
c.execute("SELECT value FROM settings WHERE key = 'TELETHON_STRING_SESSION'")
session_str = c.fetchone()[0]
conn.close()

async def main():
    client = TelegramClient(StringSession(session_str), 2040, 'b18441a1ff607e10a989891a5462e627')
    await client.connect()
    entity = await client.get_entity(-4242902075)
    for mid in [194836, 194843]:
        m = await client.get_messages(entity, ids=mid)
        if m:
            print(f"Msg {m.id} at {m.date}:\n{m.text.strip()}\n" + "="*40)
    await client.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
