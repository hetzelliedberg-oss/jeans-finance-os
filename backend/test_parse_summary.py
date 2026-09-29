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
    
    msgs = []
    async for msg in client.iter_messages(ONLINE_CHAT_ID, limit=200):
        dt = msg.date.astimezone(TZ_TH)
        d_str = dt.strftime('%Y-%m-%d')
        t_str = dt.strftime('%H:%M:%S')
        text = msg.text or msg.message or ''
        if text.strip() and ('สรุปออเดอร์' in text or 'โอน :' in text or 'ปลายทาง :' in text):
            if d_str >= '2026-09-25':
                msgs.append((msg.id, d_str, t_str, text))
                
    msgs.sort(key=lambda x: (x[1], x[2]))
    
    daily_stats = {}
    for mid, d, t, txt in msgs:
        actual_date = d
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
            if actual_date not in daily_stats:
                daily_stats[actual_date] = {'orders': 0, 'pieces': 0, 'sales': 0.0, 'cogs': 0.0, 'missing': []}
            daily_stats[actual_date]['orders'] += 1
            daily_stats[actual_date]['pieces'] += parsed['total_pieces']
            daily_stats[actual_date]['sales'] += parsed['total_sales']
            daily_stats[actual_date]['cogs'] += parsed['cogs_total']
            for it in parsed['items']:
                if it['unit_cost'] == 0.0:
                    daily_stats[actual_date]['missing'].append(it['sku'])

    for d in sorted(daily_stats.keys()):
        st = daily_stats[d]
        orders = st['orders']
        pieces = st['pieces']
        sales = st['sales']
        cogs = st['cogs']
        missing = set(st['missing'])
        print(f"Date {d}: Orders={orders}, Pieces={pieces}, Sales={sales:,.2f} THB, COGS={cogs:,.2f} THB, MissingCostSKUs={missing}")

if __name__ == '__main__':
    asyncio.run(main())
