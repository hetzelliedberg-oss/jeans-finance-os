import requests
import json

url = 'https://jeans-finance-os.onrender.com/api/orders?start_date=2026-09-27&end_date=2026-09-28&limit=100'
r = requests.get(url, timeout=10)
print('Status:', r.status_code)
data = r.json()
print('Total on Render:', data.get('total'))
orders = data.get('orders', [])
for o in orders:
    oid = o['id']
    odate = o['order_date']
    och = o['source_channel']
    osales = o['total_sales']
    omsg = o['message_id']
    print(f"ID: {oid} | Date: {odate} | Channel: {och} | Sales: {osales} | Msg: {omsg}")
