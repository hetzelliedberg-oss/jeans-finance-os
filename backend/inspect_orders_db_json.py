import json
import os
import sys
from collections import Counter

sys.stdout.reconfigure(encoding='utf-8')

fb_file = "C:/Users/PAWIN/.gemini/antigravity/scratch/fb-sales-ai-engine/orders_database.json"
if not os.path.exists(fb_file):
    print("Not found")
    sys.exit()

with open(fb_file, 'r', encoding='utf-8') as f:
    data = json.load(f)

print(f"Total orders in orders_database.json: {len(data)}")

dates = Counter()
channels = Counter()
total_rev = 0.0

for o in data:
    dt = str(o.get("created_at", ""))[:7]
    dates[dt] += 1
    total_rev += float(o.get("total_amount", 0) or 0)

print("\nBy month in orders_database.json:")
for d, count in sorted(dates.items()):
    print(f"  {d}: {count} orders")

print(f"\nSample order:\n{json.dumps(data[0], ensure_ascii=False, indent=2)}")
