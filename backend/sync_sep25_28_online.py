import asyncio
import sys
import sqlite3
from telethon import TelegramClient
from telethon.sessions import StringSession
from datetime import timezone, timedelta

sys.stdout.reconfigure(encoding='utf-8')
sys.path.append('C:/Users/PAWIN/.gemini/antigravity/scratch/jeans-around-finance-os')
from backend.database import get_settings, get_sku_cost_map
from backend.parser import parse_order_message
from backend.order_importer import save_order_to_db

ONLINE_CHAT_ID = -4242902075
TZ_TH = timezone(timedelta(hours=7))

async def main():
    settings = get_settings()
    client = TelegramClient(StringSession(settings['TELETHON_STRING_SESSION']), 2040, 'b18441a1ff607e10a989891a5462e627')
    await client.connect()
    
    sku_map = get_sku_cost_map()
    
    msgs = []
    async for msg in client.iter_messages(ONLINE_CHAT_ID, limit=250):
        dt = msg.date.astimezone(TZ_TH)
        d_str = dt.strftime('%Y-%m-%d')
        t_str = dt.strftime('%H:%M:%S')
        text = msg.text or msg.message or ''
        if text.strip() and ('สรุปออเดอร์' in text or 'โอน :' in text or 'ปลายทาง :' in text):
            if d_str >= '2026-09-25':
                msgs.append((msg.id, d_str, t_str, text))
                
    msgs.sort(key=lambda x: (x[1], x[2]))
    print(f'Syncing {len(msgs)} online order messages to DB...')
    
    imported_count = 0
    for mid, d, t, txt in msgs:
        actual_date = d
        # 5 orders on 28th early morning (< 05:00) belong to 2026-09-27
        if d == '2026-09-28' and t < '05:00:00':
            actual_date = '2026-09-27'
            
        parsed = parse_order_message(
            text=txt,
            source_channel='online',
            sku_cost_map=sku_map,
            order_date=actual_date,
            order_time=f'{d} {t}',
            message_id=str(mid)
        )
        if parsed:
            save_order_to_db(parsed)
            imported_count += 1
            
    print(f'Successfully imported/updated {imported_count} orders in DB.')
    
    # Verify in DB
    conn = sqlite3.connect('C:/Users/PAWIN/.gemini/antigravity/scratch/jeans-around-finance-os/data/finance_hub.db')
    c = conn.cursor()
    c.execute('''
        SELECT order_date, COUNT(*), SUM(total_pieces), SUM(total_sales), SUM(cogs_total)
        FROM orders
        WHERE source_channel = 'online' AND order_date >= '2026-09-24'
        GROUP BY order_date
        ORDER BY order_date
    ''')
    print('\nDB Verification (Online 24-28 Sep):')
    print('Date | Orders | Pieces | Sales (THB) | COGS (THB)')
    print('---|---|---|---|---')
    for r in c.fetchall():
        print(f'{r[0]} | {r[1]} | {r[2]} | {r[3]:,.2f} | {r[4]:,.2f}')

if __name__ == '__main__':
    asyncio.run(main())
