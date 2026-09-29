import asyncio, sqlite3, sys
from telethon import TelegramClient
from telethon.sessions import StringSession
from datetime import datetime, timezone, timedelta
from backend.parser import parse_order_message, extract_business_date
from backend.database import get_sku_cost_map, get_db_connection
from backend.order_importer import save_order_to_db

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
    end_utc = datetime(2026, 9, 27, 23, 59, 59, tzinfo=tz_th).astimezone(timezone.utc)
    sku_cost_map = get_sku_cost_map()
    
    entity = await client.get_entity(-5366638194)
    print("=== KKC STOREFRONT MESSAGES IN CHAT -5366638194 (SEP 24 - 27) ===")
    
    orders = []
    async for msg in client.iter_messages(entity, offset_date=end_utc):
        if msg.date < start_utc:
            break
        if msg.text and any(k in msg.text for k in ["รหัสสินค้า", "โอน", "เงินสด"]):
            th_dt = msg.date.astimezone(tz_th)
            d_str = extract_business_date(th_dt, msg.text)
            p = parse_order_message(
                text=msg.text,
                source_channel="kkc",
                sku_cost_map=sku_cost_map,
                order_date=d_str,
                order_time=th_dt.strftime("%Y-%m-%d %H:%M:%S"),
                message_id=str(msg.id)
            )
            if p:
                orders.append((msg.id, th_dt.strftime("%Y-%m-%d %H:%M:%S"), d_str, p, msg.text))
                
    orders.reverse()
    print(f"Total storefront order messages found: {len(orders)}")
    for mid, t_str, d_str, p, raw in orders:
        fline = raw.strip().split('\n')[0]
        print(f"Msg {mid} | {t_str} | Date: {d_str} | Pcs: {p.get('total_pieces')} | Sales: {p.get('total_sales'):7.2f} | Method: {p.get('payment_method'):7s} | {fline}")
        save_order_to_db(p)
        
    await client.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
