import sqlite3
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('data/finance_hub.db')
c = conn.cursor()

# Check all orders in October
c.execute("""
    SELECT o.id, o.order_date, o.source_channel, o.total_pieces, o.total_sales, o.cogs_total, o.raw_text
    FROM orders o
    WHERE o.order_date >= '2026-10-01' AND o.order_date <= '2026-10-14'
    ORDER BY o.order_date, o.id
""")
orders = c.fetchall()

print(f"Total October orders in DB: {len(orders)}")

issues = []
for r in orders:
    oid, odate, ch, total_pcs, sales, cogs, raw = r
    
    # Get items
    c.execute("SELECT sku, quantity, unit_cost, total_cost FROM order_items WHERE order_id = ?", (oid,))
    items = c.fetchall()
    
    items_pcs = sum(it[1] for it in items)
    items_cost = sum(it[3] for it in items)
    
    # Check if pieces mismatch
    if items_pcs != total_pcs:
        issues.append({
            'id': oid, 'date': odate, 'ch': ch, 'type': 'PIECES_MISMATCH',
            'order_pcs': total_pcs, 'items_pcs': items_pcs, 'sales': sales, 'raw': raw[:100]
        })
        
    # Check if any item has 0 cost
    for it in items:
        if it[2] == 0.0 or it[3] == 0.0:
            issues.append({
                'id': oid, 'date': odate, 'ch': ch, 'type': 'ZERO_COST_ITEM',
                'sku': it[0], 'qty': it[1], 'sales': sales, 'raw': raw[:100]
            })
            
    # Check if cogs mismatch
    if abs(cogs - items_cost) > 1.0:
        issues.append({
            'id': oid, 'date': odate, 'ch': ch, 'type': 'COGS_MISMATCH',
            'cogs_total': cogs, 'items_cost': items_cost, 'sales': sales
        })

print(f"Total issues found: {len(issues)}")
for iss in issues[:30]:
    print(iss)

conn.close()
