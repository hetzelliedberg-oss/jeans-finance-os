"""Order Extractor, Telegram Billing Formatter & 3-Enter Confirmation."""

import os
import re
import time
import requests
from typing import Any, Dict, List

from db import get_latest_order_by_psid, save_order, update_order_by_id, upsert_customer_crm
from grill_engine import PHONE_RE
from meta_client import meta_client

SKU_RE = re.compile(r"\b(XRP\s*\d+|AR\s*\d+|JA\s*\d+)\b", re.IGNORECASE)
SIZE_RE = re.compile(r"\b(M|L|XL|2XL|3XL|4XL|5XL)\b", re.IGNORECASE)


def extract_order_from_chat(
    psid: str,
    customer_name: str,
    messages: List[Dict[str, Any]],
    branch: str = "ONLINE",
    ad_name: str = "",
) -> Dict[str, Any]:
    # Isolate the active order session AFTER the latest truly completed/dispatched bill so historical orders never bleed in
    # (keep "คุณร้องขอไป" / payment requests excluded here since Meta triggers them mid-checkout BEFORE billing finishes!)
    bill_markers = (
        "สรุปออเดอร์การสั่งซื้อ",
        "เปิดบิลแล้ว",
        "marked the order as dispatched",
        "ทำเครื่องหมายคำสั่งซื้อว่าจัดส่งแล้ว",
    )
    active_msgs = list(messages or [])
    last_bill_idx = -1
    for i, m in enumerate(active_msgs):
        if any(mk in (m.get("text") or "") for mk in bill_markers):
            last_bill_idx = i
    if last_bill_idx >= 0 and any(m.get("sender_role") == "customer" for m in active_msgs[last_bill_idx + 1 :]):
        active_msgs = active_msgs[last_bill_idx + 1 :]

    cust_msgs = [m for m in active_msgs if m.get("sender_role") == "customer"]
    cust_texts = [m.get("text", "") for m in cust_msgs if m.get("text")]
    all_texts = [m.get("text", "") for m in active_msgs if m.get("text")]
    last_cust = cust_texts[-1] if cust_texts else ""
    recent_cust_block = "\n".join(cust_texts[-5:])
    joined_all = "\n".join(all_texts)

    # Phone
    phone_match = PHONE_RE.search(recent_cust_block) or PHONE_RE.search("\n".join(cust_texts))
    phone = phone_match.group(0).replace(" ", "").replace("-", "") if phone_match else ""

    # Recipient name
    recipient_name = customer_name
    m_name = re.search(r"(?:ชื่อ|ผู้รับ)\s*[:：]?\s*([^\n0-9]{3,40})", recent_cust_block)
    if m_name:
        recipient_name = m_name.group(1).strip()

    # Address
    addr_lines = [t for t in cust_texts[-4:] if any(h in t for h in ["บ้านเลขที่", "หมู่", "ต.", "ตำบล", "อ.", "อำเภอ", "จ.", "จังหวัด", "แขวง", "เขต", "ซอย", "ถนน", "รหัสไปรษณีย์"])]
    address = " ".join(addr_lines).strip() if addr_lines else last_cust.strip()
    if phone_match:
        address = address.replace(phone_match.group(0), "").strip(" ,-\n")

    # Filter out bot/upsell/Meta-payment-request template noise so false amounts never overwrite real quotes
    non_template_msgs = [
        m.get("text", "") for m in active_msgs
        if m.get("text") and m.get("sender_role") != "bot"
        and not any(
            noise in (m.get("text") or "")
            for noise in (
                "โปรจับคู่", "โปรคู่ 2 ตัว", "หนูขออนุญาตส่งข้อมูลเพิ่มเติม",
                "ได้รับข้อมูลครบถ้วนแล้วนะคะพี่", "จากคลิป/แอดที่พี่ทักเข้ามา",
                "คุณร้องขอไป", "เก็บข้อมูลไว้ค่อยตัดสินใจ",
                "ขอบพระคุณ", "ได้รับชื่อ-ที่อยู่",
            )
        )
    ]
    cust_joined = "\n".join(cust_texts)
    non_template_joined = "\n".join(non_template_msgs)
    ad_intro = "\n".join(non_template_msgs[:3])

    # SKUs & Size
    skus = [re.sub(r"\s+", "", s).upper() for s in SKU_RE.findall(f"{cust_joined}\n{ad_intro}\n{ad_name}")]
    sizes = [s.upper() for s in SIZE_RE.findall(cust_joined)]
    if skus:
        sku_part = "/".join(dict.fromkeys(skus))
    elif "กระโปรง" in f"{cust_joined} {ad_intro}":
        sku_part = "กระโปรงปักฉลุ"
    elif "ขาสั้น" in f"{cust_joined} {ad_intro}":
        sku_part = "ขาสั้นปักฉลุ"
    else:
        sku_part = "ยีนส์ปักฉลุ"
    size_part = sizes[-1] if sizes else "รอระบุไซส์"
    items = f"{sku_part}/{size_part}"

    # Payment method & amount (grounded ONLY in active-session customer text & non-template admin/ad quotes)
    cleaned_cust_ctx = re.sub(r"ไม่สะดวกโอน|ไม่โอน|โอนหรือปลายทาง", "", "\n".join(cust_texts))
    has_cust_img = any(t.startswith("[IMAGE:") for t in cust_texts[-5:]) or "[IMG" in "\n".join(cust_texts[-5:])
    admin_transfer_cue = any(k in non_template_joined for k in ["ยอดโอน", "ขอสลิป", "ขอสลีป", "โอนแล้วแจ้งสลิป", "ช่องทางการโอน"])
    is_transfer = any(
        k in cleaned_cust_ctx
        for k in [
            "โอนแล้ว", "ส่งสลิป", "โอนเรียบร้อย", "ขอเลขบัญชี", "โอนค่ะ", "โอนครับ",
            "เปนโอน", "เป็นโอน", "โอนเลย", "จ่ายเงินเลย", "รับโอน",
            "ส่งการชำระเงิน", "โอนชำระ", "แนบสลิป", "ชำระเงินจำนวน", "สลิป",
        ]
    ) or (admin_transfer_cue and has_cust_img and "ปลายทาง" not in cleaned_cust_ctx[-80:])
    payment_method = "โอน" if is_transfer else "ปลายทาง"

    explicit_amount = False
    amount = 1290
    recent_cust_order = "\n".join(cust_texts[-2:])
    cust_explicit_single = bool(re.search(r"(?:1\s*ตัว|ตัวเดียว|รับตัวนี้|เอาตัวนี้|รุ่นนี้|1,290|1290|1,190|1190|1,090|1090|990)", recent_cust_order))
    cust_wants_multi = (not cust_explicit_single) and any(
        k in recent_cust_order for k in ["2 ตัว", "2ตัว", "สองตัว", "2ชุด", "2 ชุด", "เอาทั้ง 2", "เอา2ตัว", "2400", "2,400"]
    )
    recent_non_template = "\n".join(non_template_msgs[-8:])
    recent_quote_ctx = re.sub(
        r"[^\n]{0,40}(?:โปรคู่|จับคู่|ซื้อคู่|2\s*ตัว|คู่ละ)[^\n]{0,40}2[,]?[234]00",
        "",
        recent_non_template,
    )
    m_fb_pay = re.search(r"ส่งการชำระเงินจำนวน\s*[฿]?\s*([\d,]+)", recent_cust_block)
    m_admin_quote = re.search(
        r"(?:โอน|ลด|ยอด|ราคา|เหลือ|ตัวละ|หลุดมา|เสื้อ\+กางเกง|รวม)\D{0,15}(1[,]?590|1[,]?290|1[,]?250|1[,]?200|1[,]?190|1[,]?150|1[,]?090|1[,]?050|2[,]?400|2[,]?300|2[,]?200|990|950|890)",
        recent_quote_ctx,
    )
    if m_admin_quote and (not cust_wants_multi) and int(m_admin_quote.group(1).replace(",", "")) >= 2000:
        # Never let a 2-pair promo quote (2,400) override a single-item 1,290 order
        m_admin_quote = re.search(
            r"(?:โอน|ลด|ยอด|ราคา|เหลือ|ตัวละ|หลุดมา|เสื้อ\+กางเกง|รวม)\D{0,15}(1[,]?590|1[,]?290|1[,]?250|1[,]?200|1[,]?190|1[,]?150|1[,]?090|1[,]?050|990|950|890)",
            recent_quote_ctx,
        )
    m_sched = re.search(r"(?:ส่ง(?:วันที่)?|สะดวกรับวันที่|นัดรับ(?:วันที่)?)\s*[,]?\s*(\d{1,2}(?:\s*(?:พ\.?ย\.?|ธ\.?ค\.?|ม\.?ค\.?|พฤศจิกา(?:ยน)?|ธันวา|มกรา))?)", cust_joined)
    scheduled_date = m_sched.group(1).strip() if m_sched else ""
    if m_fb_pay:
        amount = int(m_fb_pay.group(1).replace(",", ""))
        explicit_amount = True
    elif m_admin_quote:
        amount = int(m_admin_quote.group(1).replace(",", ""))
        explicit_amount = True
    elif "1590" in non_template_joined or "1,590" in non_template_joined:
        amount = 1590
        explicit_amount = True
    elif "1190" in non_template_joined or "1,190" in non_template_joined:
        amount = 1190
        explicit_amount = True
    elif "1090" in non_template_joined or "1,090" in non_template_joined:
        amount = 1090
        explicit_amount = True
    elif cust_wants_multi:
        amount = 2400
        explicit_amount = True
    elif "1100" in f"{cust_joined}\n{ad_intro}" or "1,100" in f"{cust_joined}\n{ad_intro}":
        amount = 1100
        explicit_amount = True
    elif "990" in f"{cust_joined}\n{ad_intro}" or "ขาสั้น" in f"{cust_joined}\n{ad_intro}":
        amount = 990
        explicit_amount = True
    elif "1290" in f"{cust_joined}\n{ad_intro}" or "1,290" in f"{cust_joined}\n{ad_intro}":
        amount = 1290
        explicit_amount = True

    source_tag = f"ลูกค้า : จากเพจ" + (f" ({ad_name})" if ad_name else "")
    transfer_line = f"โอน : {amount}" if payment_method == "โอน" else "โอน :"
    cod_line = f"ปลายทาง : {amount}" if payment_method == "ปลายทาง" else "ปลายทาง :"

    raw_summary = (
        f"{source_tag}\n\n"
        f"สรุปออเดอร์การสั่งซื้อ\n"
        f"จำนวน : {items}\n"
        f"{transfer_line}\n"
        f"{cod_line}\n"
        f"ชื่อ : {recipient_name}\n"
        f"ที่อยู่ : {address}\n"
        f"เบอร์ : {phone}\n"
        f"FB : {customer_name}"
    )

    return {
        "psid": psid,
        "fb_name": customer_name,
        "recipient_name": recipient_name,
        "phone": phone,
        "address": address,
        "items": items,
        "payment_method": payment_method,
        "amount": amount,
        "explicit_details": bool(skus and sizes and explicit_amount),
        "branch": branch,
        "ad_name": ad_name,
        "scheduled_date": scheduled_date,
        "raw_summary": raw_summary,
    }


def send_order_to_telegram(order: Dict[str, Any]) -> bool:
    # Disabled by default: human admins summarize orders into "jeans around 2" themselves
    if os.getenv("TELEGRAM_SEND_ORDER_SUMMARY", "false").lower() != "true":
        return False

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not bot_token:
        return False

    # Always post closed orders ONLY to "jeans around 2" (TELEGRAM_ONLINE_CHAT_ID = -4242902075); never post order messages anywhere else
    chat_id = (os.getenv("TELEGRAM_ONLINE_CHAT_ID", "-4242902075") or "-4242902075").strip()
    if not chat_id:
        return False

    try:
        r = requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": order["raw_summary"]},
            timeout=10,
        )
        return r.status_code == 200
    except Exception as e:
        print(f"[OrderCloser] Telegram send error: {e}")
        return False


def fire_meta_capi_purchase(order: Dict[str, Any], psid: str) -> bool:
    pixel_id = os.getenv("PIXEL_ID", "1026583581319095")
    token = meta_client.get_user_token()
    if not pixel_id or not token:
        return False
    try:
        payload = {
            "data": [
                {
                    "event_name": "Purchase",
                    "event_time": int(time.time()),
                    "action_source": "business_messaging",
                    "messaging_channel": "messenger",
                    "user_data": {"page_id": meta_client.page_id, "page_scoped_user_id": psid},
                    "custom_data": {
                        "currency": "THB",
                        "value": float(order.get("amount", 1290)),
                        "content_name": order.get("items", "XRP53"),
                    },
                }
            ]
        }
        r = requests.post(
            f"https://graph.facebook.com/v21.0/{pixel_id}/events",
            params={"access_token": token},
            json=payload,
            timeout=10,
        )
        return r.status_code == 200
    except Exception as e:
        print(f"[OrderCloser] Meta CAPI Purchase error: {e}")
        return False


def close_and_record_order(
    psid: str,
    customer_name: str,
    messages: List[Dict[str, Any]],
    branch: str = "ONLINE",
    ad_name: str = "",
    dry_run: bool = True,
) -> Dict[str, Any]:
    order = extract_order_from_chat(psid, customer_name, messages, branch, ad_name)
    tg_ok = False if dry_run else send_order_to_telegram(order)
    capi_ok = False if dry_run else fire_meta_capi_purchase(order, psid)
    order["telegram_sent"] = tg_ok
    order["capi_sent"] = capi_ok
    order_id = save_order(order)
    order["id"] = order_id

    upsert_customer_crm(
        fb_name=customer_name,
        recipient_name=order["recipient_name"],
        phone=order["phone"],
        address=order["address"],
        last_sku=order["items"],
    )

    short_name = (customer_name or "พี่").split()[0]
    sched = order.get("scheduled_date")
    needs_size = order.get("items", "").endswith("รอระบุไซส์")
    summary_card = (
        f"📋 สรุปออเดอร์การสั่งซื้อ\n"
        f"• รายการ: {order['items']}\n"
        f"• ยอดชำระ: {order['amount']:,} บาท ({order['payment_method']})\n"
        f"• ชื่อผู้รับ: {order['recipient_name']}\n"
        f"• ที่อยู่: {order['address']}\n"
        f"• เบอร์โทร: {order['phone']}"
    )
    if order.get("explicit_details"):
        first_bubble = f"ได้รับข้อมูลครบถ้วนแล้วนะคะพี่{short_name} หนูบันทึกออเดอร์เรียบร้อยค่ะ\n\n{summary_card}"
    else:
        first_bubble = f"ได้รับข้อมูลครบถ้วนแล้วนะคะพี่{short_name} หนูสรุปออเดอร์และส่งต่อแอดมินเปิดบิลจัดส่งให้เลยค่ะ\n\n{summary_card}"
    if sched:
        second_bubble = f"หนูบันทึกนัดหมายจัดส่งให้ตามวันที่พี่แจ้ง (วันที่ {sched}) เรียบร้อยค่ะ ส่งฟรี EMS ไม่บวกเพิ่มนะคะ"
    elif needs_size:
        second_bubble = "รบกวนพี่แจ้งยืนยันไซส์ที่ใส่ (M–4XL หรือรอบเอว-สะโพก) เพิ่มเติมก่อนทีมงานแพคจัดส่งฟรี EMS ให้นะคะ"
    elif order["payment_method"] == "ปลายทาง":
        second_bubble = "จัดส่งฟรี EMS ให้ด่วนเลยนะคะ รอรับของประมาณ 1–2 วันทำการ (เก็บเงินปลายทางไม่มีบวกเพิ่ม แกะเช็คก่อนได้ค่ะ)"
    else:
        second_bubble = "ทางร้านตรวจสอบยอดเรียบร้อยแล้ว เตรียมแพ็กจัดส่งฟรี EMS ให้ด่วนเลยนะคะ รอรับของ 1–2 วันทำการค่ะ"
    confirm_bubbles = [
        first_bubble,
        second_bubble,
        f"หากได้รับของแล้วหรือต้องการสอบถามเลขพัสดุ ทักหาหนูในแชทนี้ได้ตลอดเลยนะคะพี่{short_name} ขอบพระคุณมากๆ ที่อุดหนุนค่ะ 🙏",
    ]
    return {"order": order, "confirm_bubbles": confirm_bubbles}


def update_order_and_reconfirm(
    psid: str,
    customer_name: str,
    last_cust_text: str,
    dry_run: bool = True,
) -> Dict[str, Any]:
    existing = get_latest_order_by_psid(psid)
    if not existing:
        return {"order": None, "confirm_bubbles": []}

    new_items = existing["items"]
    skus = [re.sub(r"\s+", "", s).upper() for s in SKU_RE.findall(last_cust_text)]
    sizes = [s.upper() for s in SIZE_RE.findall(last_cust_text)]
    if skus or sizes:
        old_parts = existing["items"].split("/")
        sku_part = "/".join(dict.fromkeys(skus)) if skus else old_parts[0]
        size_part = sizes[-1] if sizes else (old_parts[-1] if len(old_parts) > 1 else "")
        new_items = f"{sku_part}/{size_part}".strip("/")

    new_payment = "โอน" if "โอน" in last_cust_text else ("ปลายทาง" if "ปลายทาง" in last_cust_text else existing["payment_method"])
    new_phone_m = PHONE_RE.search(last_cust_text)
    new_phone = new_phone_m.group(0).replace(" ", "").replace("-", "") if new_phone_m else existing["phone"]
    new_address = last_cust_text.strip() if any(k in last_cust_text for k in ["ที่อยู่", "บ้านเลขที่", "ต.", "อ.", "จ."]) else existing["address"]

    transfer_line = f"โอน : {existing['amount']}" if new_payment == "โอน" else "โอน :"
    cod_line = f"ปลายทาง : {existing['amount']}" if new_payment == "ปลายทาง" else "ปลายทาง :"
    new_summary = (
        f"[แก้ไขออเดอร์ #{existing['id']}] ลูกค้า : จากเพจ\n\n"
        f"สรุปออเดอร์การสั่งซื้อ\n"
        f"จำนวน : {new_items}\n"
        f"{transfer_line}\n"
        f"{cod_line}\n"
        f"ชื่อ : {existing['recipient_name']}\n"
        f"ที่อยู่ : {new_address}\n"
        f"เบอร์ : {new_phone}\n"
        f"FB : {customer_name}"
    )

    update_order_by_id(
        existing["id"],
        {
            "items": new_items,
            "payment_method": new_payment,
            "phone": new_phone,
            "address": new_address,
            "raw_summary": new_summary,
        },
    )
    updated = {**existing, "items": new_items, "payment_method": new_payment, "phone": new_phone, "address": new_address, "raw_summary": new_summary}
    if not dry_run:
        send_order_to_telegram(updated)

    short_name = (customer_name or "พี่").split()[0]
    confirm_bubbles = [
        f"รับทราบค่ะพี่{short_name} หนูแก้ไขออเดอร์ให้เรียบร้อยแล้วนะคะ เป็น {new_items} ({new_payment}) ยอด {existing['amount']:,} บาทค่ะ",
        f"จัดส่งไปที่: {new_address} โทร {new_phone} (ส่งฟรี EMS 1–2 วันถึงเหมือนเดิมค่ะ)",
        f"ข้อมูลถูกต้องครบถ้วนนะคะพี่{short_name} ถ้ามีตรงไหนอยากปรับเพิ่มแจ้งหนูได้เลยค่ะ?",
    ]
    return {"order": updated, "confirm_bubbles": confirm_bubbles}
