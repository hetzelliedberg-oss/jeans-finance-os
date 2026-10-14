import sqlite3
import json
import sys
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('data/finance_hub.db')
c = conn.cursor()

# Get ads
daily_ads = {}
for r in c.execute("SELECT date, online_spend, kkc_spend, total_spend FROM daily_fb_ads WHERE date >= '2026-10-01' AND date <= '2026-10-14'").fetchall():
    daily_ads[r[0]] = {'online': float(r[1] or 0), 'kkc': float(r[2] or 0), 'total': float(r[3] or 0)}

# Constants
ONLINE_LABOR_DAILY = 1132.0
ONLINE_COMM_RATE = 10.0
ONLINE_BOX_RATE = 3.0
ONLINE_COD_PCT = 0.0214

KKC_RENT_DAILY = round(27214.0 / 31, 2) # 877.87
KKC_LABOR_WEEKDAY = 460.0
KKC_LABOR_WEEKEND = 500.0
KKC_BAG_RATE = 6.0

def get_kkc_labor(dt_str):
    dt = datetime.strptime(dt_str, '%Y-%m-%d')
    if dt.weekday() in [4, 5, 6]: # Fri, Sat, Sun
        return KKC_LABOR_WEEKEND
    return KKC_LABOR_WEEKDAY

dates = [f"2026-10-{d:02d}" for d in range(1, 15)]
master_table = []

for dt in dates:
    # 1. Online
    c.execute("""
        SELECT count(*), sum(total_pieces), sum(total_sales), sum(cogs_total), sum(cod_amount)
        FROM orders
        WHERE order_date = ? AND source_channel = 'online' AND status != 'cancelled'
    """, (dt,))
    on_row = c.fetchone()
    on_cnt = on_row[0] or 0
    on_pcs = on_row[1] or 0
    on_sales = on_row[2] or 0.0
    on_cogs = on_row[3] or 0.0
    on_cod = on_row[4] or 0.0
    on_gp = on_sales - on_cogs
    on_labor = ONLINE_LABOR_DAILY if on_cnt > 0 else 0.0
    on_comm = on_pcs * ONLINE_COMM_RATE
    on_misc = on_cnt * ONLINE_BOX_RATE
    on_cod_fee = on_cod * ONLINE_COD_PCT
    on_ads = daily_ads.get(dt, {}).get('online', 0.0)
    on_exp = on_labor + on_comm + on_misc + on_cod_fee + on_ads
    on_net = on_gp - on_exp
    
    # 2. KKC
    c.execute("""
        SELECT count(*), sum(total_pieces), sum(total_sales), sum(cogs_total)
        FROM orders
        WHERE order_date = ? AND source_channel = 'kkc' AND status != 'cancelled'
    """, (dt,))
    kk_row = c.fetchone()
    kk_cnt = kk_row[0] or 0
    kk_pcs = kk_row[1] or 0
    kk_sales = kk_row[2] or 0.0
    kk_cogs = kk_row[3] or 0.0
    kk_gp = kk_sales - kk_cogs
    kk_rent = KKC_RENT_DAILY
    kk_labor = get_kkc_labor(dt) if (kk_cnt > 0 or dt != '2026-10-09') else 0.0
    kk_misc = kk_cnt * KKC_BAG_RATE
    kk_ads = daily_ads.get(dt, {}).get('kkc', 0.0)
    kk_exp = kk_rent + kk_labor + kk_misc + kk_ads
    kk_net = kk_gp - kk_exp
    
    # Totals
    tot_sales = on_sales + kk_sales
    tot_cogs = on_cogs + kk_cogs
    tot_gp = on_gp + kk_gp
    tot_exp = on_exp + kk_exp
    tot_net = on_net + kk_net
    
    master_table.append({
        'date': dt,
        'on_cnt': on_cnt, 'on_pcs': on_pcs, 'on_sales': on_sales, 'on_cogs': on_cogs, 'on_gp': on_gp, 'on_ads': on_ads, 'on_exp': on_exp, 'on_net': on_net,
        'kk_cnt': kk_cnt, 'kk_pcs': kk_pcs, 'kk_sales': kk_sales, 'kk_cogs': kk_cogs, 'kk_gp': kk_gp, 'kk_ads': kk_ads, 'kk_exp': kk_exp, 'kk_net': kk_net,
        'tot_sales': tot_sales, 'tot_cogs': tot_cogs, 'tot_gp': tot_gp, 'tot_exp': tot_exp, 'tot_net': tot_net
    })

conn.close()

with open('master_audit_oct_1_14.json', 'w', encoding='utf-8') as f:
    json.dump(master_table, f, ensure_ascii=False, indent=2)

print(f"{'Date':<11} | {'Channel':<7} | {'Bills':<5} | {'Pcs':<5} | {'Sales':>10} | {'COGS':>10} | {'GP':>10} | {'Ads':>9} | {'Net Profit':>12} | {'Margin':>6}")
print("-" * 95)
for r in master_table:
    d = r['date']
    # online
    on_m = (r['on_net'] / r['on_sales'] * 100) if r['on_sales'] > 0 else 0
    print(f"{d:<11} | {'Online':<7} | {r['on_cnt']:<5} | {r['on_pcs']:<5} | {r['on_sales']:>10,.2f} | {r['on_cogs']:>10,.2f} | {r['on_gp']:>10,.2f} | {r['on_ads']:>9,.2f} | {r['on_net']:>12,.2f} | {on_m:>5.1f}%")
    # kkc
    kk_m = (r['kk_net'] / r['kk_sales'] * 100) if r['kk_sales'] > 0 else 0
    print(f"{'':<11} | {'KKC':<7} | {r['kk_cnt']:<5} | {r['kk_pcs']:<5} | {r['kk_sales']:>10,.2f} | {r['kk_cogs']:>10,.2f} | {r['kk_gp']:>10,.2f} | {r['kk_ads']:>9,.2f} | {r['kk_net']:>12,.2f} | {kk_m:>5.1f}%")
    # total
    tot_m = (r['tot_net'] / r['tot_sales'] * 100) if r['tot_sales'] > 0 else 0
    print(f"{'':<11} | {'TOTAL':<7} | {r['on_cnt']+r['kk_cnt']:<5} | {r['on_pcs']+r['kk_pcs']:<5} | {r['tot_sales']:>10,.2f} | {r['tot_cogs']:>10,.2f} | {r['tot_gp']:>10,.2f} | {r['on_ads']+r['kk_ads']:>9,.2f} | {r['tot_net']:>12,.2f} | {tot_m:>5.1f}%")
    print("-" * 95)
