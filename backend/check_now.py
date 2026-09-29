import asyncio, sqlite3, sys
from datetime import datetime, timezone, timedelta
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
    tz_th = timezone(timedelta(hours=7))
    start_utc = datetime(2026, 9, 24, 0, 0, 0, tzinfo=tz_th).astimezone(timezone.utc)
    end_utc = datetime(2026, 9, 24, 23, 59, 59, tzinfo=tz_th).astimezone(timezone.utc)
    entity = await client.get_entity(-4242902075)
    
    msgs = []
    async for msg in client.iter_messages(entity, offset_date=end_utc):
        if msg.date < start_utc:
            break
        msgs.append(msg)
        
    msgs.reverse()
    print(f"Total messages in chat today: {len(msgs)}")
    order_msgs = []
    for m in msgs:
        if m.text and any(k in m.text for k in ['สรุปออเดอร์', 'ปลายทาง', 'โอน']):
            order_msgs.append(m)
            
    print(f"Total order-like messages: {len(order_msgs)}")
    for idx, m in enumerate(order_msgs, 1):
        lines = [l.strip() for l in m.text.split('\n') if l.strip()]
        first_line = lines[0] if lines else ''
        th_dt = m.date.astimezone(tz_th).strftime('%H:%M:%S')
        ed = f" (EDITED {m.edit_date.astimezone(tz_th).strftime('%H:%M:%S')})" if m.edit_date else ""
        print(f"#{idx:2d} | Msg {m.id} | {th_dt}{ed} | {first_line[:40]}")
        
    # Also check what the database currently has!
    print("\n--- Current Database Orders for today ---")
    conn2 = sqlite3.connect('data/finance_hub.db')
    c2 = conn2.cursor()
    c2.execute("SELECT id, message_id, order_time, total_sales, raw_text FROM orders WHERE order_date = '2026-09-24' AND source_channel = 'online' ORDER BY order_time ASC")
    db_orders = c2.fetchall()
    print(f"Total online orders in DB: {len(db_orders)}")
    for idx, r in enumerate(db_orders, 1):
        fline = r[4].strip().split('\n')[0] if r[4] else ''
        print(f"DB #{idx:2d} | ID {r[0]} | Msg {r[1]} | {r[2]} | {fline[:30]}")
        
    # Also check storefront in DB
    c2.execute("SELECT id, message_id, order_time, total_sales, raw_text FROM orders WHERE order_date = '2026-09-24' AND source_channel = 'kkc' ORDER BY order_time ASC")
    db_k = c2.fetchall()
    print(f"Total kkc orders in DB: {len(db_k)}")
    for idx, r in enumerate(db_k, 1):
        print(f"DB KKC #{idx:2d} | ID {r[0]} | Msg {r[1]} | {r[2]}")
    conn2.close()

    await client.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
