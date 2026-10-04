import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')

from backend.finance_engine import calculate_pnl

pnl_online = calculate_pnl('2026-09-01', '2026-09-30', 'online')
pnl_kkc = calculate_pnl('2026-09-01', '2026-09-30', 'kkc')

print("="*80)
print("TABLE 1: หน้าร้าน CENTRAL ขอนแก่น (KKC) - DAILY P&L STATEMENT (ก.ย. 2569)")
print("="*80)
print("| วันที่ | บิล | ชิ้น | ยอดขาย (฿) | ต้นทุน (฿) | กำไรขั้นต้น (฿) | ค่าเช่า (฿) | ค่าแรง (฿) | ค่าแอด (฿) | ค่าถุง (฿) | รวมค่าใช้จ่าย (฿) | กำไรสุทธิ (฿) | Margin% |")
print("| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |")

conn = sqlite3.connect('data/finance_hub.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# Get orders per day for kkc
cur.execute("""
SELECT order_date, COUNT(*) as bills, SUM(total_pieces) as pcs, SUM(total_sales) as sales, SUM(cogs_total) as cogs
FROM orders
WHERE source_channel = 'kkc' AND order_date >= '2026-09-01' AND order_date <= '2026-09-30'
GROUP BY order_date
""")
kkc_orders_map = {r['order_date']: r for r in cur.fetchall()}

# Get kkc ads per day
cur.execute("SELECT date, kkc_spend FROM daily_fb_ads WHERE date >= '2026-09-01' AND date <= '2026-09-30'")
kkc_ads_map = {r['date']: (r['kkc_spend'] or 0.0) for r in cur.fetchall()}

from datetime import datetime, timedelta
start_dt = datetime(2026, 9, 1)
tot_k_bills, tot_k_pcs, tot_k_sales, tot_k_cogs, tot_k_gp = 0, 0, 0.0, 0.0, 0.0
tot_k_rent, tot_k_labor, tot_k_ads, tot_k_misc, tot_k_exp, tot_k_net = 0.0, 0.0, 0.0, 0.0, 0.0, 0.0

for i in range(30):
    d = start_dt + timedelta(days=i)
    d_str = d.strftime('%Y-%m-%d')
    dow = d.strftime('%a')
    
    ord_info = kkc_orders_map.get(d_str, {'bills': 0, 'pcs': 0, 'sales': 0.0, 'cogs': 0.0})
    bills = ord_info['bills']
    pcs = ord_info['pcs'] or 0
    sales = ord_info['sales'] or 0.0
    cogs = ord_info['cogs'] or 0.0
    gp = sales - cogs
    
    rent = round(27214.0 / 30, 2)  # 907.13 THB/day for Sep
    labor = 500.0 if d.weekday() in [4, 5, 6] else 460.0
    ads = kkc_ads_map.get(d_str, 0.0)
    misc = bills * 6.0
    exp = rent + labor + ads + misc
    net = gp - exp
    margin = (net / sales * 100) if sales > 0 else 0.0
    
    tot_k_bills += bills
    tot_k_pcs += pcs
    tot_k_sales += sales
    tot_k_cogs += cogs
    tot_k_gp += gp
    tot_k_rent += rent
    tot_k_labor += labor
    tot_k_ads += ads
    tot_k_misc += misc
    tot_k_exp += exp
    tot_k_net += net
    
    print(f"| {d_str} ({dow}) | {bills:2d} | {pcs:2d} | ฿{sales:>8,.2f} | ฿{cogs:>8,.2f} | ฿{gp:>8,.2f} | ฿{rent:>6,.2f} | ฿{labor:>6,.2f} | ฿{ads:>6,.2f} | ฿{misc:>5,.2f} | ฿{exp:>7,.2f} | ฿{net:>8,.2f} | {margin:>5.1f}% |")

print("| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |")
tot_k_margin = (tot_k_net / tot_k_sales * 100) if tot_k_sales > 0 else 0.0
print(f"| **รวมทั้งเดือน KKC** | **{tot_k_bills}** | **{tot_k_pcs}** | **฿{tot_k_sales:,.2f}** | **฿{tot_k_cogs:,.2f}** | **฿{tot_k_gp:,.2f}** | **฿{tot_k_rent:,.2f}** | **฿{tot_k_labor:,.2f}** | **฿{tot_k_ads:,.2f}** | **฿{tot_k_misc:,.2f}** | **฿{tot_k_exp:,.2f}** | **฿{tot_k_net:,.2f}** | **{tot_k_margin:.1f}%** |")

print("\n" + "="*80)
print("TABLE 2: ออนไลน์ (ONLINE) - DAILY P&L STATEMENT (ก.ย. 2569)")
print("="*80)
print("| วันที่ | บิล | ชิ้น | ยอดขาย (฿) | ต้นทุน (฿) | กำไรขั้นต้น (฿) | ค่าแรง (฿) | ค่าคอม (฿) | ค่าแอด (฿) | ค่าแพ็ค (฿) | ค่า COD (฿) | รวมค่าใช้จ่าย (฿) | กำไรสุทธิ (฿) | Margin% |")
print("| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |")

cur.execute("""
SELECT order_date, COUNT(*) as bills, SUM(total_pieces) as pcs, SUM(total_sales) as sales,
       SUM(cogs_total) as cogs, SUM(cod_amount) as cod
FROM orders
WHERE source_channel = 'online' AND order_date >= '2026-09-01' AND order_date <= '2026-09-30'
GROUP BY order_date
""")
on_orders_map = {r['order_date']: r for r in cur.fetchall()}

cur.execute("SELECT date, online_spend FROM daily_fb_ads WHERE date >= '2026-09-01' AND date <= '2026-09-30'")
on_ads_map = {r['date']: (r['online_spend'] or 0.0) for r in cur.fetchall()}

tot_o_bills, tot_o_pcs, tot_o_sales, tot_o_cogs, tot_o_gp = 0, 0, 0.0, 0.0, 0.0
tot_o_labor, tot_o_comm, tot_o_ads, tot_o_misc, tot_o_cod_fee, tot_o_exp, tot_o_net = 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0

for i in range(30):
    d = start_dt + timedelta(days=i)
    d_str = d.strftime('%Y-%m-%d')
    dow = d.strftime('%a')
    
    ord_info = on_orders_map.get(d_str, {'bills': 0, 'pcs': 0, 'sales': 0.0, 'cogs': 0.0, 'cod': 0.0})
    bills = ord_info['bills']
    pcs = ord_info['pcs'] or 0
    sales = ord_info['sales'] or 0.0
    cogs = ord_info['cogs'] or 0.0
    cod = ord_info['cod'] or 0.0
    gp = sales - cogs
    
    labor = 1132.0
    comm = pcs * 10.0
    ads = on_ads_map.get(d_str, 0.0)
    misc = bills * 3.0
    cod_fee = cod * 0.0214
    exp = labor + comm + ads + misc + cod_fee
    net = gp - exp
    margin = (net / sales * 100) if sales > 0 else 0.0
    
    tot_o_bills += bills
    tot_o_pcs += pcs
    tot_o_sales += sales
    tot_o_cogs += cogs
    tot_o_gp += gp
    tot_o_labor += labor
    tot_o_comm += comm
    tot_o_ads += ads
    tot_o_misc += misc
    tot_o_cod_fee += cod_fee
    tot_o_exp += exp
    tot_o_net += net
    
    print(f"| {d_str} ({dow}) | {bills:2d} | {pcs:2d} | ฿{sales:>8,.2f} | ฿{cogs:>8,.2f} | ฿{gp:>8,.2f} | ฿{labor:>6,.2f} | ฿{comm:>5,.2f} | ฿{ads:>8,.2f} | ฿{misc:>5,.2f} | ฿{cod_fee:>6,.2f} | ฿{exp:>9,.2f} | ฿{net:>8,.2f} | {margin:>5.1f}% |")

print("| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |")
tot_o_margin = (tot_o_net / tot_o_sales * 100) if tot_o_sales > 0 else 0.0
print(f"| **รวมทั้งเดือน Online** | **{tot_o_bills}** | **{tot_o_pcs}** | **฿{tot_o_sales:,.2f}** | **฿{tot_o_cogs:,.2f}** | **฿{tot_o_gp:,.2f}** | **฿{tot_o_labor:,.2f}** | **฿{tot_o_comm:,.2f}** | **฿{tot_o_ads:,.2f}** | **฿{tot_o_misc:,.2f}** | **฿{tot_o_cod_fee:,.2f}** | **฿{tot_o_exp:,.2f}** | **฿{tot_o_net:,.2f}** | **{tot_o_margin:.1f}%** |")

conn.close()
