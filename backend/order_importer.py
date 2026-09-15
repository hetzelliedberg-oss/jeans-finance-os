import os
import re
import json
from datetime import datetime, timedelta
import random
from typing import Dict, Any, List, Optional
from backend.database import get_db_connection, get_sku_cost_map
from backend.parser import parse_order_message, normalize_sku


def save_order_to_db(order_data: Dict[str, Any]) -> Optional[int]:
    """
    Save parsed order and its items to SQLite database.
    Prevents duplicates using (source_channel, message_id) if message_id exists.
    Returns inserted order ID or None.
    """
    if not order_data:
        return None

    conn = get_db_connection()
    cur = conn.cursor()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    channel = order_data.get("source_channel", "online")
    msg_id = order_data.get("message_id")
    order_date = order_data.get("order_date") or datetime.now().strftime("%Y-%m-%d")
    order_time = order_data.get("order_time") or f"{order_date} 12:00:00"

    # Check duplicate
    if msg_id:
        cur.execute("SELECT id FROM orders WHERE source_channel = ? AND message_id = ?", (channel, str(msg_id)))
        existing = cur.fetchone()
        if existing:
            conn.close()
            return existing["id"]

    cur.execute("""
        INSERT INTO orders (
            source_channel, message_id, sender_name, order_date, order_time,
            raw_text, total_pieces, total_sales, payment_method, cod_amount,
            transfer_amount, cogs_total, commission_amount, status, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'completed', ?)
    """, (
        channel,
        str(msg_id) if msg_id else None,
        order_data.get("sender_name", "แอดมินทั่วไป"),
        order_date,
        order_time,
        order_data.get("raw_text", ""),
        order_data.get("total_pieces", 1),
        order_data.get("total_sales", 0.0),
        order_data.get("payment_method", "โอน"),
        order_data.get("cod_amount", 0.0),
        order_data.get("transfer_amount", 0.0),
        order_data.get("cogs_total", 0.0),
        order_data.get("commission_amount", 0.0),
        now_str
    ))

    order_id = cur.lastrowid

    # Insert items
    for itm in order_data.get("items", []):
        cur.execute("""
            INSERT INTO order_items (
                order_id, sku, size, color, quantity, unit_cost, total_cost
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            order_id,
            itm.get("sku", ""),
            itm.get("size", ""),
            itm.get("color", ""),
            itm.get("quantity", 1),
            itm.get("unit_cost", 0.0),
            itm.get("total_cost", 0.0)
        ))

    conn.commit()
    conn.close()
    return order_id


def import_telegram_export_json(file_content: str, default_channel: str = "online") -> Dict[str, Any]:
    """
    Import chat history from Telegram Desktop export JSON format ('result.json').
    """
    try:
        data = json.loads(file_content)
    except Exception as e:
        return {"success": False, "error": f"Invalid JSON format: {str(e)}"}

    group_name = data.get("name", "")
    channel = "kkc" if ("ขอนแก่น" in group_name or "kkc" in group_name.lower()) else default_channel
    messages = data.get("messages", [])

    sku_cost_map = get_sku_cost_map()
    imported_count = 0
    skipped_count = 0

    for msg in messages:
        if msg.get("type") != "message":
            continue

        raw_text_val = msg.get("text", "")
        # Handle list of text entities in Telegram JSON
        if isinstance(raw_text_val, list):
            parts = []
            for part in raw_text_val:
                if isinstance(part, str):
                    parts.append(part)
                elif isinstance(part, dict) and "text" in part:
                    parts.append(part["text"])
            text = "".join(parts)
        else:
            text = str(raw_text_val)

        if not text.strip():
            continue

        msg_date_raw = msg.get("date", "") # "2026-08-15T14:23:10"
        order_date = ""
        order_time = ""
        if msg_date_raw:
            try:
                dt = datetime.fromisoformat(msg_date_raw.replace("Z", ""))
                order_date = dt.strftime("%Y-%m-%d")
                order_time = dt.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                pass

        sender = msg.get("from", "")
        msg_id = msg.get("id")

        parsed = parse_order_message(
            text=text,
            source_channel=channel,
            sku_cost_map=sku_cost_map,
            sender_name=sender,
            order_date=order_date,
            order_time=order_time,
            message_id=str(msg_id)
        )

        if parsed:
            save_order_to_db(parsed)
            imported_count += 1
        else:
            skipped_count += 1

    return {
        "success": True,
        "group_name": group_name,
        "channel": channel,
        "total_messages": len(messages),
        "imported_orders": imported_count,
        "skipped_non_orders": skipped_count
    }


def import_pasted_text(raw_text: str, channel: str = "online", default_date: str = "") -> Dict[str, Any]:
    """
    Parse blocks of text pasted directly from Telegram chat.
    Can split multiple orders by double newlines or admin separators.
    """
    if not raw_text or not raw_text.strip():
        return {"success": False, "error": "Empty text provided"}

    sku_cost_map = get_sku_cost_map()
    today_str = default_date or datetime.now().strftime("%Y-%m-%d")

    # Check if numbered list (e.g. 1.\nลูกค้า : ... 2.\nลูกค้า : ...)
    raw_numbered = re.split(r"(?:^|\n)\s*\d+\.\s*\n", raw_text)
    if len(raw_numbered) > 1 and any("ลูกค้า" in b or "รหัส" in b for b in raw_numbered):
        blocks = [b.strip() for b in raw_numbered if b.strip()]
    else:
        # Split by double newline or dashed delimiter or clear order boundary
        blocks = re.split(r"\n\s*\n|(?:\r?\n){2,}|(?:\n---+|\n===+)", raw_text)
    imported = 0
    parsed_orders = []

    for block in blocks:
        block_clean = block.strip()
        if not block_clean:
            continue

        parsed = parse_order_message(
            text=block_clean,
            source_channel=channel,
            sku_cost_map=sku_cost_map,
            sender_name="",
            order_date=today_str,
            order_time=f"{today_str} 12:00:00"
        )

        if parsed:
            oid = save_order_to_db(parsed)
            parsed["db_id"] = oid
            parsed_orders.append(parsed)
            imported += 1

    return {
        "success": True,
        "imported_orders": imported,
        "orders": parsed_orders
    }


def seed_realistic_sales_data(start_date: str = "2026-08-01", end_date: str = "2026-09-12"):
    """
    Seed realistic order data for August and September 2026 matching real-world sales volume
    for both 'online' (Jeans Around Online Office) and 'kkc' (Central Khon Kaen Storefront).
    """
    sku_cost_map = get_sku_cost_map()
    available_skus = [s for s, c in sku_cost_map.items() if c > 0]
    if not available_skus:
        available_skus = ["XRP67", "XRP55", "AR01", "AR02", "AR189", "XRP15", "AR23"]

    popular_skus = ["XRP67", "XRP55", "AR01", "AR02", "AR189", "AR23ขาว", "XRP14", "XRP65"]
    sizes = ["S", "M", "L", "XL", "28", "30", "32", "34", "36"]
    colors = ["ยีนส์เข้ม", "ยีนส์อ่อน", "ยีนส์สนิม", "ดำ", "ขาว", "ฟอกมิดไนท์"]
    admins = ["แอดมินฟ้า", "แอดมินหมวย", "แอดมินแนน", "แอดมินโบว์", "แอดมินวิว"]
    kkc_staff = ["หน้าร้านเซนทรัล KKC - น้องแอน", "หน้าร้านเซนทรัล KKC - น้องกิ๊ฟ"]

    s_dt = datetime.strptime(start_date, "%Y-%m-%d")
    e_dt = datetime.strptime(end_date, "%Y-%m-%d")
    delta = (e_dt - s_dt).days

    # Clear existing orders to avoid duplicate seeding
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM order_items")
    cur.execute("DELETE FROM orders")
    conn.commit()
    conn.close()

    total_online_orders = 0
    total_kkc_orders = 0

    for day_offset in range(delta + 1):
        curr_dt = s_dt + timedelta(days=day_offset)
        d_str = curr_dt.strftime("%Y-%m-%d")
        weekday = curr_dt.weekday()

        # 1. Generate Online Orders (15 to 35 orders per day)
        num_online = random.randint(18, 38)
        for i in range(num_online):
            hour = random.randint(9, 22)
            minute = random.randint(0, 59)
            time_str = f"{d_str} {hour:02d}:{minute:02d}:00"
            admin = random.choice(admins)

            # Pick 1-2 items
            num_items = 1 if random.random() < 0.75 else 2
            items = []
            for _ in range(num_items):
                sku = random.choice(popular_skus if random.random() < 0.7 else available_skus)
                size = random.choice(sizes)
                col = random.choice(colors)
                qty = 1 if random.random() < 0.9 else 2
                cost = sku_cost_map.get(sku, 450.0)
                items.append({
                    "sku": sku,
                    "size": size,
                    "color": col,
                    "quantity": qty,
                    "unit_cost": cost,
                    "total_cost": cost * qty
                })

            total_pcs = sum(it["quantity"] for it in items)
            # Retail price: 590 per piece, 2 pieces promo 1,090
            price = 590.0 if total_pcs == 1 else (1090.0 if total_pcs == 2 else total_pcs * 540.0)

            # Payment: 60% COD, 40% Transfer
            is_cod = random.random() < 0.60
            payment = "ปลายทาง" if is_cod else "โอน"
            cod_val = price if is_cod else 0.0
            trf_val = price if not is_cod else 0.0

            raw_txt = f"รหัส {items[0]['sku']} สี{items[0]['color']} ไซส์ {items[0]['size']} {items[0]['quantity']} ตัว\n{payment} {int(price)}\n{admin}"

            order_dict = {
                "source_channel": "online",
                "message_id": f"sim_on_{d_str}_{i+1}",
                "sender_name": admin.replace("แอดมิน", ""),
                "order_date": d_str,
                "order_time": time_str,
                "raw_text": raw_txt,
                "total_pieces": total_pcs,
                "total_sales": price,
                "payment_method": payment,
                "cod_amount": cod_val,
                "transfer_amount": trf_val,
                "cogs_total": sum(it["total_cost"] for it in items),
                "commission_amount": total_pcs * 10.0,
                "items": items
            }
            save_order_to_db(order_dict)
            total_online_orders += 1

        # 2. Generate KKC Storefront Orders (8 to 22 orders per day, weekends higher)
        num_kkc = random.randint(14, 25) if weekday in [4, 5, 6] else random.randint(6, 14)
        for i in range(num_kkc):
            hour = random.randint(11, 20)
            minute = random.randint(0, 59)
            time_str = f"{d_str} {hour:02d}:{minute:02d}:00"
            staff = random.choice(kkc_staff)

            sku = random.choice(popular_skus if random.random() < 0.7 else available_skus)
            size = random.choice(sizes)
            col = random.choice(colors)
            cost = sku_cost_map.get(sku, 450.0)
            items = [{
                "sku": sku,
                "size": size,
                "color": col,
                "quantity": 1,
                "unit_cost": cost,
                "total_cost": cost
            }]

            price = 690.0 if random.random() < 0.5 else 590.0
            raw_txt = f"สาขาเซนทรัล KKC บิล #{i+1}\n{sku} {col} ไซส์ {size} 1 ตัว\nยอดชำระ {int(price)} บาท\n{staff}"

            order_dict = {
                "source_channel": "kkc",
                "message_id": f"sim_kkc_{d_str}_{i+1}",
                "sender_name": staff,
                "order_date": d_str,
                "order_time": time_str,
                "raw_text": raw_txt,
                "total_pieces": 1,
                "total_sales": price,
                "payment_method": "โอน" if random.random() < 0.7 else "เงินสด",
                "cod_amount": 0.0,
                "transfer_amount": price,
                "cogs_total": cost,
                "commission_amount": 0.0,
                "items": items
            }
            save_order_to_db(order_dict)
            total_kkc_orders += 1

    return {
        "success": True,
        "total_days": delta + 1,
        "online_orders_seeded": total_online_orders,
        "kkc_orders_seeded": total_kkc_orders
    }


if __name__ == "__main__":
    print("Seed function disabled to enforce 100% Fact Data.")
