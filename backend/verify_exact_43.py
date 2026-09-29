import asyncio, sqlite3, sys
from datetime import datetime, timezone, timedelta
from telethon import TelegramClient
from telethon.sessions import StringSession
from backend.parser import parse_order_message
from backend.database import get_sku_cost_map

sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('data/finance_hub.db')
c = conn.cursor()
c.execute("SELECT value FROM settings WHERE key = 'TELETHON_STRING_SESSION'")
session_str = c.fetchone()[0]
conn.close()

async def check():
    client = TelegramClient(StringSession(session_str), 2040, 'b18441a1ff607e10a989891a5462e627')
    await client.connect()
    sku_cost_map = get_sku_cost_map()
    entity = await client.get_entity(-4242902075)
    
    # Get all orders from Msg 194648 (order 1) to Msg 194843 (order 43)
    tz_th = timezone(timedelta(hours=7))
    start_utc = datetime(2026, 9, 24, 6, 0, 0, tzinfo=tz_th).astimezone(timezone.utc)
    end_utc = datetime(2026, 9, 24, 23, 59, 59, tzinfo=tz_th).astimezone(timezone.utc)
    
    orders = []
    async for msg in client.iter_messages(entity, offset_date=end_utc):
        if msg.date < start_utc:
            break
        if msg.text and any(k in msg.text for k in ['สรุปออเดอร์', 'ปลายทาง', 'โอน']):
            th_dt = msg.date.astimezone(tz_th).strftime('%Y-%m-%d %H:%M:%S')
            p = parse_order_message(
                text=msg.text,
                source_channel='online',
                sku_cost_map=sku_cost_map,
                order_date='2026-09-24',
                order_time=th_dt,
                message_id=str(msg.id)
            )
            orders.append((msg.id, th_dt, p, msg.text))
            
    orders.reverse()
    print(f"Total orders from 06:00 AM to now: {len(orders)}")
    tot_sales = sum(p.get('total_sales', 0.0) for _, _, p, _ in orders)
    tot_pcs = sum(p.get('total_pieces', 1) for _, _, p, _ in orders)
    tot_cod = sum(p.get('cod_amount', 0.0) for _, _, p, _ in orders if p.get('payment_method') == 'ปลายทาง')
    tot_trans = sum(p.get('transfer_amount', 0.0) for _, _, p, _ in orders if p.get('payment_method') != 'ปลายทาง')
    
    print(f"Totals: {len(orders)} orders | {tot_pcs} pcs | {tot_sales:,.2f} THB (COD: {tot_cod:,.2f}, Trans: {tot_trans:,.2f})")
    for idx, (mid, mtime, p, text) in enumerate(orders, 1):
        first_line = text.strip().split('\n')[0]
        cust = ''
        for l in text.split('\n'):
            if 'ชื่อ' in l:
                cust = l.split(':', 1)[-1].strip()
                break
        print(f"#{idx:2d} | Msg {mid} | {mtime[11:]} | Pcs: {p.get('total_pieces')} | Sales: {p.get('total_sales'):7.2f} | Method: {p.get('payment_method'):7s} | Hdr: {first_line[:15]} | {cust[:20]}")
        
    await client.disconnect()

if __name__ == '__main__':
    asyncio.run(check())
