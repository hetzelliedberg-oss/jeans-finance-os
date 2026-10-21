import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

with open('classified_chats_20_21.json', 'r', encoding='utf-8') as f:
    d = json.load(f)

korat = d['korat']
kkc = d['kkc']

print(f"Total Korat: {len(korat)}, Total KKC: {len(kkc)}")

for label, lst in [("โคราช", korat), ("ขอนแก่น", kkc)]:
    print(f"\n==================== {label} ====================")
    for i, c in enumerate(lst, 1):
        cname = c['customer_name']
        is_ret = "เคยทัก" if c['is_returning_chatter'] else "ทักใหม่"
        is_buy = "เคยซื้อ" if c['is_buyer'] else "ไม่เคยซื้อ"
        d20 = "20" if c['has_msg_20'] else ""
        d21 = "21" if c['has_msg_21'] else ""
        dates = "+".join(filter(None, [d20, d21])) + " ต.ค."
        
        # All messages
        cust_lines = []
        for dt, d_str, sender, txt in c['messages_20_21']:
            if sender == 'Customer' and txt:
                cust_lines.append(f"{txt.strip()}")
            elif sender == 'Admin' and 'คุณกำลังตอบกลับความคิดเห็น' in txt:
                cust_lines.append("[ดึงจากคอมเมนต์ Reel]")
                
        summary = " | ".join(cust_lines)[:120] if cust_lines else "(กดปุ่มเริ่มสนทนา / ส่งสติ๊กเกอร์)"
        print(f"{i:02d}. [{dates}] {cname:<25} | {is_ret} | {is_buy} | ข้อความ: {summary}")
