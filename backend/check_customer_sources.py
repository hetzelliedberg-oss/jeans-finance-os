import sqlite3, re, sys
sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('data/finance_hub.db')
c = conn.cursor()

c.execute("SELECT substr(order_date, 1, 7) as mo, raw_text FROM orders WHERE source_channel = 'kkc'")

stats = {}
for mo, text in c.fetchall():
    if mo not in stats:
        stats[mo] = {'fb': 0, 'walkin': 0, 'tiktok': 0, 'other': 0, 'total': 0}
    stats[mo]['total'] += 1
    t = text or ''
    m = re.search(r'ลูกค้า\s*[:=]?\s*([^\n]+)', t)
    source = m.group(1).strip() if m else ''
    if 'เพจ' in source or 'fb' in source.lower() or 'facebook' in source.lower():
        stats[mo]['fb'] += 1
    elif 'เดิน' in source or 'หน้าร้าน' in source or 'walk' in source.lower():
        stats[mo]['walkin'] = stats[mo].get('walkin', 0) + 1
    elif 'tiktok' in source.lower():
        stats[mo]['tiktok'] += 1
    else:
        stats[mo]['other'] += 1

print("=== STOREFRONT CUSTOMER SOURCE BREAKDOWN (KKC) ===")
for mo, d in stats.items():
    print(f"Month {mo}: Total {d['total']} orders")
    print(f"  - มาจากเพจ FB / ตามแอด: {d['fb']} ({d['fb']/d['total']*100:.1f}%)")
    print(f"  - เดินเข้าหน้าร้าน (Walk-in): {d['walkin']} ({d['walkin']/d['total']*100:.1f}%)")
    print(f"  - TikTok: {d['tiktok']} ({d['tiktok']/d['total']*100:.1f}%)")
    print(f"  - อื่นๆ/ไม่ระบุ: {d['other']} ({d['other']/d['total']*100:.1f}%)")

conn.close()
