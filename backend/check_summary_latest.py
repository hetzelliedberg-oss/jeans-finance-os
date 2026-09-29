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
    # Check KKC orders
    entity_orders = await client.get_entity(-5366638194)
    print("KKC Orders chat (-5366638194) latest 3:")
    async for m in client.iter_messages(entity_orders, limit=3):
        print(f"Msg {m.id} ({m.date}):\n{m.text}\n---")
        
    # Check KKC summary
    entity_sum = await client.get_entity(-5383851414)
    print("\nKKC Summary chat (-5383851414) latest 2:")
    async for m in client.iter_messages(entity_sum, limit=2):
        print(f"Msg {m.id} ({m.date}):\n{m.text}\n---")
    await client.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
