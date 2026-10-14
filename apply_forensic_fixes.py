import sqlite3

conn = sqlite3.connect('data/finance_hub.db')
c = conn.cursor()

# 1. Fix ID 8909: total_pieces = 2
c.execute("UPDATE orders SET total_pieces = 2 WHERE id = 8909")

# 2. Fix ID 8942: Add free shirt 174 THB to items and update cogs_total = 713.40, total_pieces = 2
c.execute("UPDATE orders SET total_pieces = 2, cogs_total = 713.40 WHERE id = 8942")
c.execute("SELECT id FROM order_items WHERE order_id = 8942 AND sku LIKE '%เสื้อ%'")
if not c.fetchone():
    c.execute("""
        INSERT INTO order_items (order_id, sku, size, color, quantity, unit_cost, total_cost)
        VALUES (8942, 'แถมเสื้อเหลือง', 'M', 'เหลือง', 1, 174.0, 174.0)
    """)

# 3. Fix ID 8949: AR37 (504) + XRP69 (440) + 3 shirts (3*174=522) = 1466.0, total_pieces = 5
c.execute("UPDATE orders SET total_pieces = 5, cogs_total = 1466.0 WHERE id = 8949")
c.execute("DELETE FROM order_items WHERE order_id = 8949")
c.execute("INSERT INTO order_items (order_id, sku, size, color, quantity, unit_cost, total_cost) VALUES (8949, 'AR37', 'XL', '', 1, 504.0, 504.0)")
c.execute("INSERT INTO order_items (order_id, sku, size, color, quantity, unit_cost, total_cost) VALUES (8949, 'XRP69', 'L', '', 1, 440.0, 440.0)")
c.execute("INSERT INTO order_items (order_id, sku, size, color, quantity, unit_cost, total_cost) VALUES (8949, 'เสื้อครีม', 'L', 'ครีม', 2, 174.0, 348.0)")
c.execute("INSERT INTO order_items (order_id, sku, size, color, quantity, unit_cost, total_cost) VALUES (8949, 'เสื้อฟ้า', 'M', 'ฟ้า', 1, 174.0, 174.0)")

# 4. Fix ID 9007: JA001 (174) + JA002 (174) + XRP68ฟ้า (446) + XRP68ดำ (446) = 1240.0, total_pieces = 4
c.execute("UPDATE orders SET total_pieces = 4, cogs_total = 1240.0 WHERE id = 9007")
c.execute("DELETE FROM order_items WHERE order_id = 9007")
c.execute("INSERT INTO order_items (order_id, sku, size, color, quantity, unit_cost, total_cost) VALUES (9007, 'JA001', 'XL', '', 1, 174.0, 174.0)")
c.execute("INSERT INTO order_items (order_id, sku, size, color, quantity, unit_cost, total_cost) VALUES (9007, 'JA002', 'XL', '', 1, 174.0, 174.0)")
c.execute("INSERT INTO order_items (order_id, sku, size, color, quantity, unit_cost, total_cost) VALUES (9007, 'XRP68ฟ้า', '3XL', 'ฟ้า', 1, 446.0, 446.0)")
c.execute("INSERT INTO order_items (order_id, sku, size, color, quantity, unit_cost, total_cost) VALUES (9007, 'XRP68ดำ', '3XL', 'ดำ', 1, 446.0, 446.0)")

# 5. Fix ID 9022: Thanyanan Khompipot was placed on 13 Oct 11:03 AM -> assign true_date = '2026-10-13'
c.execute("UPDATE orders SET order_date = '2026-10-13' WHERE id = 9022")

conn.commit()
conn.close()
print("Applied all 5 forensic fixes to finance_hub.db successfully!")
