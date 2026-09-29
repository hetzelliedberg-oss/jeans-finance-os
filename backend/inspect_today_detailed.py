import asyncio
import sqlite3
import sys
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

api_id = 2040
api_hash = 'b18441a1ff607e10a989891a5462e627'
ONLINE_CHAT_ID = -4242902075
KKC_ORDERS_CHAT_ID = -5366638194

async def main():
    client = TelegramClient(StringSession(session_str), api_id, api_hash)
    await client.connect()
    tz_th = timezone(timedelta(hours=7))
    start_utc = datetime(2026, 9, 24, 0, 0, 0, tzinfo=tz_th).astimezone(timezone.utc)
    end_utc = datetime(2026, 9, 24, 23, 59, 59, tzinfo=tz_th).astimezone(timezone.utc)
    sku_cost_map = get_sku_cost_map()
    
    online_entity = await client.get_entity(ONLINE_CHAT_ID)
    orders = []
    async for msg in client.iter_messages(online_entity, offset_date=end_utc):
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
    print(f"=== ONLINE ORDERS 2026-09-24 (Total: {len(orders)}) ===")
    tot_sales = 0.0
    tot_pcs = 0
    tot_cod = 0.0
    tot_trans = 0.0
    for idx, (mid, mtime, p, text) in enumerate(orders, 1):
        items_summary = ', '.join([f"{it.get('sku')}({it.get('qty')})" for it in p.get('items', [])])
        pcs = p.get('total_pieces', 1)
        sales = p.get('total_sales', 0.0)
        method = p.get('payment_method', 'โอน')
        cod = p.get('cod_amount', 0.0)
        trans = p.get('transfer_amount', 0.0)
        tot_sales += sales
        tot_pcs += pcs
        tot_cod += cod
        tot_trans += trans
        print(f"#{idx:2d} | Msg {mid} | {mtime[11:]} | Pcs: {pcs} | Sales: {sales:7.2f} | Method: {method:7s} | COD: {cod:7.2f} | Trans: {trans:7.2f} | Items: {items_summary}")
        
    print(f"\nONLINE SUMMARY: {len(orders)} orders | {tot_pcs} pcs | {tot_sales:,.2f} THB (COD: {tot_cod:,.2f}, Trans: {tot_trans:,.2f})")

    # KKC
    kkc_entity = await client.get_entity(KKC_ORDERS_CHAT_ID)
    k_orders = []
    async for msg in client.iter_messages(kkc_entity, offset_date=end_utc):
        if msg.date < start_utc:
            break
        if msg.text and any(k in msg.text for k in ['รหัสสินค้า', 'โอน', 'เงินสด']):
            th_dt = msg.date.astimezone(tz_th).strftime('%Y-%m-%d %H:%M:%S')
            p = parse_order_message(
                text=msg.text,
                source_channel='kkc',
                sku_cost_map=sku_cost_map,
                order_date='2026-09-24',
                order_time=th_dt,
                message_id=str(msg.id)
            )
            k_orders.append((msg.id, th_dt, p, msg.text))
            
    k_orders.reverse()
    print(f"\n=== KKC STOREFRONT ORDERS 2026-09-24 (Total: {len(k_orders)}) ===")
    k_sales = 0.0
    k_pcs = 0
    k_cash = 0.0
    k_trans = 0.0
    for idx, (mid, mtime, p, text) in enumerate(k_orders, 1):
        items_summary = ', '.join([f"{it.get('sku')}({it.get('qty')})" for it in p.get('items', [])])
        pcs = p.get('total_pieces', 1)
        sales = p.get('total_sales', 0.0)
        method = p.get('payment_method', 'เงินสด')
        if method == 'เงินสด':
            k_cash += sales
        else:
            k_trans += sales
        k_sales += sales
        k_pcs += pcs
        print(f"#{idx:2d} | Msg {mid} | {mtime[11:]} | Pcs: {pcs} | Sales: {sales:7.2f} | Method: {method:7s} | Items: {items_summary}")
        
    print(f"\nKKC SUMMARY: {len(k_orders)} orders | {k_pcs} pcs | {k_sales:,.2f} THB (Cash: {k_cash:,.2f}, Trans: {k_trans:,.2f})")

    await client.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
