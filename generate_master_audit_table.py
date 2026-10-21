import sqlite3
import datetime
import sys

sys.stdout.reconfigure(encoding='utf-8')
conn = sqlite3.connect('C:/Users/PAWIN/.gemini/antigravity/scratch/jeans-around-finance-os/data/finance_hub.db')
c = conn.cursor()

# Get settings
c.execute("SELECT key, value FROM settings")
settings = {r[0]: float(r[1]) if r[1].replace('.', '', 1).isdigit() else r[1] for r in c.fetchall()}

# Get ads
c.execute("SELECT date, online_spend, kkc_spend, total_spend FROM daily_fb_ads WHERE date >= '2026-10-01' AND date <= '2026-10-20'")
ads_map = {r[0]: {'online': float(r[1]), 'kkc': float(r[2]), 'total': float(r[3])} for r in c.fetchall()}

# Get orders grouped by date and channel
c.execute("""
    SELECT 
        order_date,
        source_channel,
        COUNT(*),
        SUM(total_pieces),
        SUM(total_sales),
        SUM(cogs_total),
        SUM(CASE WHEN payment_method = 'cod' THEN total_sales ELSE 0 END)
    FROM orders
    WHERE order_date >= '2026-10-01' AND order_date <= '2026-10-20'
    GROUP BY order_date, source_channel
""")
order_stats = {}
for r in c.fetchall():
    d, ch, cnt, pcs, sales, cogs, cod = r
    if d not in order_stats:
        order_stats[d] = {}
    order_stats[d][ch] = {
        'orders': cnt,
        'pieces': pcs or 0,
        'sales': sales or 0.0,
        'cogs': cogs or 0.0,
        'cod': cod or 0.0
    }

dates = [f"2026-10-{i:02d}" for i in range(1, 21)]

daily_records = []

total_online_rev = 0.0
total_online_exp = 0.0
total_online_net = 0.0

total_kkc_rev = 0.0
total_kkc_exp = 0.0
total_kkc_net = 0.0

total_combined_rev = 0.0
total_combined_exp = 0.0
total_combined_net = 0.0

for d in dates:
    dt = datetime.date.fromisoformat(d)
    dow = dt.strftime('%a') # Mon, Tue, etc.
    is_weekend = dow in ['Sat', 'Sun']
    
    # Online
    onl = order_stats.get(d, {}).get('online', {'orders': 0, 'pieces': 0, 'sales': 0.0, 'cogs': 0.0, 'cod': 0.0})
    onl_ads = ads_map.get(d, {}).get('online', 0.0)
    onl_labor = settings.get('ONLINE_LABOR_DAILY', 1132.0)
    onl_comm = onl['pieces'] * settings.get('ONLINE_COMMISSION_PER_PIECE', 10.0)
    onl_cod_fee = onl['cod'] * (settings.get('ONLINE_COD_FEE_PCT', 2.14) / 100.0)
    onl_misc = onl['orders'] * settings.get('ONLINE_MISC_PER_ORDER', 3.0)
    onl_exp = onl['cogs'] + onl_ads + onl_labor + onl_comm + onl_cod_fee + onl_misc
    onl_net = onl['sales'] - onl_exp
    
    # KKC
    kkc = order_stats.get(d, {}).get('kkc', {'orders': 0, 'pieces': 0, 'sales': 0.0, 'cogs': 0.0, 'cod': 0.0})
    kkc_ads = ads_map.get(d, {}).get('kkc', 0.0)
    kkc_rent = settings.get('KKC_RENT_DAILY', 877.87)
    kkc_labor = settings.get('KKC_LABOR_WEEKEND', 500.0) if is_weekend else settings.get('KKC_LABOR_WEEKDAY', 460.0)
    kkc_misc = kkc['orders'] * settings.get('KKC_MISC_PER_ORDER', 6.0)
    kkc_exp = kkc['cogs'] + kkc_ads + kkc_rent + kkc_labor + kkc_misc
    kkc_net = kkc['sales'] - kkc_exp
    
    # Combined
    comb_rev = onl['sales'] + kkc['sales']
    comb_exp = onl_exp + kkc_exp
    comb_net = comb_rev - comb_exp
    comb_margin = (comb_net / comb_rev * 100.0) if comb_rev > 0 else 0.0
    
    total_online_rev += onl['sales']
    total_online_exp += onl_exp
    total_online_net += onl_net
    
    total_kkc_rev += kkc['sales']
    total_kkc_exp += kkc_exp
    total_kkc_net += kkc_net
    
    total_combined_rev += comb_rev
    total_combined_exp += comb_exp
    total_combined_net += comb_net
    
    # Notes about late order / lagged logic
    note = ""
    if d == '2026-10-04':
        note = "Reconciled 4 online orders from Oct 5 morning post"
    elif d == '2026-10-11':
        note = "Reconciled 26 online orders from Oct 12 morning post"
    elif d == '2026-10-13':
        note = "Reconciled spillover orders from Oct 14 post"
    elif d == '2026-10-18':
        note = "Reconciled 7 online orders from Oct 19 morning post"
    elif d == '2026-10-19':
        note = "Reconciled Order #6 from Oct 20 morning post"
    elif d == '2026-10-20':
        note = "Audited up to 23:16 PM (24 orders closed)"
        
    daily_records.append({
        'date': d,
        'dow': dow,
        'onl_orders': onl['orders'],
        'onl_pieces': onl['pieces'],
        'onl_rev': onl['sales'],
        'onl_cogs': onl['cogs'],
        'onl_ads': onl_ads,
        'onl_exp': onl_exp,
        'onl_net': onl_net,
        'kkc_orders': kkc['orders'],
        'kkc_pieces': kkc['pieces'],
        'kkc_rev': kkc['sales'],
        'kkc_cogs': kkc['cogs'],
        'kkc_ads': kkc_ads,
        'kkc_exp': kkc_exp,
        'kkc_net': kkc_net,
        'comb_rev': comb_rev,
        'comb_exp': comb_exp,
        'comb_net': comb_net,
        'comb_margin': comb_margin,
        'note': note
    })

print("| วันที่ | วัน | Online ยอดขาย | Online กำไรสุทธิ | KKC ยอดขาย | KKC กำไรสุทธิ | รวม ยอดขาย | รวม กำไรสุทธิ | Margin % | Audit Status / Late Reconciled |")
print("|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---|")
for r in daily_records:
    print(f"| {r['date']} | {r['dow']} | ฿{r['onl_rev']:,.0f} ({r['onl_orders']} ออเดอร์) | ฿{r['onl_net']:,.0f} | ฿{r['kkc_rev']:,.0f} ({r['kkc_orders']} ออเดอร์) | ฿{r['kkc_net']:,.0f} | ฿{r['comb_rev']:,.0f} | ฿{r['comb_net']:,.0f} | {r['comb_margin']:.1f}% | {r['note']} |")

print(f"\n=== MTD SUMMARY (1-20 OCT 2026) ===")
print(f"Total Combined Revenue: ฿{total_combined_rev:,.2f}")
print(f"Total Combined Expenses: ฿{total_combined_exp:,.2f}")
print(f"Total Combined Net Profit: ฿{total_combined_net:,.2f} ({total_combined_net/total_combined_rev*100:.2f}%)")
print(f"Online Net: ฿{total_online_net:,.2f} on ฿{total_online_rev:,.2f} ({total_online_net/total_online_rev*100:.2f}%)")
print(f"KKC Net: ฿{total_kkc_net:,.2f} on ฿{total_kkc_rev:,.2f} ({total_kkc_net/total_kkc_rev*100:.2f}%)")

conn.close()
