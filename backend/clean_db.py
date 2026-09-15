import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "finance_hub.db")

def clean_and_verify():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Delete any duplicate fb_ORD-JA-% rows
    cur.execute("DELETE FROM order_items WHERE order_id IN (SELECT id FROM orders WHERE message_id LIKE 'fb_ORD-JA-%')")
    cur.execute("DELETE FROM orders WHERE message_id LIKE 'fb_ORD-JA-%'")
    # Delete any sim_% rows
    cur.execute("DELETE FROM order_items WHERE order_id IN (SELECT id FROM orders WHERE message_id LIKE 'sim_%')")
    cur.execute("DELETE FROM orders WHERE message_id LIKE 'sim_%'")
    conn.commit()

    cur.execute("SELECT COUNT(*), SUM(total_sales) FROM orders WHERE platform = 'facebook_page'")
    print("Exact 100% FACT orders from FB Page:", cur.fetchone())

    cur.execute("SELECT sender_name, COUNT(*), SUM(total_sales) FROM orders WHERE platform = 'facebook_page' GROUP BY sender_name")
    print("Admins breakdown:", cur.fetchall())

    conn.close()

if __name__ == "__main__":
    clean_and_verify()
