import os
import sys
import re
import asyncio
import sqlite3
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

# Ensure project root is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError
from backend.database import get_db_connection, get_settings, update_setting, get_sku_cost_map
from backend.parser import parse_order_message
from backend.order_importer import save_order_to_db

API_ID = 2040
API_HASH = "b18441a1ff607e10a989891a5462e627"
SESSION_PATH = os.path.join(BASE_DIR, "data", "telethon_user")

ONLINE_CHAT_ID = -4242902075
KKC_CHAT_ID = -5366638194

# Thailand timezone UTC+7
TZ_TH = timezone(timedelta(hours=7))


def get_telegram_client() -> TelegramClient:
    settings = get_settings()
    session_str = settings.get("TELETHON_STRING_SESSION", "").strip()
    if session_str:
        return TelegramClient(StringSession(session_str), API_ID, API_HASH)
    else:
        return TelegramClient(SESSION_PATH, API_ID, API_HASH)


async def check_authorization(client: TelegramClient) -> bool:
    await client.connect()
    is_auth = await client.is_user_authorized()
    return is_auth


async def request_code(client: TelegramClient, phone: str) -> str:
    clean_phone = re.sub(r'[\s\-()]', '', phone.strip())
    if clean_phone.startswith("0"):
        clean_phone = "+66" + clean_phone[1:]
    elif not clean_phone.startswith("+"):
        clean_phone = "+" + clean_phone

    await client.connect()
    res = await client.send_code_request(clean_phone)
    return res.phone_code_hash


async def verify_code(client: TelegramClient, phone: str, code: str, phone_code_hash: str, password: str = ""):
    clean_phone = re.sub(r'[\s\-()]', '', phone.strip())
    if clean_phone.startswith("0"):
        clean_phone = "+66" + clean_phone[1:]
    elif not clean_phone.startswith("+"):
        clean_phone = "+" + clean_phone

    await client.connect()
    try:
        await client.sign_in(phone=clean_phone, code=code.strip(), phone_code_hash=phone_code_hash)
    except SessionPasswordNeededError:
        if not password:
            raise ValueError("2FA Password is required for this account")
        await client.sign_in(password=password)

    session_str = client.session.save()
    if session_str:
        update_setting("TELETHON_STRING_SESSION", session_str)
        print(f"[Telethon] Permanent StringSession saved to database ({len(session_str)} chars)")


async def scan_and_audit_channel(
    client: TelegramClient,
    chat_id: int,
    channel_name: str,
    since_date: str = "2026-01-01",
    until_date: Optional[str] = None,
    progress_callback=None
) -> Dict[str, Any]:
    """
    Iterates through Telegram chat history from since_date until until_date,
    parses each message, and imports into the database.
    """
    await client.connect()
    if not await client.is_user_authorized():
        return {"success": False, "error": "Client not authorized"}

    since_dt = datetime.strptime(since_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    until_dt = (
        datetime.strptime(until_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        if until_date
        else datetime.now(timezone.utc)
    )

    sku_cost_map = get_sku_cost_map()
    scanned_messages = 0
    parsed_orders = 0
    imported_orders = 0
    skipped_duplicates = 0
    orders_by_month: Dict[str, int] = {}
    sales_by_month: Dict[str, float] = {}

    print(f"\n[Audit] Starting scan for {channel_name} (chat_id={chat_id}) since {since_date}...")

    # We iterate from newest to oldest
    async for msg in client.iter_messages(chat_id, limit=None):
        msg_date_utc = msg.date
        if msg_date_utc > until_dt:
            continue
        if msg_date_utc < since_dt:
            # Reached beyond since_date, finish
            print(f"[Audit] Reached messages before {since_date}. Stopping scan.")
            break

        scanned_messages += 1
        text = msg.text or msg.message or ""
        if not text.strip():
            continue

        # Convert timestamp to Thailand local time (UTC+7)
        msg_dt_th = msg_date_utc.astimezone(TZ_TH)
        date_str = msg_dt_th.strftime("%Y-%m-%d")
        time_str = msg_dt_th.strftime("%Y-%m-%d %H:%M:%S")
        month_str = date_str[:7]
        msg_id = str(msg.id)

        # Get sender name
        sender_name = ""
        try:
            sender = await msg.get_sender()
            if sender:
                sender_name = getattr(sender, "first_name", "") or getattr(sender, "title", "")
        except Exception:
            pass

        # Check if message contains multiple numbered orders (e.g. 1. ... 2. ...)
        raw_numbered = re.split(r"(?:^|\n)\s*\d+\.\s*\n", text)
        if len(raw_numbered) > 1 and any("ลูกค้า" in b or "รหัส" in b or "สรุปออเดอร์" in b for b in raw_numbered):
            blocks = [b.strip() for b in raw_numbered if b.strip()]
            for b_idx, block_text in enumerate(blocks):
                sub_msg_id = f"{msg_id}_{b_idx+1}"
                parsed = parse_order_message(
                    text=block_text,
                    source_channel=channel_name,
                    sku_cost_map=sku_cost_map,
                    sender_name=sender_name,
                    order_date=date_str,
                    order_time=time_str,
                    message_id=sub_msg_id
                )
                if parsed:
                    parsed_orders += 1
                    oid, is_new = save_order_to_db(parsed, return_is_new=True)
                    if is_new:
                        imported_orders += 1
                        orders_by_month[month_str] = orders_by_month.get(month_str, 0) + 1
                        sales_by_month[month_str] = sales_by_month.get(month_str, 0.0) + parsed.get("total_sales", 0.0)
                    else:
                        skipped_duplicates += 1
        else:
            parsed = parse_order_message(
                text=text,
                source_channel=channel_name,
                sku_cost_map=sku_cost_map,
                sender_name=sender_name,
                order_date=date_str,
                order_time=time_str,
                message_id=msg_id
            )
            if parsed:
                parsed_orders += 1
                oid, is_new = save_order_to_db(parsed, return_is_new=True)
                if is_new:
                    imported_orders += 1
                    orders_by_month[month_str] = orders_by_month.get(month_str, 0) + 1
                    sales_by_month[month_str] = sales_by_month.get(month_str, 0.0) + parsed.get("total_sales", 0.0)
                else:
                    skipped_duplicates += 1

        if scanned_messages % 200 == 0:
            print(f"[Audit] Scanned {scanned_messages} msgs | Found {parsed_orders} orders | Date: {date_str}")
            if progress_callback:
                progress_callback(scanned_messages, parsed_orders, date_str)

    print(f"\n[Audit Completed for {channel_name}]")
    print(f"Total Scanned Messages: {scanned_messages}")
    print(f"Total Parsed Orders: {parsed_orders}")
    print(f"Newly Imported Orders: {imported_orders}")
    print(f"Skipped Duplicates: {skipped_duplicates}")
    print("Breakdown by Month:")
    for m in sorted(orders_by_month.keys()):
        print(f"  Month {m}: {orders_by_month[m]} orders | {sales_by_month.get(m, 0.0):,.2f} THB")

    return {
        "success": True,
        "channel": channel_name,
        "scanned_messages": scanned_messages,
        "parsed_orders": parsed_orders,
        "imported_orders": imported_orders,
        "skipped_duplicates": skipped_duplicates,
        "orders_by_month": orders_by_month,
        "sales_by_month": sales_by_month
    }
