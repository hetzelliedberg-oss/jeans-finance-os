import json
import sys
from datetime import datetime, timezone, timedelta

sys.stdout.reconfigure(encoding='utf-8')

with open('all_folders_oct21.json', 'r', encoding='utf-8') as f:
    convs = json.load(f)

print(f"Total unique conversations loaded: {len(convs)}")

tz_thai = timezone(timedelta(hours=7))
page_id = '359833590537243'

all_21_records = []

for c in convs:
    cid = c['id']
    msgs = c.get('messages', {}).get('data', [])
    if not msgs:
        continue
        
    chrono = list(reversed(msgs))
    first_time = datetime.fromisoformat(chrono[0]['created_time'].replace('+0000', '+00:00')).astimezone(tz_thai)
    
    cust_name = "Unknown"
    cust_id = None
    for p in c.get('participants', {}).get('data', []):
        if p.get('id') != page_id:
            cust_name = p.get('name')
            cust_id = p.get('id')
            
    msgs_21 = []
    cust_msgs_21 = []
    admin_msgs_21 = []
    
    for m in chrono:
        m_dt = datetime.fromisoformat(m['created_time'].replace('+0000', '+00:00')).astimezone(tz_thai)
        if m_dt.strftime('%Y-%m-%d') == '2026-10-21':
            sender = "Customer" if m.get('from', {}).get('id') != page_id else "Admin"
            txt = m.get('message', '')
            msgs_21.append((m_dt, sender, txt))
            if sender == 'Customer' and txt:
                cust_msgs_21.append(txt)
            elif sender == 'Admin' and txt:
                admin_msgs_21.append(txt)
                
    if msgs_21:
        # Check topic
        full_text = " ".join(cust_msgs_21 + admin_msgs_21).lower()
        topic = "ONLINE"
        if any(k in full_text for k in ['โคราช', 'เซ็นทรัลโคราช', 'central korat', 'showcase']):
            topic = "KORAT"
        elif any(k in full_text for k in ['ขอนแก่น', 'เซ็นทรัลขอนแก่น', 'central ขอนแก่น']):
            topic = "KKC"
            
        is_new_chat = first_time >= datetime(2026, 10, 21, 0, 0, 0, tzinfo=tz_thai)
        
        all_21_records.append({
            'conv_id': cid,
            'name': cust_name,
            'topic': topic,
            'is_new_chat': is_new_chat,
            'cust_msgs': cust_msgs_21,
            'admin_msgs': admin_msgs_21,
            'total_msgs': len(msgs_21),
            'first_time': first_time.strftime('%Y-%m-%d %H:%M:%S'),
            'last_msg_time': msgs_21[-1][0].strftime('%H:%M:%S')
        })

print(f"\n==================================================================")
print(f"🔥 FINAL VERIFIED AUDIT FOR 21 OCT 2026 (ALL FOLDERS INCLUDED)")
print(f"==================================================================")
print(f"Total Active Conversations on 21 Oct: {len(all_21_records)} แชท")
print(f"- แชทที่มีลูกค้าพิมพ์ข้อความจริง: {len([r for r in all_21_records if r['cust_msgs']])} แชท")
print(f"- แชทที่มีเฉพาะแอดมินทักตาม/บรอดแคสต์: {len([r for r in all_21_records if not r['cust_msgs']])} แชท")
print(f"- แชทใหม่เอี่ยม (ทักครั้งแรกในชีวิตวันที่ 21 ต.ค.): {len([r for r in all_21_records if r['is_new_chat']])} แชท")
print(f"- แชทเก่าคุยซ้ำ (Returning Customers): {len([r for r in all_21_records if not r['is_new_chat']])} แชท")

korat_list = [r for r in all_21_records if r['topic'] == 'KORAT']
kkc_list = [r for r in all_21_records if r['topic'] == 'KKC']
online_list = [r for r in all_21_records if r['topic'] == 'ONLINE']

print(f"\nแยกตามช่องทาง/หัวข้อการคุย:")
print(f"1. โคราช (Korat): {len(korat_list)} แชท")
print(f"2. ขอนแก่น (KKC): {len(kkc_list)} แชท")
print(f"3. ออนไลน์ทั่วไป (Online): {len(online_list)} แชท")

with open('verified_oct21_all_chats.json', 'w', encoding='utf-8') as f:
    json.dump(all_21_records, f, ensure_ascii=False, indent=2)

print("\nSaved verified records to verified_oct21_all_chats.json")
