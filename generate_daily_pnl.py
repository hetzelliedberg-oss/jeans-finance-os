import sqlite3
import sys
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8')
conn = sqlite3.connect('data/finance_hub.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()

def get_day_pnl(date_str):
    d = datetime.strptime(date_str, "%Y-%m-%d")
    
    # 1. Orders
    cur.execute("""
        SELECT * FROM orders 
        WHERE order_date = ? AND status != 'cancelled'
    """, (date_str,))
    orders = cur.fetchall()
    
    online_orders = [o for o in orders if o["source_channel"] == "online"]
    kkc_orders = [o for o in orders if o["source_channel"] in ["kkc", "storefront_kkc"]]
    
    on_orders = len(online_orders)
    on_pcs = sum(o["total_pieces"] for o in online_orders)
    on_sales = sum(o["total_sales"] for o in online_orders)
    on_cogs = sum(o["cogs_total"] for o in online_orders)
    on_cod = sum(o["cod_amount"] for o in online_orders)
    on_gp = on_sales - on_cogs
    
    kkc_orders_count = len(kkc_orders)
    kkc_pcs = sum(o["total_pieces"] for o in kkc_orders)
    kkc_sales = sum(o["total_sales"] for o in kkc_orders)
    kkc_cogs = sum(o["cogs_total"] for o in kkc_orders)
    kkc_gp = kkc_sales - kkc_cogs
    
    tot_orders = on_orders + kkc_orders_count
    tot_pcs = on_pcs + kkc_pcs
    tot_sales = on_sales + kkc_sales
    tot_cogs = on_cogs + kkc_cogs
    tot_gp = tot_sales - tot_cogs
    
    # 2. Ads
    cur.execute("SELECT online_spend, kkc_spend, total_spend FROM daily_fb_ads WHERE date = ?", (date_str,))
    ad_row = cur.fetchone()
    on_ads = ad_row["online_spend"] if ad_row else 0.0
    kkc_ads = ad_row["kkc_spend"] if ad_row else 0.0
    tot_ads = on_ads + kkc_ads
    
    # 3. Online expenses
    # Labor 1132/day, Comm 10/pc, Misc 3/order, COD 2.14%
    on_labor = 1132.0 if on_orders > 0 or on_sales > 0 else 0.0
    # Wait, in finance_engine.py, does labor apply every calendar day?
    # In finance_engine.py: online_labor = 1132.0 * days_count
    on_labor = 1132.0
    on_comm = on_pcs * 10.0
    on_misc = on_orders * 3.0
    on_cod_fee = on_cod * 0.0214
    on_exp = on_labor + on_comm + on_misc + on_cod_fee + on_ads
    on_np = on_gp - on_exp
    
    # 4. KKC expenses
    import calendar
    kkc_rent = round(27214.0 / calendar.monthrange(d.year, d.month)[1], 2)
    kkc_labor = 500.0 if d.weekday() in [4, 5, 6] else 460.0
    kkc_misc = kkc_orders_count * 6.0
    kkc_exp = kkc_rent + kkc_labor + kkc_misc + kkc_ads
    kkc_np = kkc_gp - kkc_exp
    
    tot_exp = on_exp + kkc_exp
    tot_np = tot_gp - tot_exp
    
    return {
        "date": date_str,
        "tot_orders": tot_orders, "tot_pcs": tot_pcs, "tot_sales": tot_sales,
        "tot_cogs": tot_cogs, "tot_gp": tot_gp, "tot_ads": tot_ads, "tot_exp": tot_exp, "tot_np": tot_np,
        "on_orders": on_orders, "on_pcs": on_pcs, "on_sales": on_sales, "on_cogs": on_cogs, "on_gp": on_gp, "on_exp": on_exp, "on_np": on_np,
        "kkc_orders": kkc_orders_count, "kkc_pcs": kkc_pcs, "kkc_sales": kkc_sales, "kkc_cogs": kkc_cogs, "kkc_gp": kkc_gp, "kkc_exp": kkc_exp, "kkc_np": kkc_np,
    }

def print_month_pnl(month_prefix, days):
    print(f"\n==================== P&L FOR {month_prefix} ====================")
    print("| วันที่ | ออเดอร์ | ชิ้น | ยอดขาย (Sales) | ต้นทุนสินค้า (COGS) | กำไรขั้นต้น (GP) | ค่าใช้จ่ายรวม (Exp) | กำไรสุทธิ (Net Profit) |")
    print("| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |")
    
    m_orders, m_pcs, m_sales, m_cogs, m_gp, m_exp, m_np = 0, 0, 0.0, 0.0, 0.0, 0.0, 0.0
    
    for day in range(1, days + 1):
        dt_str = f"{month_prefix}-{day:02d}"
        res = get_day_pnl(dt_str)
        m_orders += res["tot_orders"]
        m_pcs += res["tot_pcs"]
        m_sales += res["tot_sales"]
        m_cogs += res["tot_cogs"]
        m_gp += res["tot_gp"]
        m_exp += res["tot_exp"]
        m_np += res["tot_np"]
        
        np_str = f"฿{res['tot_np']:,.2f}" if res['tot_np'] >= 0 else f"-฿{abs(res['tot_np']):,.2f}"
        print(f"| {res['date']} | {res['tot_orders']} | {res['tot_pcs']} | ฿{res['tot_sales']:,.2f} | ฿{res['tot_cogs']:,.2f} | ฿{res['tot_gp']:,.2f} | ฿{res['tot_exp']:,.2f} | {np_str} |")
        
    m_np_str = f"฿{m_np:,.2f}" if m_np >= 0 else f"-฿{abs(m_np):,.2f}"
    print(f"| **รวมทั้งเดือน** | **{m_orders}** | **{m_pcs}** | **฿{m_sales:,.2f}** | **฿{m_cogs:,.2f}** | **฿{m_gp:,.2f}** | **฿{m_exp:,.2f}** | **{m_np_str}** |")

print_month_pnl("2026-09", 30)
print_month_pnl("2026-08", 31)
