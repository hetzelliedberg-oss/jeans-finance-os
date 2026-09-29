import sys
import re
import sqlite3

sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('C:/Users/PAWIN/.gemini/antigravity/scratch/jeans-around-finance-os/data/finance_hub.db')
c = conn.cursor()

c.execute('SELECT sku, cost FROM sku_costs')
raw_costs = dict(c.fetchall())

core_costs = {}
for s, cost in raw_costs.items():
    m = re.match(r'^(AR\d+|XRP\d+)', s.upper())
    if m:
        core = m.group(1)
        if core not in core_costs or cost > 0:
            core_costs[core] = cost
    else:
        core_costs[s.upper()] = cost

c.execute('''
SELECT o.source_channel, o.order_date, oi.sku, oi.quantity
FROM orders o
JOIN order_items oi ON o.id = oi.order_id
WHERE o.order_date >= '2026-08-01' AND o.order_date <= '2026-09-30'
''')
all_items = c.fetchall()

missing_core_skus = {}
for ch, d, sku, qty in all_items:
    m = re.search(r'(AR\d+|XRP\d+)', sku.upper())
    core_sku = m.group(1) if m else sku.upper()
    if core_sku == 'XRP5':
        core_sku = 'XRP05'
        
    cost = core_costs.get(core_sku)
    if cost is None or cost == 0.0:
        if core_sku not in missing_core_skus:
            missing_core_skus[core_sku] = {
                'channels': set(),
                'months': set(),
                'dates': set(),
                'total_qty': 0,
                'raw_variants': set()
            }
        missing_core_skus[core_sku]['channels'].add(ch)
        missing_core_skus[core_sku]['months'].add(d[:7])
        missing_core_skus[core_sku]['dates'].add(d)
        missing_core_skus[core_sku]['total_qty'] += qty
        missing_core_skus[core_sku]['raw_variants'].add(sku)

print(f'Distinct missing Core SKUs across Aug-Sep 2026: {len(missing_core_skus)}')
print('='*80)
for core, info in sorted(missing_core_skus.items()):
    mths = ', '.join(sorted(info['months']))
    chs = ', '.join(sorted(info['channels']))
    variants = ', '.join(sorted(info['raw_variants']))
    d_list = ', '.join(sorted(info['dates']))
    print(f"{core:<8} | ขายรวม {info['total_qty']:>2} ตัว | เดือน: {mths:<15} | ช่องทาง: {chs:<12} | วันที่พบ: {d_list}")
