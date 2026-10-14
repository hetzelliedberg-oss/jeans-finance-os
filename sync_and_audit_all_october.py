import sqlite3
import json
import re

conn = sqlite3.connect('data/finance_hub.db')
c = conn.cursor()

# 1. Master SKU costs
c.execute("SELECT sku, cost FROM sku_costs")
sku_costs = dict(c.fetchall())
sku_costs['XRP189'] = 395.0
sku_costs['AR189'] = 395.0
sku_costs['JA001'] = 174.0
sku_costs['JA002'] = 174.0
sku_costs['JR001'] = 174.0
sku_costs['JA001ฟ้า'] = 174.0
sku_costs['JA002เหลือง'] = 174.0
sku_costs['JA001สีฟ้า'] = 174.0

# 2. Load all raw orders
with open('all_oct_orders_day_by_day.json', 'r', encoding='utf-8') as f:
    raw_orders = json.load(f)

# Clear existing orders from Oct 1 to Oct 14 in DB
c.execute("SELECT id FROM orders WHERE order_date >= '2026-10-01' AND order_date <= '2026-10-14'")
existing_ids = [r[0] for r in c.fetchall()]
for oid in existing_ids:
    c.execute("DELETE FROM order_items WHERE order_id = ?", (oid,))
c.execute("DELETE FROM orders WHERE order_date >= '2026-10-01' AND order_date <= '2026-10-14'")

duplicate_ids = [9015] # 9015 is duplicate of 9011 (Esther Mevmev)
inserted_orders = 0

for o in raw_orders:
    oid = o['id']
    if oid in duplicate_ids:
        continue
        
    ch = o.get('source_channel')
    raw_date = o.get('order_date')
    raw_text = o.get('raw_text', '')
    total_sales = float(o.get('total_sales') or 0)
    
    # Accurate Date Assignment:
    true_date = raw_date
    
    if ch == 'kkc':
        # Use regex to find exact date
        m = re.search(r'วันที่\s*:\s*(\d{1,2})/(\d{1,2})/(?:25)?(69|26)?', raw_text)
        if m:
            day = int(m.group(1))
            true_date = f"2026-10-{day:02d}"
        else:
            true_date = raw_date
            
        # Exception: 9025 & 9028 were posted today 14 Oct at 14:46 & 14:59 (Today's actual sales where staff copy-pasted 13/10/69 template)
        if oid in [9025, 9028]:
            true_date = '2026-10-14'

    elif ch == 'online':
        # Batch from Oct 11 entered late on Oct 12 morning: IDs 8957 to 8982
        if 8957 <= oid <= 8982:
            true_date = '2026-10-11'
        # Batch from Oct 12: IDs 8983 to 8997
        elif 8983 <= oid <= 8997:
            true_date = '2026-10-12'
        # Batch from Oct 13: IDs 9001 to 9012
        elif 9001 <= oid <= 9012:
            true_date = '2026-10-13'
        # Batch from Oct 14: IDs 9013 to 9027
        elif 9013 <= oid <= 9027:
            true_date = '2026-10-14'
            
    # Calculate audited COGS
    cogs_total = 0.0
    items = o.get('items', [])
    
    if oid == 9006:
        cogs_total = 395.0
    elif oid == 9007:
        cogs_total = 174.0 * 2 + 446.0 * 2
    else:
        for it in items:
            sku = it.get('sku', '').strip()
            qty = int(it.get('quantity') or 1)
            cost = float(it.get('unit_cost') or 0)
            if cost == 0.0 and sku in sku_costs:
                cost = sku_costs[sku]
            cogs_total += cost * qty
            
    if cogs_total == 0.0:
        cogs_total = float(o.get('cogs_total') or 0)

    # Insert into orders
    c.execute("""
        INSERT INTO orders (
            id, source_channel, message_id, sender_name, order_date, order_time,
            raw_text, total_pieces, total_sales, payment_method, cod_amount,
            transfer_amount, cogs_total, commission_amount, status, created_at,
            customer_name, platform
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        oid, ch, o.get('message_id'), o.get('sender_name'),
        true_date, o.get('order_time'), raw_text,
        o.get('total_pieces'), total_sales, o.get('payment_method'),
        o.get('cod_amount'), o.get('transfer_amount'), cogs_total,
        o.get('commission_amount'), o.get('status'), o.get('created_at'),
        o.get('customer_name'), o.get('platform')
    ))
    
    for it in items:
        sku = it.get('sku', '').strip()
        qty = int(it.get('quantity') or 1)
        cost = float(it.get('unit_cost') or 0)
        if cost == 0.0 and sku in sku_costs:
            cost = sku_costs[sku]
        c.execute("""
            INSERT INTO order_items (
                order_id, sku, size, color, quantity, unit_cost, total_cost
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            oid, sku, it.get('size'), it.get('color'),
            qty, cost, cost * qty
        ))
        
    inserted_orders += 1

# Update daily_fb_ads for Oct 13 and Oct 14
ads_data = [
    ('2026-10-13', 6955.96, 282.92, 7238.88),
    ('2026-10-14', 5159.84, 250.30, 5410.14)
]

for dt, on_sp, kk_sp, tot_sp in ads_data:
    c.execute("SELECT date FROM daily_fb_ads WHERE date = ?", (dt,))
    row = c.fetchone()
    if row:
        c.execute("UPDATE daily_fb_ads SET online_spend = ?, kkc_spend = ?, total_spend = ?, updated_at = datetime('now') WHERE date = ?",
                  (on_sp, kk_sp, tot_sp, dt))
    else:
        c.execute("""
            INSERT INTO daily_fb_ads (date, online_spend, kkc_spend, total_spend, updated_at)
            VALUES (?, ?, ?, ?, datetime('now'))
        """, (dt, on_sp, kk_sp, tot_sp))

conn.commit()
conn.close()
print(f"Correctly synced {inserted_orders} audited orders into finance_hub.db with exact regex dates!")
