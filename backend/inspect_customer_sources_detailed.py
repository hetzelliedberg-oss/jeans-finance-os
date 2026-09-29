import sqlite3, re, sys
sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('data/finance_hub.db')
c = conn.cursor()

c.execute("SELECT substr(order_date, 1, 7) as mo, order_date, raw_text FROM orders WHERE source_channel = 'kkc' ORDER BY order_date")
rows = c.fetchall()

sources_by_month = {}
daily_breakdown = {}

for mo, d_str, text in rows:
    if mo not in sources_by_month:
        sources_by_month[mo] = {}
    if d_str not in daily_breakdown:
        daily_breakdown[d_str] = {}
        
    t = text or ''
    m = re.search(r'ลูกค้า\s*[:=]?\s*([^\n]+)', t)
    src = m.group(1).strip() if m else 'ไม่ระบุ'
    clean_src = src.replace('ลูกค้า :', '').strip()
    if not clean_src:
        clean_src = 'ไม่ระบุ'
        
    sources_by_month[mo][clean_src] = sources_by_month[mo].get(clean_src, 0) + 1
    daily_breakdown[d_str][clean_src] = daily_breakdown[d_str].get(clean_src, 0) + 1

for mo, d in sources_by_month.items():
    print(f"\n=======================================================")
    print(f"  สถิติที่มาของลูกค้าหน้าร้านขอนแก่น (KKC) - {mo}")
    print(f"=======================================================")
    total = sum(d.values())
    for k, v in sorted(d.items(), key=lambda x: x[1], reverse=True):
        print(f"  {k:35s}: {v:3d} บิล ({v/total*100:5.1f}%)")

# Check specifically for recent days (Sep 23 - Sep 27)
print(f"\n=======================================================")
print(f"  เจาะลึก 5 วันล่าสุด (23 - 27 ก.ย.) ลูกค้ามาจากไหน?")
print(f"=======================================================")
for d_str in sorted(daily_breakdown.keys()):
    if d_str >= '2026-09-23':
        print(f"วันที่ {d_str}: {daily_breakdown[d_str]}")

conn.close()
