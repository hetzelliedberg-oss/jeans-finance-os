import asyncio
import sys
from telethon import TelegramClient
from telethon.sessions import StringSession
from datetime import timezone, timedelta

sys.stdout.reconfigure(encoding='utf-8')
sys.path.append('C:/Users/PAWIN/.gemini/antigravity/scratch/jeans-around-finance-os')
from backend.database import get_settings, get_sku_cost_map
from backend.parser import parse_order_message

ONLINE_CHAT_ID = -4242902075
TZ_TH = timezone(timedelta(hours=7))

async def main():
    settings = get_settings()
    client = TelegramClient(StringSession(settings['TELETHON_STRING_SESSION']), 2040, 'b18441a1ff607e10a989891a5462e627')
    await client.connect()
    
    sku_map = get_sku_cost_map()
    # Test setting XRP68 to 430.0
    sku_map['XRP68'] = 430.0
    
    msgs = []
    async for msg in client.iter_messages(ONLINE_CHAT_ID, limit=100):
        dt = msg.date.astimezone(TZ_TH)
        d_str = dt.strftime('%Y-%m-%d')
        t_str = dt.strftime('%H:%M:%S')
        text = msg.text or msg.message or ''
        if text.strip() and ('สรุปออเดอร์' in text or 'โอน :' in text or 'ปลายทาง :' in text):
            if d_str == '2026-09-28':
                msgs.append((msg.id, d_str, t_str, text))
                
    msgs.sort(key=lambda x: (x[1], x[2]))
    
    print(f'Total messages on 2026-09-28: {len(msgs)}')
    for idx, (mid, d, t, txt) in enumerate(msgs, 1):
        actual_date = '2026-09-27' if t < '05:00:00' else '2026-09-28'
        parsed = parse_order_message(
            text=txt,
            source_channel='online',
            sku_cost_map=sku_map,
            order_date=actual_date,
            order_time=f'{d} {t}',
            message_id=str(mid)
        )
        if parsed:
            items_desc = []
            for it in parsed['items']:
                items_desc.append(f"{it['sku']}(size={it.get('size')}, qty={it['quantity']}, cost={it['unit_cost']})")
            items_str = ', '.join(items_desc)
            print(f"{idx:02d}. Msg {mid} | TargetDate:{actual_date} | Time:{t} | Cust:{parsed.get('customer_name','')} | Total:{parsed.get('total_sales',0)} | COGS:{parsed.get('cogs_total',0)} | Items: [{items_str}]")
        else:
            print(f"{idx:02d}. Msg {mid} FAILED TO PARSE: {repr(txt[:60])}")

if __name__ == '__main__':
    asyncio.run(main())
