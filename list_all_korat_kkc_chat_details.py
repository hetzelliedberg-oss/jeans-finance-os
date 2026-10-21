import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

with open('classified_chats_20_21.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

korat = data['korat']
kkc = data['kkc']

print("==================================================================")
print("             รายละเอียดแชท โคราช ทั้งหมด (43 แชท)                 ")
print("==================================================================")

for idx, c in enumerate(korat, 1):
    cname = c['customer_name']
    ret = "ลูกค้าเก่า(เคยทัก)" if c['is_returning_chatter'] else "แชทใหม่(ไม่เคยทัก)"
    buyer = "เคยซื้อ" if c['is_buyer'] else "ไม่เคยซื้อ"
    dates = []
    if c['has_msg_20']: dates.append('20 ต.ค.')
    if c['has_msg_21']: dates.append('21 ต.ค.')
    date_str = ", ".join(dates)
    
    # Extract customer messages on 20-21 Oct
    cust_msgs = [txt for _, _, sender, txt in c['messages_20_21'] if sender == 'Customer' and txt]
    admin_msgs = [txt for _, _, sender, txt in c['messages_20_21'] if sender == 'Admin' and txt]
    
    first_cust_msg = cust_msgs[0] if cust_msgs else (c['messages_20_21'][0][3] if c['messages_20_21'] else '')
    all_cust_summary = " // ".join(cust_msgs)[:150]
    
    print(f"\n#{idx:02d} | ลูกค้า: {cname} | วันที่คุย: {date_str} | สถานะ: [{ret} | {buyer}]")
    print(f"     ข้อความลูกค้า: {all_cust_summary if all_cust_summary else first_cust_msg[:120]}")

print("\n==================================================================")
print("             รายละเอียดแชท ขอนแก่น ทั้งหมด (11 แชท)               ")
print("==================================================================")

for idx, c in enumerate(kkc, 1):
    cname = c['customer_name']
    ret = "ลูกค้าเก่า(เคยทัก)" if c['is_returning_chatter'] else "แชทใหม่(ไม่เคยทัก)"
    buyer = "เคยซื้อ" if c['is_buyer'] else "ไม่เคยซื้อ"
    dates = []
    if c['has_msg_20']: dates.append('20 ต.ค.')
    if c['has_msg_21']: dates.append('21 ต.ค.')
    date_str = ", ".join(dates)
    
    cust_msgs = [txt for _, _, sender, txt in c['messages_20_21'] if sender == 'Customer' and txt]
    all_cust_summary = " // ".join(cust_msgs)[:150]
    
    print(f"\n#{idx:02d} | ลูกค้า: {cname} | วันที่คุย: {date_str} | สถานะ: [{ret} | {buyer}]")
    print(f"     ข้อความลูกค้า: {all_cust_summary if all_cust_summary else c['full_text_sample'][:120]}")
