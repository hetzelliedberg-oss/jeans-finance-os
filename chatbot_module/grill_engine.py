"""Grill Engine: Anti-Annoyance, Deduplication, Handoff & Context Guardrails."""

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

REJECTION_PATTERNS = [
    r"ยังไม่รับ",
    r"ยังไม่อยาก",
    r"ยังไม่ได้สั่ง",
    r"ยังไม่สั่ง",
    r"^ยัง(?:นะ)?(?:คะ|ค่ะ|ครับ)?$",
    r"^นัง(?:นะ)?(?:คะ|ค่ะ|ครับ)?$",
    r"ยังก่อน",
    r"ไว้ก่อน",
    r"ทักไว้ก่อน",
    r"ขอดูก่อน",
    r"ขอคิดดู",
    r"เดี๋ยวทักใหม่",
    r"เดี๋ยวสั่งอีกที",
    r"ไว้ทัก",
    r"ไม่เอา",
    r"ไม่รับ(?:ค่ะ|คะ|ครับ|จ้า|นะ|แล้ว|$)",
    r"ไม่สะดวก",
    r"ไม่เป็นไร",
    r"ยังไม่มี(?:เงิน|งบ|ตัง)",
    r"ใส่ไม่(?:ได้|ลง)",
    r"ใส่ไม้ได้",
    r"อย่าทัก",
    r"ไม่ต้องทัก",
    r"รำคาญ",
    r"เลิกส่ง",
    r"ยกเลิก",
    r"ซื้อแล้ว",
    r"รอรุ่น",
]

DELIVERY_THANKS_PATTERNS = [
    r"ได้รับ(?!.*(?:ยังไม่ได้|ยังไม่ถึง|ไม่ครบ|ผิด)).{0,25}(?:ของ|สินค้า|กางเกง|กระโปรง|เสื้อ|พัสดุ|แล้ว)",
    r"ถึงมือ.{0,20}แล้ว",
    r"ของถึงแล้ว",
    r"ใส่ได้พอดี",
    r"พอดีเป๊ะ",
    r"สั่งมาแล้ว.{0,15}ได้แล้ว",
    r"รับมาแล้ว",
    r"ไปซื้อ(?:มา)?(?:เรียบร้อย|หน้าร้านแล้ว)",
    r"(?:ไป|แวะ|เพิ่ง)?(?:ซื้อ|จัด|อุดหนุน|สอย)(?:มา)?(?:แล้ว|เรียบร้อย)",
    r"ได้(?:เกง|กางเกง|กระโปรง|เสื้อ|ของ|สินค้า)?\s*\d+\s*ตัว",
    r"ได้(?:มา)?(?:มะ|เมื่อ)วาน",
    r"ได้ลดด้วย",
    r"ได้ของแล้ว",
]

STORE_VISIT_PATTERNS = [
    r"จะเข้าไป",
    r"จะเข้าดู",
    r"เข้าดูเอง",
    r"เข้าไปดูเอง",
    r"เด[ี๋่]?ยวเข้าไป",
    r"เด่วเข้าไป",
    r"เดี๋ยวแวะ",
    r"แวะไป",
    r"จะแวะ(?:ไป)?ดู",
    r"เดี๋ยวไปดู",
    r"พรุ่งนี้.*ไป",
    r"วันอาทิตย์.*ไป",
    r"วันเสาร์.*ไป",
    r"ไปหน้าร้าน",
    r"จะแวะเข้ามา",
    r"เด[ี๋่]?ยวพาไปดู",
    r"พาไปดูที่สาขา",
]

SYSTEM_ORDER_MARKERS = (
    "ทำเครื่องหมายคำสั่งซื้อ",
    "marked the order as",
    "created a transfer request",
    "คุณร้องขอไป",
    "กำหนดการสนทนานี้ให้กับ",
    "assigned this conversation",
    "เชื่อมต่อบัญชีธนาคาร",
    "ตรวจสอบความถูกต้องของสลิป",
)

ADMIN_BILL_MARKERS = (
    "สรุปออเดอร์การสั่งซื้อ",
    "เปิดบิลแล้ว",
    "เปิดบิลให้แล้ว",
    "รับยอด",
    "ได้รับยอด",
    "แพ็กจัดส่ง",
    "จัดส่งให้เรียบร้อย",
    "โอนเรียบร้อย",
    "marked the order as paid",
    "marked the order as dispatched",
    "ทำเครื่องหมายคำสั่งซื้อว่าชำระเงินแล้ว",
    "ทำเครื่องหมายคำสั่งซื้อว่าจัดส่งแล้ว",
    "คุณร้องขอไป",
)

AUTO_AD_GREETING_CUES = (
    "ตอบกลับโฆษณา",
    "สั่งซื้อทักแชทแจ้งรอบเอวมาเลยค่า",
    "ของพร้อมส่ง สั่งเลยมีครบไซส์ m-4xl ค่ะ ส่งฟรีมีปลายทาง",
)


def is_auto_ad_greeting_text(text: str, prev_text: str = "") -> bool:
    """Return True if a page message is Facebook's automatic Ad-click greeting (header OR paired template body)."""
    t = (text or "").strip()
    p = (prev_text or "").strip()
    if "ตอบกลับโฆษณา" in t or "ตอบกลับโฆษณา" in p:
        return True
    low = t.lower()
    if any(cue in low for cue in AUTO_AD_GREETING_CUES):
        return True
    if ("เอวเท่าไรคะพี่" in low or "เอวเท่าไหร่คะพี่" in low) and len(low) >= 60 and any(
        k in low for k in ("บาท", "ส่งฟรี", "ปลายทาง")
    ):
        return True
    return False

COMPLAINT_PATTERNS = [
    r"ส่งผิด",
    r"ผิดลาย",
    r"ผิดไซ[ส์ซ]",
    r"ผิดสี",
    r"ผิดแบบ",
    r"ไม่ได้สั่ง(?:ลาย|ตัว|สี|แบบ)นี้",
    r"ไม่ตรงปก",
    r"ตำหนิ",
    r"ขาด",
    r"เคลม",
    r"เปลี่ยนของ",
    r"เปลี่ยนไซซ์",
    r"เปลี่ยนสี",
    r"เปลี่ยน(?:ที่|สินค้า|รุ่น|ขนาด|ตัว|ลาย|ไป|ของ|ไซ[ส์ซ]|สี)",
    r"(?:ถือ|เอา|นำ|แวะ|ส่ง)ไปเปลี่ยน",
    r"ขอเปลี่ยน",
    r"เป้ายิ้ม",
    r"แก้ไซซ์",
    r"แก้ที่อยู่",
    r"คืนเงิน",
    r"โกง",
    r"ช้ามาก",
    r"ยังไม่ได้ของ",
    r"ตามของ",
    r"เลขพัสดุ",
    r"(?:เล็ก|ใหญ่|คับ|หลวม|สั้น)กว่า(?:เดิม|ที่เคยสั่ง|ตัวเก่า|\s*\d\s*xl)",
    r"ทำ[ไใ]ม.{0,25}(?:เล็ก|ใหญ่|คับ|หลวม|สั้น)",
    r"[ไใ]ส่[ไใ]ม่ได้",
    r"ขนาดมันเล็ก",
]

PAYMENT_EVENT_PATTERNS = [
    r"ส่งการชำระเงิน",
    r"ชำระเงินจำนวน",
]

CLOSING_ACK_EXACT = {
    "ขอบคุณ", "ขอบคุณค่ะ", "ขอบคุณคะ", "ขอบคุณครับ", "ขอบคุณมาก", "ขอบคุณมากค่ะ", "ขอบคุณมากคะ", "ขอบคุณมากครับ", "ขอบพระคุณค่ะ", "ขอบพระคุณคะ", "ขอบพระคุณครับ",
    "โอเค", "โอเคค่ะ", "โอเคคะ", "โอเคครับ", "โอเคจ้า", "โอเคค่ะ รับทราบค่ะ", "โอเคครับ รับทราบครับ", "โอเครค่ะ", "โอเครคะ", "ok", "okay",
    "จ้า", "จ้ะ", "ค่ะ", "คะ", "ครับ", "ได้จ้า", "รับทราบ", "รับทราบค่ะ", "รับทราบคะ", "รับทราบครับ", "รับทราบจ้า", "ได้เลยค่ะ", "ได้เลยคะ", "ได้เลยครับ",
    "สาธุ", "เยี่ยม", "ดีค่ะ", "ดีครับ", "👍", "🙏", "❤️",
}

PHONE_RE = re.compile(r"0[689]\d[\s\-]?\d{3}[\s\-]?\d{4}")
ADDRESS_HINTS = ["บ้านเลขที่", "หมู่", "ต.", "ตำบล", "อ.", "อำเภอ", "จ.", "จังหวัด", "แขวง", "เขต", "ซอย", "ถนน", "รหัสไปรษณีย์"]


def parse_iso_dt(dt_str: Optional[str]) -> Optional[datetime]:
    if not dt_str:
        return None
    try:
        s = dt_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


FOOTER_BRANCH_RE = re.compile(
    r"(?:ลองไซส์\s*)?(?:ที่)?หน้าร้าน(?:ที่|เรามี\s*3\s*สาขา(?:คือ)?)?[^\n]{0,160}(?:ขอนแก่น[^\n]{0,80}โคราช|โคราช[^\n]{0,80}อุดร|อุดร[^\n]{0,80}ขอนแก่น)"
    r"|พิกัดหน้าร้าน[^\n]{0,180}(?:ขอนแก่น[^\n]{0,80}โคราช)"
    r"|ตอนนี้ทางร้านยังไม่มีสาขา[^\n]+",
    re.IGNORECASE,
)


def _strip_branch_footer(s: str) -> str:
    """Strip 3-branch storefront footers (e.g. 'ลองไซส์ ที่หน้าร้านที่เซนทรัลขอนแก่น,เซนทรัลโคราช,เซนทรัลอุดร')
    so the Ad's primary branch headline (e.g. 'ที่เซนทรัลโคราช') is preserved instead of masked as ONLINE."""
    return FOOTER_BRANCH_RE.sub(" ", s or "").strip()


def _match_branches(s: str) -> List[str]:
    low = (s or "").lower()
    found: List[str] = []
    if any(k in low for k in ["โคราช", "เซนทรัลโคราช", "เซ็นทรัลโคราช", "korat", "นครราชสีมา", "จอหอ"]):
        found.append("KORAT")
    if any(k in low for k in ["อุดร", "เซนทรัลอุดร", "เซ็นทรัลอุดร", "udn", "udon"]):
        found.append("UDN")
    if any(k in low for k in ["ขอนแก่น", "ม.ข.", "มข."]) or re.search(r"\b(?:kkc|khon kaen)\b|(?:^|\s)มข(?:\s|$)", low):
        found.append("KKC")
    return found


def _dominant_ad_branch(s: str) -> str:
    """Resolve primary branch of an Ad/Post message, ignoring boilerplate 3-branch footers."""
    cleaned = _strip_branch_footer(s)
    hits = _match_branches(cleaned)
    if len(hits) == 1:
        return hits[0]
    if len(hits) >= 2:
        low = cleaned.lower()
        counts = {
            "KORAT": low.count("โคราช") + low.count("นครราชสีมา") + low.count("korat"),
            "UDN": low.count("อุดร") + low.count("udon") + low.count("udn"),
            "KKC": low.count("ขอนแก่น") + low.count("kkc"),
        }
        top_b, top_c = max(counts.items(), key=lambda kv: kv[1])
        others = [c for b, c in counts.items() if b != top_b]
        if top_c > 0 and top_c > max(others or [0]):
            return top_b
    return ""


def detect_branch(
    text: str,
    ad_name: str = "",
    campaign_name: str = "",
    cust_text: str = "",
    latest_ad_text: str = "",
    ad_post_branch: str = "",
) -> str:
    # 1. Customer's own words always take highest priority (fixes 3-branch directory greetings defaulting to KKC)
    cust_hits = _match_branches(cust_text)
    if len(cust_hits) == 1:
        return cust_hits[0]
    if cust_hits:
        return cust_hits[-1]

    # 2. Latest active-session Ad greeting / Reel / single-branch admin pin BEFORE stale historical ad_name
    if latest_ad_text:
        dom = _dominant_ad_branch(latest_ad_text)
        if dom:
            return dom

    # 3. Resolved Ad/Post branch from Meta Ads API + Story/Reel caption lookup
    if ad_post_branch in ("KKC", "KORAT", "UDN"):
        return ad_post_branch

    # 4. Explicit campaign/ad name
    camp_hits = _match_branches(f"{ad_name} {campaign_name}")
    if len(camp_hits) == 1:
        return camp_hits[0]

    # 5. Fallback recent thread text (stripping 3-branch footers first!)
    dom_thread = _dominant_ad_branch(text)
    if dom_thread:
        return dom_thread

    return "ONLINE"


def detect_intent(last_customer_text: str, is_followup: bool = False) -> str:
    if is_followup:
        return "SLOW_REPLY"
    t = (last_customer_text or "").lower()
    t = re.sub(r"(?:เอ้กซ์แอล|เอ็กซ์แอล|เอ้กแอล|เอ็กแอล|เอกแอล|เอ้กl|เอ็กl)", "xl", t)
    t_no_skirt = re.sub(r"กระโปรง|โปรง", "", t)
    if any(k in t for k in ["เอวสูง", "เอวต่ำ", "รอบสะดือ", "high waist", "low waist", "mid rise", "high rise"]):
        return "ASK_WAIST_RISE"
    if any(k in t for k in ["ขอดูสี", "มีกี่สี", "กี่สี", "สีอะไร", "ความยาว", "ยาวเท่า", "ยาวกี่", "ขอดูความยาว", "color", "colour", "length", "how long", "inseam"]):
        return "ASK_COLOR_LENGTH"
    if any(k in t for k in ["ขาม้า", "กระบอก", "ทรงอะไร", "ทรงไหน", "ขาปล่อย", "flare", "straight leg", "wide leg", "fitting", "cutting"]):
        return "ASK_STYLE_FIT"
    if any(k in t_no_skirt for k in ["ราคา", "เท่าไหร่", "เท่าไร", "กี่บาท", "จัดโปร", "มีโปร", "โปรคู่", "โปรโมชั่น", "ลด", "price", "how much", "cost", "promo", "discount"]):
        return "ASK_PRICE"
    if any(k in t for k in ["ไซส์", "ไซด์", "ตาราง", "ขนาด", "ขยาด", "เอว", "สะโพก", "ต้นขา", "xl", "2xl", "3xl", "4xl", "น้ำหนัก", "สูง", "size", "waist", "hip", "chart", "measurement"]):
        return "ASK_SIZE"
    if any(k in t for k in ["สาขา", "หน้าร้าน", "อยู่ตรงไหน", "อยู่ส่วนไหน", "พิกัด", "เซ็นทรัล", "เซนทรัล", "ขอนแก่น", "โคราช", "อุดร", "กทม", "กรุงเทพ", "ชล", "ระยอ", "สัตหีบ", "where", "shop", "store", "branch", "location", "address", "mall", "bangkok"]):
        return "ASK_BRANCH"
    if any(k in t for k in ["ปลายทาง", "cod", "โอน", "ส่งฟรี", "ค่าส่ง", "ems", "กี่วัน", "cash on delivery", "shipping", "delivery", "how many days"]):
        return "ASK_COD"
    if any(k in t for k in ["เสื้อ", "กระโปรง", "ขาสั้น", "ขายาว", "xrp", "สี", "ลายปัก", "มีของ", "ด้านหลัง", "skirt", "shorts", "shirt", "available", "in stock"]):
        return "ASK_STOCK_MODEL"
    return "GREETING_INTEREST"


def analyze_already_covered(messages: List[Dict[str, Any]]) -> Dict[str, Any]:
    admin_texts = [m.get("text", "") for m in messages if m.get("sender_role") in ("admin", "bot")]
    bot_like_texts = [
        m.get("text", "")
        for m in messages
        if m.get("sender_role") == "bot"
        or (m.get("sender_role") == "admin" and any(k in (m.get("text") or "") for k in ("Jeans Around", "1,290", "990", "ปลายทาง", "ทักทิ้งไว้", "น้องแนะนำ", "แวะมาลอง")))
    ]
    joined = "\n".join(admin_texts).lower()

    consecutive_unanswered = 0
    for m in reversed(messages):
        if m.get("sender_role") == "customer":
            break
        consecutive_unanswered += 1

    return {
        "sent_price": any(k in joined for k in ["1,290", "1290", "990", "1,100", "1,090", "1090", "1,190", "1190", "2,400", "2400"]),
        "sent_2400": any(k in joined for k in ["2,400", "2400"]),
        "sent_size_chart": any(k in joined for k in ["ตารางไซส์", "เอว 26", "เอว 28", "สะโพก"]),
        "sent_branch_kkc": "เซ็นทรัลขอนแก่น" in joined or "เซนทรัล ขอนแก่น" in joined or "ชั้น g" in joined,
        "sent_branch_korat": "เซ็นทรัลโคราช" in joined or "เซนทรัล โคราช" in joined,
        "sent_branch_udn": "เซ็นทรัลอุดร" in joined or "เซนทรัล อุดร" in joined,
        "sent_cod": any(k in joined for k in ["ปลายทาง", "cod", "ส่งฟรี"]),
        "asked_size": any(k in joined for k in ["เอวเท่าไหร่", "เอวเท่าไร", "ใส่ไซส์อะไร", "รอบเอว", "สะโพกประมาณ"]),
        "asked_address": any(k in joined for k in ["ขอชื่อ", "ที่อยู่", "เบอร์โทร", "สั่งเลยมั้ย", "สั่งเลยไหม"]),
        "sent_no_size": any(k in joined for k in ["ยังไม่มีถึงเอว", "ใหญ่สุดจะเป็น 4xl", "ใหญ่สุด40", "เอว44 ไม่มี", "เอว 44 ไม่มี", "ไม่มีเลยค่ะพี่", "ร้านเอวใหญ่สุด", "รุ่นนี้ไม่มีค่ะ", "รุ่นนี้ไม่มีค่ะ"]),
        "admin_billed": any(any(mk in t for mk in ADMIN_BILL_MARKERS) for t in admin_texts),
        "consecutive_unanswered": consecutive_unanswered,
        "recent_bot_texts": [t for t in (bot_like_texts or admin_texts)[-20:] if t],
    }


def grill_conversation(
    psid: str,
    customer_name: str,
    messages: List[Dict[str, Any]],
    conv_meta: Optional[Dict[str, Any]] = None,
    is_followup: bool = False,
    max_followups: int = 8,
    trigger_type: str = "INSTANT_REPLY",
) -> Dict[str, Any]:
    """
    Evaluate whether it is safe, helpful, and non-annoying to send a 3-Enter reply.
    Returns:
      decision: 'SEND' | 'BLOCK' | 'HANDOFF_ORDER' | 'HANDOFF_ESCALATE'
      reason: human-readable explanation
      branch: 'KKC' | 'KORAT' | 'UDN' | 'ONLINE'
      intent: detected intent
      already_covered: dict of flags to prevent repetition
    """
    conv_meta = conv_meta or {}
    if conv_meta.get("status") == "BLACKLISTED":
        return {"decision": "BLOCK", "reason": f"Blacklisted previously: {conv_meta.get('blacklist_reason')}"}

    # Filter out Meta system order notifications misattributed to customer role
    customer_msgs = [
        m for m in messages
        if m.get("sender_role") == "customer"
        and not any(mk in (m.get("text") or "") for mk in SYSTEM_ORDER_MARKERS)
    ]
    if not customer_msgs:
        return {"decision": "BLOCK", "reason": "No customer messages in thread"}

    last_cust = customer_msgs[-1]
    last_cust_text = (last_cust.get("text") or "").strip()
    last_cust_dt = parse_iso_dt(last_cust.get("created_at") or conv_meta.get("last_customer_msg_at"))

    # Use ONLY active-window messages (within 18h of last_cust) for branch & ad detection so 2-week-old UDN messages never override today's KKC Ad!
    active_msgs = []
    for m in messages:
        m_dt = parse_iso_dt(m.get("created_at"))
        if not last_cust_dt or not m_dt or (last_cust_dt - m_dt).total_seconds() <= 18 * 3600:
            active_msgs.append(m)

    # Slice off old completed bills when customer returns on a new Ad click, >1h later, or asks about a new product
    allow_returning_won = False
    last_bill_idx = -1
    for i, m in enumerate(active_msgs):
        if any(mk in (m.get("text") or "") for mk in ADMIN_BILL_MARKERS):
            last_bill_idx = i
    is_new_product_q = any(
        k in last_cust_text
        for k in ("มี", "สนใจ", "ราคา", "เท่าไหร่", "เท่าไร", "ไซส์", "เอว", "ขาสั้น", "ขาสามส่วน", "กระโปรง", "เสื้อ", "รุ่น")
    )
    if last_bill_idx >= 0 and last_bill_idx < len(active_msgs) - 1:
        bill_msg_dt = parse_iso_dt(active_msgs[last_bill_idx].get("created_at"))
        after_bill_msgs = active_msgs[last_bill_idx + 1 :]
        has_ad_after_bill = any("ตอบกลับโฆษณา" in (m.get("text") or "") for m in after_bill_msgs)
        hours_after_bill = ((last_cust_dt - bill_msg_dt).total_seconds() / 3600.0) if (last_cust_dt and bill_msg_dt) else 0.0
        if has_ad_after_bill or hours_after_bill > 1.0 or is_new_product_q:
            active_msgs = after_bill_msgs
            allow_returning_won = True
    elif last_bill_idx < 0 and conv_meta.get("status") == "WON":
        has_ad_in_active = any("ตอบกลับโฆษณา" in (m.get("text") or "") for m in active_msgs)
        if has_ad_in_active or is_new_product_q:
            allow_returning_won = True

    active_cust_msgs = [m for m in customer_msgs if m in active_msgs] or [last_cust]
    all_cust_text = " ".join((m.get("text") or "") for m in active_cust_msgs[-6:])
    all_thread_text = " ".join((m.get("text") or "") for m in active_msgs[-8:])

    # Collect Ad / Reel / single-branch admin pin text, pairing Meta's "ตอบกลับโฆษณา" header with its adjacent body bubble.
    # Strip boilerplate 3-branch footers ("ลองไซส์ ที่หน้าร้านที่เซนทรัลขอนแก่น,เซนทรัลโคราช,เซนทรัลอุดร") so the Ad's real branch is NEVER wiped!
    def _find_latest_ad_text(msg_list: List[Dict[str, Any]]) -> str:
        for i in range(len(msg_list) - 1, -1, -1):
            m = msg_list[i]
            if m.get("sender_role") not in ("admin", "bot"):
                continue
            txt = (m.get("text") or "").strip()
            if not txt or "หน้าร้านเรามี 3 สาขา" in txt or "พิกัดหน้าร้าน" in txt or "ตอนนี้ทางร้านยังไม่มีสาขา" in txt:
                continue
            is_ad_cue = (
                "ตอบกลับโฆษณา" in txt
                or "จากคลิป/แอด" in txt
                or "facebook.com/reel" in txt
                or "facebook.com/photo" in txt
                or "@" in txt
                or "เซนทรัล" in txt
                or "เซ็นทรัล" in txt
                or bool(_match_branches(txt))
            )
            if not is_ad_cue:
                continue
            combined_ad_txt = txt
            if "ตอบกลับโฆษณา" in txt and i + 1 < len(msg_list):
                nxt = (msg_list[i + 1].get("text") or "").strip()
                if nxt and ("หน้าร้านเรามี 3 สาขา" not in nxt):
                    combined_ad_txt = f"{txt} {nxt}"
            if _dominant_ad_branch(combined_ad_txt):
                return combined_ad_txt
        return ""

    latest_ad_text = _find_latest_ad_text(active_msgs) or _find_latest_ad_text(messages)

    camp_name = conv_meta.get("campaign_name") or ""
    post_branch = conv_meta.get("ad_post_branch") or ""
    m_pb = re.search(r"POST_BRANCH:(KKC|KORAT|UDN)", camp_name)
    if m_pb and not post_branch:
        post_branch = m_pb.group(1)
    if not post_branch and not latest_ad_text and conv_meta.get("branch") in ("KKC", "KORAT", "UDN"):
        post_branch = conv_meta["branch"]

    branch = detect_branch(
        all_thread_text,
        conv_meta.get("ad_name") or "",
        camp_name,
        cust_text=all_cust_text,
        latest_ad_text=latest_ad_text,
        ad_post_branch=post_branch,
    )
    intent = detect_intent(last_cust_text, is_followup=is_followup)
    covered = analyze_already_covered(active_msgs)

    # 1. Check 24-hour Meta messaging window
    if last_cust_dt:
        hours_since = (datetime.now(timezone.utc) - last_cust_dt).total_seconds() / 3600.0
        if hours_since > 23.5:
            return {
                "decision": "BLOCK",
                "end_conversation": True,
                "reason": f"Outside 24h Meta window ({hours_since:.1f}h since last customer msg)",
                "branch": branch,
                "intent": intent,
                "already_covered": covered,
            }

    # 2a. Check complaints / claims FIRST (even across rapid multi-bubble bursts before human admin resolves!)
    # Gather customer messages since the last substantive human admin resolution
    unhandled_cust = []
    for m in reversed(active_msgs):
        role = m.get("sender_role")
        txt = m.get("text") or ""
        if role == "admin" and any(k in txt for k in ["ขออภัย", "ส่งเปลี่ยน", "แก้ไขให้", "สรุปออเดอร์", "เลขพัสดุ", "เปลี่ยนให้"]):
            break
        if role == "customer" and txt and not any(mk in txt for mk in SYSTEM_ORDER_MARKERS):
            unhandled_cust.append(txt)
    unhandled_cust.reverse()
    unhandled_joined = " ".join(unhandled_cust[-4:]) or last_cust_text
    for pat in COMPLAINT_PATTERNS:
        if re.search(pat, last_cust_text, re.IGNORECASE) or re.search(pat, unhandled_joined, re.IGNORECASE):
            return {
                "decision": "HANDOFF_ESCALATE",
                "reason": f"Support/claim keyword detected ('{pat}') -> Escalate to Telegram human admin",
                "branch": branch,
                "intent": intent,
                "already_covered": covered,
            }

    # 2a-bis. Delivery/store-purchase confirmation ("ได้รับของแล้ว", "สินค้าถึงมือ", "ไปซื้อมาเรียบร้อยแล้ว") ->
    # Send ONE warm thank-you + fabric care reply (NO selling!) and close gracefully; block repeated acks.
    recent_cust_pair = re.sub(
        r"ไม่ผิดหวัง|ผิดหวัง",
        "",
        " ".join((m.get("text") or "") for m in active_cust_msgs[-2:]),
    )
    has_negative_stop = bool(re.search(r"ไม่เอา|ไม่รับ|อย่าทัก|ไม่ต้องทัก|รำคาญ|ยกเลิก|คืนเงิน", last_cust_text))
    has_new_product_q = any(
        q in last_cust_text
        for q in ["ราคา", "เท่าไหร่", "เท่าไร", "กี่บาท", "กระโปรง", "ขาสั้น", "รุ่นอื่น", "สั่งเพิ่ม", "ตัวใหม่", "อีกตัว", "มีสี", "ขอดู"]
    )
    if not is_followup and not has_negative_stop and not has_new_product_q:
        if any(re.search(pat, last_cust_text, re.IGNORECASE) for pat in DELIVERY_THANKS_PATTERNS) or any(
            re.search(pat, recent_cust_pair, re.IGNORECASE) for pat in DELIVERY_THANKS_PATTERNS
        ):
            already_thanked = conv_meta.get("status") == "CLOSED_GRACEFULLY" or any(
                any(k in (m.get("text") or "") for k in ("ดีใจมากเลยค่ะที่ได้รับ", "ใส่พอดีถูกใจ", "ดูแลซักถนอม", "ใส่ถุงถนอมผ้า"))
                for m in active_msgs
                if m.get("sender_role") in ("admin", "bot")
            )
            if already_thanked:
                return {
                    "decision": "BLOCK",
                    "end_conversation": True,
                    "reason": "Already sent after-sales thank-you -> Stop gracefully without repeating",
                    "branch": branch,
                    "intent": "AFTER_SALES_THANKS",
                    "already_covered": covered,
                }
            return {
                "decision": "SEND",
                "close_after_send": True,
                "reason": "Customer confirmed delivery / purchase -> Send warm thank-you & care reply and close gracefully",
                "branch": branch,
                "intent": "AFTER_SALES_THANKS",
                "already_covered": covered,
            }

    # 2. Check explicit rejection / annoyance
    for pat in REJECTION_PATTERNS:
        if re.search(pat, last_cust_text, re.IGNORECASE):
            is_soft_stop = pat in (
                r"ทักไว้ก่อน",
                r"เดี๋ยวสั่งอีกที",
                r"ขอดูก่อน",
                r"ขอคิดดู",
                r"ยังไม่มี(?:เงิน|งบ|ตัง)",
                r"ซื้อแล้ว",
                r"รอรุ่น",
            )
            return {
                "decision": "BLOCK",
                "blacklist": not is_soft_stop,
                "end_conversation": is_soft_stop,
                "reason": f"Customer stop/rejection detected ('{pat}') -> Stop follow-ups cleanly",
                "branch": branch,
                "intent": intent,
                "already_covered": covered,
            }

    # 2b. Check natural conversation-ending / polite acknowledgment / sticker-only / sent_no_size ack
    has_any_page_reply = any(
        m.get("sender_role") in ("bot", "admin")
        and not is_auto_ad_greeting_text(
            m.get("text") or "",
            messages[idx - 1].get("text") or "" if idx > 0 else "",
        )
        for idx, m in enumerate(messages)
    )
    if covered.get("sent_no_size") and (last_cust_text == "[STICKER]" or len(last_cust_text) <= 20):
        return {
            "decision": "BLOCK",
            "end_conversation": True,
            "reason": "Already told customer max size is out-of-range -> Stop gracefully",
            "branch": branch,
            "intent": intent,
            "already_covered": covered,
        }
    if last_cust_text == "[STICKER]":
        if len(customer_msgs) <= 1 and not has_any_page_reply and conv_meta.get("status") not in ("WON", "CLOSED_GRACEFULLY"):
            pass  # Fresh Ad/Page first-turn Like/Sticker -> reply once with Ad context!
        else:
            return {
                "decision": "BLOCK",
                "end_conversation": True,
                "reason": "Customer sent closing sticker -> Stop gracefully without replying",
                "branch": branch,
                "intent": intent,
                "already_covered": covered,
            }
    if last_cust_text.startswith("[IMAGE:"):
        return {
            "decision": "HANDOFF_IMAGE",
            "reason": "Customer sent photo (possible payment slip / address screenshot / product photo) -> Analyze or escalate to admin",
            "branch": branch,
            "intent": intent,
            "already_covered": covered,
        }
    cleaned_ack = re.sub(r"[\s\.!?,]+", "", last_cust_text.lower())
    ack_remainder = re.sub(r"(ขอบพระคุณ|ขอบคุณ|รับทราบ|โอเคร|โอเค|ได้เลย|ได้จ้า|okay|ok|สาธุ|เยี่ยม|มาก|จ้า|จ้ะ|ค่ะ|คะ|ค่า|ครับ|นะ|น้า|ดี|👍|🙏|❤️)", "", cleaned_ack)
    if not last_cust_text or cleaned_ack in CLOSING_ACK_EXACT or (len(cleaned_ack) <= 30 and not ack_remainder):
        return {
            "decision": "BLOCK",
            "end_conversation": True,
            "reason": f"Natural closing/sticker ('{last_cust_text or '[sticker/attachment]'}') -> Stop gracefully without replying",
            "branch": branch,
            "intent": intent,
            "already_covered": covered,
        }
    for pat in STORE_VISIT_PATTERNS:
        if re.search(pat, last_cust_text, re.IGNORECASE):
            return {
                "decision": "BLOCK",
                "end_conversation": True,
                "reason": f"Customer confirmed store visit ('{pat}') -> Stop gracefully without nagging",
                "branch": branch,
                "intent": intent,
                "already_covered": covered,
            }

    # 2b-pre. Ongoing exchange/return/already-paid/post-apology guard:
    recent_thread_text = "\n".join((m.get("text") or "") for m in active_msgs[-8:])
    if (
        not re.search(r"(?:สั่งเพิ่ม|เอาเพิ่ม|อีกตัว|อีกสี)", last_cust_text, re.IGNORECASE)
        and re.search(r"(?:โอนจ่าย|จ่ายเงินเรียบร้อย|โอนเงินเรียบร้อย|โอนเรียบร้อย|จ่ายแล้ว|ชำระแล้ว|โอนแล้ว|ส่งสลิปแล้ว|สั่งแล้ว|สั่งไปแล้ว|ซื้อแล้ว)", last_cust_text, re.IGNORECASE)
    ):
        return {
            "decision": "BLOCK",
            "end_conversation": True,
            "reason": "Customer confirmed payment/already ordered -> Stop gracefully without pitching sales",
            "branch": branch,
            "intent": intent,
            "already_covered": covered,
        }
    if (
        re.search(r"(?:ส่งตัวที่ได้รับ|ส่งตัวเดิม|ส่งคืน|ส่งกลับ|ยังไม่ได้รับ|เบอร์โทรถูกต้อง|ยังไม่รับเพิ่ม|ส่งของมาไม่มี|ส่งมาไม่มี|ไม่มีเสื้อ|ขาดเสื้อ|ขาดกางเกง|ลืมส่ง|ส่งไม่ครบ|ได้ของไม่ครบ|เห็นของแล้ว|ตื่นเต้นมาก|ติดตามพัสดุ|กำลังนำส่ง|ส่ง.{0,12}ไปเปลี่ยน|ขอเปลี่ยน)", last_cust_text, re.IGNORECASE)
        or re.search(r"(?:ส่งเปลี่ยน|ส่ง.{0,12}ไปเปลี่ยน|ส่งผิด|ได้ไม่ครบ|ส่งไม่ครบ|ส่งของมาไม่มี|ไม่มีเสื้อ|ลืมส่ง|ตำหนิ|ขออภัย(?:ค่ะ|ค่า|คะ)\s*(?:พี่\s*)?AI\s*(?:ช่วย)?ตอบ|ขอโทษ.*ข้อความอัตโนมัติ|ยังไม่ได้รับของหรอ|รับเรื่องแก้ไข|แก้ไขออเดอร์|ติดตามพัสดุ|กำลังนำส่ง)", recent_thread_text, re.IGNORECASE)
        or (is_followup and any((m.get("text") or "").startswith("[IMAGE:") for m in active_msgs[-6:] if m.get("sender_role") == "customer"))
    ):
        return {
            "decision": "HANDOFF_ESCALATE",
            "reason": "Ongoing exchange/return/post-order support thread -> Escalate to human admin, never pitch sales",
            "branch": branch,
            "intent": intent,
            "already_covered": covered,
        }

    # 2b-bis. Shipping / parcel tracking inquiry ("ของยังไม่ถึง", "ส่งของมาวันไหน", "เลขพัสดุ") ->
    # Reply politely in chat AND escalate to human admin on Telegram (never leave customer hanging in silence!)
    is_tracking_q = bool(
        re.search(
            r"(?:ของ|กางเกง|กระโปรง|พัสดุ|สินค้า).{0,16}(?:ถึงยัง|ถึงหรือยัง|ยังไม่ถึง|ถึงไหน|ส่งยัง|ส่งหรือยัง|ส่งรึยัง|ส่งมาวันไหน|ส่งวันไหน|ส่งมาหรือยัง|ส่งมารึยัง)|(?:ส่งของมาวันไหน|ส่งมาวันไหน|เช[็๊]คให้.*ส่ง|เช[็๊]กให้.*ส่ง|เลขพัสดุ|เลขแทร็ก|tracking|เช็กพัสดุ|เช็คพัสดุ|ตามพัสดุ)",
            last_cust_text,
            re.IGNORECASE,
        )
    )
    if is_tracking_q and not is_followup:
        already_ack_tracking = any(
            m.get("sender_role") in ("bot", "admin") and "รับเรื่องเช็กสถานะพัสดุ" in (m.get("text") or "")
            for m in active_msgs[-6:]
        )
        if already_ack_tracking:
            return {
                "decision": "BLOCK",
                "reason": "Already acknowledged parcel tracking request recently — prevent duplicate reply",
                "branch": branch,
                "intent": "SKIP",
                "already_covered": covered,
            }
        return {
            "decision": "SEND",
            "also_escalate": True,
            "escalate_reason": "ลูกค้าตามพัสดุ/สอบถามสถานะจัดส่ง -> แอดมินเช็กเลขพัสดุตอบด่วน",
            "reason": "Customer asked about parcel delivery status -> Reply politely and escalate to admin",
            "branch": branch,
            "intent": "SHIPPING_TRACKING",
            "already_covered": covered,
        }

    # 2c. Stop follow-ups or duplicate closing if human admin already billed or conversation already handled
    if covered.get("admin_billed") or (not allow_returning_won and conv_meta.get("status") in ("WON", "CLOSED_GRACEFULLY")):
        cleaned_edit_probe = re.sub(r"ไม่ผิดหวัง|ผิดหวัง", "", last_cust_text)
        if any(k in cleaned_edit_probe for k in ["แก้", "เปลี่ยน", "ผิด", "เพิ่ม", "ลดไซส์", "ที่อยู่ใหม่"]) and not is_followup:
            return {
                "decision": "HANDOFF_ORDER_EDIT",
                "reason": "Returning/WON customer requested order correction -> Update order, re-notify Telegram & confirm",
                "branch": branch,
                "intent": intent,
                "already_covered": covered,
            }
        if is_followup or (messages and messages[-1].get("sender_role") in ("admin", "bot")) or any(k in (messages[-1].get("text") or "") for k in SYSTEM_ORDER_MARKERS):
            return {
                "decision": "BLOCK",
                "end_conversation": True,
                "reason": "Order already billed/paid or handled by human admin -> Stop bot interference",
                "branch": branch,
                "intent": intent,
                "already_covered": covered,
            }
        if covered.get("admin_billed") or (not allow_returning_won and conv_meta.get("status") == "WON"):
            return {
                "decision": "HANDOFF_ESCALATE",
                "reason": "Customer messaged after bill/payment -> Escalate directly to admin without guessing bill details",
                "branch": branch,
                "intent": intent,
                "already_covered": covered,
            }

    # 3. Check order closing ONLY when admin hasn't already sent an order summary/bill
    # Use ONLY customer messages after the latest human/bot reply AND within 2h of last_cust so historical addresses never trigger false HANDOFF_ORDER.
    if not covered.get("admin_billed") and conv_meta.get("status") != "WON":
        last_reply_idx = -1
        for i, m in enumerate(active_msgs):
            if m.get("sender_role") in ("admin", "bot") and not is_auto_ad_greeting_text(
                m.get("text") or "",
                active_msgs[i - 1].get("text") or "" if i > 0 else "",
            ):
                last_reply_idx = i
        recent_order_msgs = [
            m for m in active_msgs[last_reply_idx + 1 :]
            if m.get("sender_role") == "customer"
            and not any(mk in (m.get("text") or "") for mk in SYSTEM_ORDER_MARKERS)
            and (not last_cust_dt or not parse_iso_dt(m.get("created_at")) or (last_cust_dt - parse_iso_dt(m.get("created_at"))).total_seconds() <= 2 * 3600)
        ]
        recent_cust_3 = " ".join((m.get("text") or "") for m in recent_order_msgs[-4:])
        has_phone = bool(PHONE_RE.search(recent_cust_3))
        addr_hits = sum(1 for h in ADDRESS_HINTS if h in recent_cust_3)
        if (has_phone and addr_hits >= 1) or any(k in last_cust_text for k in ["โอนแล้ว", "ส่งสลิป", "โอนเรียบร้อย"]):
            return {
                "decision": "HANDOFF_ORDER",
                "reason": "Customer provided phone/address or transfer confirmation -> Notify Telegram & pause auto-nag",
                "branch": branch,
                "intent": intent,
                "already_covered": covered,
            }

    # 3b. Facebook Payment checkout notification without full address -> escalate to admin to verify slip/close bill
    for pat in PAYMENT_EVENT_PATTERNS:
        if re.search(pat, last_cust_text, re.IGNORECASE):
            return {
                "decision": "HANDOFF_ESCALATE",
                "reason": f"Payment confirmation event ('{pat}') -> Escalate to Telegram human admin",
                "branch": branch,
                "intent": intent,
                "already_covered": covered,
            }

    # 4. Prevent spamming beyond max_followups or when human admin took over
    if is_followup:
        if covered.get("sent_no_size"):
            return {
                "decision": "BLOCK",
                "end_conversation": True,
                "reason": "Customer waist exceeds max 4XL size -> Stop follow-ups cleanly",
                "branch": branch,
                "intent": intent,
                "already_covered": covered,
            }
        if conv_meta.get("status") in ("HANDOFF", "HANDOFF_ALERTED", "HANDOFF_CRITICAL", "HANDOFF_UNREACHABLE", "WON", "CLOSED_GRACEFULLY"):
            return {
                "decision": "BLOCK",
                "reason": f"Thread handed off or closed (status={conv_meta.get('status')})",
                "branch": branch,
                "intent": intent,
                "already_covered": covered,
            }
        stage = int(conv_meta.get("followup_stage") or 0)
        soft_pause_cues = ["ยังไม่รีบ", "ยังไม่รีบร้อน", "รอเงิน", "ขอตัดสินใจ", "เดี๋ยวแวะ", "วันหลัง", "มีโอกาสจะแวะ", "กลับโคราช", "ใส่ไม่ได้", "ไว้โอกาสหน้า"]
        if stage >= 1 and any(k in all_cust_text for k in soft_pause_cues):
            return {
                "decision": "BLOCK",
                "end_conversation": True,
                "reason": "Customer requested no rush / deferred visit -> Stop follow-ups respectfully",
                "branch": branch,
                "intent": intent,
                "already_covered": covered,
            }
        if stage >= max_followups:
            return {
                "decision": "BLOCK",
                "end_conversation": True,
                "reason": f"Reached max_auto_followups ({max_followups})",
                "branch": branch,
                "intent": intent,
                "already_covered": covered,
            }
    else:
        # Instant reply: NEVER hide from human admins — only block if the BOT itself already sent the latest message
        if messages and messages[-1].get("sender_role") == "bot":
            return {
                "decision": "BLOCK",
                "reason": "Last message is already from bot (prevent duplicate loop)",
                "branch": branch,
                "intent": intent,
                "already_covered": covered,
            }

    return {
        "decision": "SEND",
        "reason": "Passed all Grill Guardrails (inside 24h window, no rejection, non-repetitive context ready)",
        "branch": branch,
        "intent": intent,
        "already_covered": covered,
    }
