import sqlite3, sys
from datetime import datetime, date

sys.stdout.reconfigure(encoding='utf-8')
conn = sqlite3.connect('data/finance_hub.db')
c = conn.cursor()

# Get settings
c.execute("SELECT key, value FROM settings")
settings = {r[0]: float(r[1]) for r in c.fetchall() if r[0] in ['KKC_RENT_DAILY', 'KKC_LABOR_WEEKDAY', 'KKC_LABOR_WEEKEND', 'KKC_MISC_PER_ORDER']}

rent_daily = settings.get('KKC_RENT_DAILY', 910.0)
labor_weekday = settings.get('KKC_LABOR_WEEKDAY', 460.0)
labor_weekend = settings.get('KKC_LABOR_WEEKEND', 500.0)
misc_per_order = settings.get('KKC_MISC_PER_ORDER', 6.0)

# Check daily ads for KKC if any
c.execute("SELECT date, kkc_spend FROM daily_fb_ads")
daily_ads = {r[0]: float(r[1]) for r in c.fetchall()}

# Orders by day
c.execute("""
    SELECT substr(order_date, 1, 10) as d,
           count(*) as bills,
           sum(total_pieces) as pieces,
           sum(total_sales) as sales,
           sum(cogs_total) as cogs
    FROM orders
    WHERE source_channel IN ('kkc', 'storefront_kkc') AND (order_date LIKE '2026-08%' OR order_date LIKE '2026-09%' OR order_date LIKE '2026-10%')
    GROUP BY d
    ORDER BY d
""")
orders_by_day = {r[0]: {"bills": r[1], "pcs": r[2], "sales": r[3], "cogs": r[4]} for r in c.fetchall()}
conn.close()

import calendar

for month_num, month_name in [(8, "สิงหาคม 2026"), (9, "กันยายน 2026"), (10, "ตุลาคม 2026")]:
    days_in_month = calendar.monthrange(2026, month_num)[1]
    rent_daily = round(27214.0 / days_in_month, 2)
    print(f"\n=========================================================================================================================")
    print(f"  งบกำไรขาดทุน FACT รายวัน หน้าร้านสาขาขอนแก่น (KKC P&L) - {month_name}")
    print(f"  [ค่าเช่า: {rent_daily:.2f} บ./วัน (27,214/{days_in_month}) | ค่าคน: {labor_weekday:.0f} บ.(จ-พฤ), {labor_weekend:.0f} บ.(ศ-อา) | เบ็ดเตล็ด: {misc_per_order:.0f} บ./บิล]")
    print(f"=========================================================================================================================")
    
    tot_sales = tot_cogs = tot_gp = tot_rent = tot_labor = tot_misc = tot_ads = tot_exp = tot_np = 0
    tot_bills = tot_pcs = 0
    days_profit = 0
    days_loss = 0
    
    print(f"{'วันที่':10s} | {'วัน':3s} | {'บิล':3s} | {'ตัว':3s} | {'ยอดขาย':8s} | {'ต้นทุนสินค้า':10s} | {'กำไรขั้นต้น':10s} | {'ค่าเช่า':7s} | {'ค่าคน':6s} | {'เบ็ดเตล็ด':8s} | {'รวมคชจ.':8s} | {'กำไรสุทธิ':10s} | {'%Net':6s}")
    print("-" * 121)
    
    weekday_thai = ["จ.", "อ.", "พ.", "พฤ.", "ศ.", "ส.", "อา."]
    
    for day in range(1, days_in_month + 1):
        d_str = f"2026-{month_num:02d}-{day:02d}"
        dt_obj = date(2026, month_num, day)
        wd_idx = dt_obj.weekday()
        wd_name = weekday_thai[wd_idx]
        
        o = orders_by_day.get(d_str, {"bills": 0, "pcs": 0, "sales": 0.0, "cogs": 0.0})
        sales = o["sales"]
        cogs = o["cogs"]
        gp = sales - cogs
        
        rent = rent_daily
        labor = labor_weekend if wd_idx in [4, 5, 6] else labor_weekday
        misc = o["bills"] * misc_per_order
        ads = daily_ads.get(d_str, 0.0)
        exp = rent + labor + misc + ads
        np = gp - exp
        np_pct = (np / sales * 100) if sales > 0 else 0.0
        
        tot_bills += o["bills"]
        tot_pcs += o["pcs"]
        tot_sales += sales
        tot_cogs += cogs
        tot_gp += gp
        tot_rent += rent
        tot_labor += labor
        tot_misc += misc
        tot_ads += ads
        tot_exp += exp
        tot_np += np
        
        if np >= 0:
            days_profit += 1
            status_str = f"{np:9.2f}"
        else:
            days_loss += 1
            status_str = f"{np:9.2f} (ขาดทุน)"
            
        print(f"{d_str} | {wd_name:3s} | {o['bills']:3d} | {o['pcs']:3d} | {sales:8.2f} | {cogs:10.2f} | {gp:10.2f} | {rent:7.2f} | {labor:6.2f} | {misc:8.2f} | {exp:8.2f} | {status_str:10s} | {np_pct:5.1f}%")
        
    print("-" * 121)
    tot_np_pct = (tot_np / tot_sales * 100) if tot_sales > 0 else 0.0
    print(f"รวม {month_name}: {tot_bills} บิล | {tot_pcs} ตัว")
    print(f"  - ยอดขายรวม (Gross Sales):        {tot_sales:12,.2f} บาท (เฉลี่ยวันละ {tot_sales/days_in_month:,.2f} บ.)")
    print(f"  - ต้นทุนสินค้าจริง (COGS):         {tot_cogs:12,.2f} บาท ({tot_cogs/tot_sales*100:.1f}% ของยอดขาย)")
    print(f"  - กำไรขั้นต้นรวม (Gross Profit):    {tot_gp:12,.2f} บาท ({tot_gp/tot_sales*100:.1f}%)")
    print(f"  - รวมค่าเช่า ({days_in_month} วัน):           {tot_rent:12,.2f} บาท")
    print(f"  - รวมค่าพนักงาน ({days_in_month} วัน):        {tot_labor:12,.2f} บาท")
    print(f"  - รวมเบ็ดเตล็ด/ถุง:                {tot_misc:12,.2f} บาท")
    print(f"  - รวมค่าใช้จ่ายทั้งหมด (OpEx):      {tot_exp:12,.2f} บาท (เฉลี่ยวันละ {tot_exp/days_in_month:,.2f} บ.)")
    print(f"  -------------------------------------------------------------")
    print(f"  >>> กำไรสุทธิเข้ากระเป๋า (Net Profit): {tot_np:12,.2f} บาท (อัตรากำไรสุทธิ {tot_np_pct:.1f}%)")
    print(f"  >>> สถิติรายวัน: กำไร {days_profit} วัน | ขาดทุน {days_loss} วัน (จาก {days_in_month} วัน)")
