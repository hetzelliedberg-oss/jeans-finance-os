import sqlite3
import re
import sys
from collections import Counter

sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('C:/Users/PAWIN/.gemini/antigravity/scratch/jeans-around-finance-os/data/finance_hub.db')
c = conn.cursor()
c.execute("SELECT raw_text FROM orders WHERE raw_text IS NOT NULL")
rows = c.fetchall()

provinces = {
    'กทมและปริมณฑล': ['กรุงเทพ', 'กทม', 'นนทบุรี', 'ปทุมธานี', 'สมุทรปราการ', 'สมุทรสาคร'],
    'ชลบุรี-ระยอง': ['ชลบุรี', 'ระยอง', 'พัทยา'],
    'ขอนแก่น': ['ขอนแก่น'],
    'นครราชสีมา': ['นครราชสีมา', 'โคราช'],
    'อุดรธานี': ['อุดรธานี', 'อุดร'],
    'อุบลราชธานี': ['อุบลราชธานี', 'อุบล'],
    'เชียงใหม่': ['เชียงใหม่'],
    'สงขลา-หาดใหญ่': ['สงขลา', 'หาดใหญ่'],
    'สุราษฎร์ธานี': ['สุราษฎร์'],
    'นครศรีธรรมราช': ['นครศรีธรรมราช'],
    'เชียงราย': ['เชียงราย'],
    'พิษณุโลก': ['พิษณุโลก'],
    'สกลนคร': ['สกลนคร'],
    'ร้อยเอ็ด': ['ร้อยเอ็ด'],
    'บุรีรัมย์': ['บุรีรัมย์'],
    'ภูเก็ต': ['ภูเก็ต']
}

counts = Counter()
for r in rows:
    txt = r[0]
    matched = False
    for prov_group, keywords in provinces.items():
        if any(k in txt for k in keywords):
            counts[prov_group] += 1
            matched = True
            break

print(f"Total analyzed orders with text: {len(rows)}")
print("\nTop Historical Order Locations (Data Fact):")
for p, cnt in counts.most_common(16):
    print(f"- {p:<18}: {cnt:>5} orders ({cnt/len(rows)*100:>5.1f}%)")
