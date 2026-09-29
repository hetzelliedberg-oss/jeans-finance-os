import asyncio
import sys
import os
from collections import defaultdict
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
    
    print("=== SCANNING TELEGRAM ONLINE CHAT (jeans around 2) ACROSS ALL 2026 ===")
    
    parsed_by_month = defaultdict(lambda: {"count": 0, "sales": 0.0, "pieces": 0, "dates": set()})
    total_msgs = 0
    
    async for msg in client.iter_messages(ONLINE_CHAT_ID, limit=None):
        total_msgs += 1
        dt = msg.date.astimezone(TZ_TH)
        date_str = dt.strftime('%Y-%m-%d')
        if date_str < '2026-01-01':
            print(f"Reached {date_str} < 2026-01-01. Stopping.")
            break
            
        text = msg.text or msg.message or ""
        if not text.strip():
            continue
            
        ym = date_str[:7]
        
        # Check if message has orders
        parsed = parse_order_message(text=text, source_channel="online", sku_cost_map=sku_map, order_date=date_str)
        if parsed:
            b = parsed_by_month[ym]
            b["count"] += 1
            b["sales"] += parsed.get("total_sales", 0.0)
            b["pieces"] += parsed.get("total_pieces", 1)
            b["dates"].add(date_str)

        if total_msgs % 1000 == 0:
            print(f"Scanned {total_msgs} msgs... currently at {date_str}")
            
    print(f"\nScan finished! Total scanned msgs: {total_msgs}")
    print(f"{'Month':<8} | {'Days':<5} | {'Orders':<7} | {'Pieces':<7} | {'Sales (THB)':<14}")
    print("-" * 55)
    for ym in sorted(parsed_by_month.keys()):
        b = parsed_by_month[ym]
        print(f"{ym:<8} | {len(b['dates']):<5} | {b['count']:<7} | {b['pieces']:<7} | {b['sales']:>12,.2f}")
        
    await client.disconnect()

asyncio.run(main())
