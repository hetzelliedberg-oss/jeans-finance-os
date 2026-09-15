import re
import unicodedata
from typing import Dict, List, Any, Optional

def normalize_sku(raw_sku: str) -> str:
    """Normalize SKU string, e.g. 'xrp 67' -> 'XRP67', 'ar-01' -> 'AR01', 'AR23 ขาว' -> 'AR23ขาว'"""
    if not raw_sku:
        return ""
    clean = re.sub(r"[\s\-_]+", "", raw_sku).upper()
    # Handle Thai suffix like ขาว
    if "ขาว" in raw_sku:
        clean = clean.replace("ขาว", "") + "ขาว"
    return clean


def extract_admin_name(text: str, default_sender: str = "") -> str:
    """Extract admin name from text or fallback to telegram sender name"""
    patterns = [
        r"(?:แอดมิน|admin|Admin|ผู้ขาย|พนักงาน|น้อง)\s*[:=]?\s*([ก-๙a-zA-Z0-9]+)",
        r"#([ก-๙a-zA-Z0-9]+)",
        r"\[([ก-๙a-zA-Z0-9]+)\]",
        r"\(([ก-๙a-zA-Z0-9]+)\)$",
        r"แอดมิน([ก-๙a-zA-Z0-9]+)"
    ]
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            name = m.group(1).strip()
            if name.lower() not in ["jeans", "around", "group", "bot"]:
                return name
    if default_sender and default_sender.strip():
        return default_sender.strip()
    return "แอดมินทั่วไป"


def extract_payment_and_amount(text: str) -> Dict[str, Any]:
    """Determine payment method and total amount paid/cod"""
    is_cod = bool(re.search(r"(ปลายทาง|เก็บปลายทาง|cod|เก็บเงินปลายทาง|ปลาย\s*ทาง)", text, re.IGNORECASE))
    is_cash = bool(re.search(r"(เงินสด|สด|cash)", text, re.IGNORECASE))
    
    payment_method = "ปลายทาง" if is_cod else ("เงินสด" if is_cash else "โอน")

    # Extract amount — try each payment keyword in order with flexible spacing
    amount = 0.0

    # Priority 1: Explicit marker like 'ปลายทาง : 1290', 'โอน :1,180', 'ยอด 490'
    p1 = re.search(
        r"(?:โอน|ปลายทาง|ยอด|ยอดโอน|รวม|ราคา|บิล|เงินสด|สด)"
        r"\s*[:=]?\s*([0-9,]+(?:\.\d{1,2})?)\s*(?:บาท|.-|b|baht)?",
        text, re.IGNORECASE
    )
    if p1:
        try:
            val_str = p1.group(1).replace(",", "")
            val = float(val_str)
            if 50 <= val <= 100000:
                amount = val
        except ValueError:
            pass

    # Priority 1b: If amount still 0, look line-by-line for "ปลายทาง : 1290" or "โอน : 1290"
    if amount == 0.0:
        for line in text.splitlines():
            line = line.strip()
            m = re.match(
                r"(?:ปลายทาง|โอน|ยอด|รวม|ราคา)\s*:\s*([0-9,]+(?:\.\d{1,2})?)",
                line, re.IGNORECASE
            )
            if m:
                try:
                    val = float(m.group(1).replace(",", ""))
                    if 50 <= val <= 100000:
                        amount = val
                        # Also update payment_method based on which keyword matched
                        if "ปลายทาง" in line:
                            payment_method = "ปลายทาง"
                            is_cod = True
                        break
                except ValueError:
                    pass

    # Priority 2: Any price-like number in text (e.g. 590, 690, 890, 1180, 1500)
    if amount == 0.0:
        prices = re.findall(r"\b([1-9]\d{2,4})\b", text)
        for p in reversed(prices):
            try:
                val = float(p)
                # Ignore common postcodes or year like 2024, 2025, 2026, 10110, etc.
                if 190 <= val <= 20000 and val not in [2024, 2025, 2026]:
                    amount = val
                    break
            except ValueError:
                pass

    cod_amount = amount if payment_method == "ปลายทาง" else 0.0
    transfer_amount = amount if payment_method != "ปลายทาง" else 0.0

    return {
        "payment_method": payment_method,
        "total_sales": amount,
        "cod_amount": cod_amount,
        "transfer_amount": transfer_amount
    }



def parse_order_items(text: str, sku_cost_map: Dict[str, float]) -> List[Dict[str, Any]]:
    """Extract individual items (SKU, Size, Color, Qty) from message text"""
    items = []

    # Regular expression for matching SKU like AR01, XRP67, AR-189, XRP 55, AR23ขาว
    sku_pattern = re.compile(r"\b(AR|XRP)[-_ ]?(\d+)([a-zA-Zก-๙]*)\b", re.IGNORECASE)
    size_pattern = re.compile(r"\b(2XL|3XL|4XL|XXL|XXXL|FS|FreeSize|ฟรีไซส์|[SMLX]{1,3}|2[4-9]|3[0-9]|4[0-4])\b", re.IGNORECASE)
    size_word_pattern = re.compile(r"(?:ไซส์|size|เอว)\s*[:=]?\s*([0-9a-zA-Z]+)", re.IGNORECASE)
    color_pattern = re.compile(r"(ยีนส์เข้ม|ยีนส์อ่อน|ยีนส์ฟอก|ยีนส์กลาง|ยีนส์ดำ|สีขาว|สียีนส์|สีดำ|ขาว|ดำ|สนิม|มิดไนท์|เข้ม|อ่อน|ฟอก|เทา)", re.IGNORECASE)

    # Find all SKU matches and their spans
    all_sku_matches = list(sku_pattern.finditer(text))
    if not all_sku_matches:
        # Check if known SKUs are in text
        for known_sku in sorted(sku_cost_map.keys(), key=len, reverse=True):
            if known_sku in text.upper():
                cost = sku_cost_map.get(known_sku, 0.0)
                items.append({
                    "sku": known_sku,
                    "size": "",
                    "color": "",
                    "quantity": 1,
                    "unit_cost": cost,
                    "total_cost": cost
                })
                break
        return items

    for i, sm in enumerate(all_sku_matches):
        prefix = sm.group(1).upper()
        num = sm.group(2)
        suffix = sm.group(3) or ""
        raw_matched = f"{prefix}{num}{suffix}"
        sku = normalize_sku(raw_matched)

        # Segment of text belonging to this SKU: from this match start to next match start (or line break/end)
        start_idx = sm.start()
        end_idx = all_sku_matches[i + 1].start() if i + 1 < len(all_sku_matches) else len(text)
        segment = text[start_idx:end_idx]

        unit_cost = sku_cost_map.get(sku, 0.0)
        if unit_cost == 0.0 and sku not in sku_cost_map:
            base_sku = f"{prefix}{num}"
            if base_sku in sku_cost_map:
                sku = base_sku
                unit_cost = sku_cost_map.get(sku, 0.0)

        # Quantity in this segment
        qty = 1
        qty_match = re.search(r"(\d+)\s*(?:ตัว|ชิ้น|ea|pcs)", segment)
        if not qty_match:
            qty_match = re.search(r"(?:=|\*|x)\s*(\d+)", segment)
        if qty_match:
            try:
                parsed_qty = int(qty_match.group(1))
                if 1 <= parsed_qty <= 500:
                    qty = parsed_qty
            except ValueError:
                pass

        # Size in this segment
        size = ""
        sz_w = size_word_pattern.search(segment)
        if sz_w:
            size = sz_w.group(1).upper()
        else:
            sz_m = size_pattern.search(segment)
            if sz_m:
                size = sz_m.group(1).upper()

        # Color in this segment
        color = ""
        col_m = color_pattern.search(segment)
        if col_m:
            color = col_m.group(1)

        items.append({
            "sku": sku,
            "size": size,
            "color": color,
            "quantity": qty,
            "unit_cost": unit_cost,
            "total_cost": unit_cost * qty
        })

    return items


def parse_storefront_closing_message(text: str, sku_cost_map: Dict[str, float], default_date: str = "") -> Optional[Dict[str, Any]]:
    """
    Check if message is a daily storefront summary report (e.g. from Central Khon Kaen group).
    e.g.:
    สรุปยอดขาย 12 ก.ย.
    เงินสด 2,350
    โอน 4,330
    รวม 6,690
    จำนวน 8 ตัว
    """
    t = text.strip()
    is_closing = bool(re.search(r'(สรุปยอด|ยอดขาย|ปิดยอด|รายงานยอด|ยอดประจำวัน|ยอดหน้าร้าน|ปิดกะ|ยอดกะ|สรุปกะ)', t, re.IGNORECASE))
    has_money = bool(re.search(r'(สด|เงินสด|โอน|รวม|ยอด)', t) and re.search(r'\d+', t))
    if not (is_closing or (has_money and re.search(r'(ตัว|ชิ้น|คน|บิล|บาท)', t))):
        return None

    # Extract date if present in text
    date_val = None
    m_d = re.search(r'(\d{1,2})[\s\-_/]+([a-zA-Zก-๙]+)(?:[\s\-_/]+(\d{2,4}))?', t)
    if m_d:
        try:
            from backend.onedrive_engine import parse_date_str
            date_val = parse_date_str(m_d.group(0))
        except Exception:
            pass

    # Extract Cash
    cash = 0.0
    m_cash = re.search(r'(?:เงินสด|สด)\s*[:=]?\s*([0-9,]+(?:\.\d{1,2})?)', t)
    if m_cash:
        try:
            cash = float(m_cash.group(1).replace(",", ""))
        except ValueError:
            pass

    # Extract Transfer
    transfer = 0.0
    m_tr = re.search(r'(?:โอน|ยอดโอน)\s*[:=]?\s*([0-9,]+(?:\.\d{1,2})?)', t)
    if m_tr:
        try:
            transfer = float(m_tr.group(1).replace(",", ""))
        except ValueError:
            pass

    # Extract Total Sales
    total_sales = cash + transfer
    if total_sales == 0.0:
        m_tot = re.search(r'(?:รวม|ยอดรวม|ยอดขายรวม|ยอด)\s*[:=]?\s*([0-9,]+(?:\.\d{1,2})?)', t)
        if m_tot:
            try:
                total_sales = float(m_tot.group(1).replace(",", ""))
            except ValueError:
                pass

    if total_sales == 0.0:
        return None

    # Extract pieces
    pieces = 1
    m_pcs = re.search(r'(\d+)\s*(?:ตัว|ชิ้น)', t)
    if m_pcs:
        try:
            pieces = int(m_pcs.group(1))
        except ValueError:
            pass

    # Average cost
    avg_cost = sum(sku_cost_map.values()) / max(len(sku_cost_map), 1) if sku_cost_map else 456.83
    cogs_total = round(pieces * avg_cost, 2)

    return {
        "date": date_val or default_date,
        "total_sales": total_sales,
        "transfer_amount": transfer if transfer > 0 else total_sales,
        "cod_amount": cash,
        "payment_method": "เงินสด" if cash > 0 and transfer == 0 else "โอน",
        "total_pieces": pieces,
        "cogs_total": cogs_total,
        "items": [{
            "sku": "KKC_STORE",
            "size": "ALL",
            "color": "",
            "quantity": pieces,
            "unit_cost": avg_cost,
            "total_cost": cogs_total
        }]
    }


def parse_structured_storefront_order(text: str, sku_cost_map: Dict[str, float], default_date: str = "") -> Optional[Dict[str, Any]]:
    """
    Parse staff Telegram order format:
    ลูกค้า : เดินเข้าหน้าร้าน / เพจ FB
    วันที่ : 12/9/69
    รหัสสินค้า : AR37 (or AR18/ XRP67,ฟ้า)
    ไซส์ : XL (or 2XL/ XL)
    โอน : 0
    เงินสด : 1100
    """
    t = text.strip()
    if not ("รหัส" in t and ("โอน" in t or "เงินสด" in t)):
        return None

    # Date extraction (e.g. 12/9/69 -> 2026-09-12)
    m_d = re.search(r'วันที่\s*[:=]?\s*(\d{1,2})[\s\-_/]+(\d{1,2})[\s\-_/]+(\d{2,4})', t)
    date_str = ""
    if m_d:
        d, m, y = int(m_d.group(1)), int(m_d.group(2)), int(m_d.group(3))
        if y < 100:
            y = 2000 + (y - 43) if y >= 50 else 2000 + y
        date_str = f"{y:04d}-{m:02d}-{d:02d}"
    elif default_date:
        date_str = default_date

    # Transfer amount
    m_tr = re.search(r'โอน\s*[:=]?\s*([0-9,]+(?:\.\d{1,2})?)', t)
    transfer = float(m_tr.group(1).replace(",", "")) if m_tr else 0.0

    # Cash amount
    m_cash = re.search(r'(?:เงินสด|สด)\s*[:=]?\s*([0-9,]+(?:\.\d{1,2})?)', t)
    cash = float(m_cash.group(1).replace(",", "")) if m_cash else 0.0

    total_sales = transfer + cash

    # Customer
    m_cust = re.search(r'ลูกค้า\s*[:=]?\s*(.+)', t)
    cust = m_cust.group(1).strip() if m_cust else "ลูกค้าหน้าร้าน"

    # SKU & Size lines
    m_sku = re.search(r'รหัส(?:สินค้า)?\s*[:=]?\s*(.+)', t)
    sku_line = m_sku.group(1).strip() if m_sku else ""

    m_sz = re.search(r'ไซส์\s*[:=]?\s*(.+)', t)
    sz_line = m_sz.group(1).strip() if m_sz else ""

    if not sku_line:
        return None

    raw_skus = [s.strip() for s in re.split(r'[/]\s*(?=[A-Za-z0-9ก-๙])', sku_line) if s.strip()]
    raw_sizes = [s.strip() for s in re.split(r'[/]\s*', sz_line) if s.strip()]

    items = []
    for idx, s in enumerate(raw_skus):
        # Extract color if present
        color = ""
        sku_clean = s
        if "," in s:
            parts = s.split(",")
            sku_clean = parts[0].strip()
            color = parts[1].strip()
        sku_norm = normalize_sku(sku_clean)
        sz = raw_sizes[idx] if idx < len(raw_sizes) else (raw_sizes[0] if raw_sizes else "Free")
        cost = sku_cost_map.get(sku_norm, 0.0)
        if cost == 0.0:
            m_base = re.search(r'(AR\d+|XRP\d+)', sku_norm)
            cost = sku_cost_map.get(m_base.group(1), 456.83) if m_base else 456.83
        items.append({
            "sku": sku_norm,
            "size": sz,
            "color": color,
            "quantity": 1,
            "unit_cost": cost,
            "total_cost": cost
        })

    if not items:
        return None

    total_pieces = len(items)
    cogs_total = sum(it["total_cost"] for it in items)

    # Determine payment method
    if cash > 0 and transfer == 0:
        pay_method = "เงินสด"
    elif transfer > 0 and cash == 0:
        pay_method = "โอน"
    else:
        pay_method = "โอน"

    return {
        "source_channel": "kkc",
        "sender_name": "หน้าร้านเซนทรัล KKC",
        "customer_name": cust,
        "order_date": date_str or datetime.now().strftime("%Y-%m-%d"),
        "order_time": f"{date_str or datetime.now().strftime('%Y-%m-%d')} 15:00:00",
        "raw_text": t,
        "total_pieces": total_pieces,
        "total_sales": total_sales,
        "payment_method": pay_method,
        "cod_amount": cash,
        "transfer_amount": transfer,
        "cogs_total": cogs_total,
        "commission_amount": 0.0,
        "items": items
    }


def parse_order_message(
    text: str,
    source_channel: str,
    sku_cost_map: Dict[str, float],
    sender_name: str = "",
    order_date: str = "",
    order_time: str = "",
    message_id: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Complete parser for an incoming Telegram order message or daily storefront summary.
    Returns structured Order dictionary or None if text is not an order.
    """
    if not text or not text.strip():
        return None

    # 1. Check if structured staff order format
    structured = parse_structured_storefront_order(text, sku_cost_map, order_date)
    if structured:
        structured["message_id"] = message_id
        if sender_name:
            structured["sender_name"] = sender_name
        if source_channel:
            structured["source_channel"] = source_channel
        return structured

    items = parse_order_items(text, sku_cost_map)
    if not items:
        # Check if it is a storefront daily closing summary message
        store_closing = parse_storefront_closing_message(text, sku_cost_map, order_date)
        if store_closing:
            items = store_closing["items"]
            admin_name = extract_admin_name(text, sender_name or "หน้าร้านเซนทรัล KKC")
            final_date = store_closing["date"] or order_date
            return {
                "source_channel": source_channel or "kkc",
                "message_id": message_id,
                "sender_name": admin_name,
                "order_date": final_date,
                "order_time": order_time or f"{final_date} 21:00:00",
                "raw_text": text.strip(),
                "total_pieces": store_closing["total_pieces"],
                "total_sales": store_closing["total_sales"],
                "payment_method": store_closing["payment_method"],
                "cod_amount": store_closing["cod_amount"],
                "transfer_amount": store_closing["transfer_amount"],
                "cogs_total": store_closing["cogs_total"],
                "commission_amount": 0.0,
                "items": items
            }
        return None

    admin_name = extract_admin_name(text, sender_name)
    payment_info = extract_payment_and_amount(text)

    total_pieces = sum(item["quantity"] for item in items)
    cogs_total = sum(item["total_cost"] for item in items)

    # Estimate sales if amount was 0 (e.g. retail price 590 per piece)
    sales = payment_info["total_sales"]
    if sales == 0.0:
        sales = total_pieces * 590.0
        if payment_info["payment_method"] == "ปลายทาง":
            payment_info["cod_amount"] = sales
        else:
            payment_info["transfer_amount"] = sales

    # Commission: 10 THB / piece for online admin
    commission = total_pieces * 10.0 if source_channel == "online" else 0.0

    return {
        "source_channel": source_channel,
        "message_id": message_id,
        "sender_name": admin_name,
        "order_date": order_date,
        "order_time": order_time,
        "raw_text": text.strip(),
        "total_pieces": total_pieces,
        "total_sales": sales,
        "payment_method": payment_info["payment_method"],
        "cod_amount": payment_info["cod_amount"],
        "transfer_amount": payment_info["transfer_amount"],
        "cogs_total": cogs_total,
        "commission_amount": commission,
        "items": items
    }
