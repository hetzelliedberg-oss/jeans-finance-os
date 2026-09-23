import os
import sys
import re
import asyncio
import threading
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.types import Channel, Chat
from telethon.errors import SessionPasswordNeededError

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SESSION_PATH = os.path.join(BASE_DIR, "data", "telethon_user")

# Standard Telegram client credentials (can be overridden via settings)
DEFAULT_API_ID = 2040
DEFAULT_API_HASH = "b18441a1ff607e10a989891a5462e627"

from backend.database import get_settings, update_setting, get_sku_cost_map, get_db_connection
from backend.parser import parse_order_message
from backend.order_importer import save_order_to_db


class TelethonManager:
    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self.client: Optional[TelegramClient] = None
        self.is_connected = False
        self.phone_code_hash = ""
        self.phone_number = ""
        self.worker_thread = threading.Thread(target=self._run_loop, daemon=True)
        self.worker_thread.start()

    def _run_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def _get_credentials(self):
        settings = get_settings()
        api_id_val = settings.get("TELEGRAM_API_ID", "").strip()
        api_hash_val = settings.get("TELEGRAM_API_HASH", "").strip()

        api_id = int(api_id_val) if api_id_val and api_id_val.isdigit() else DEFAULT_API_ID
        api_hash = api_hash_val if api_hash_val else DEFAULT_API_HASH
        return api_id, api_hash

    async def _ensure_client(self):
        if self.client is None:
            api_id, api_hash = self._get_credentials()
            settings = get_settings()
            string_session = settings.get("TELETHON_STRING_SESSION", "").strip()
            if string_session:
                self.client = TelegramClient(StringSession(string_session), api_id, api_hash, loop=self.loop)
            elif os.path.exists(SESSION_PATH + ".session"):
                self.client = TelegramClient(SESSION_PATH, api_id, api_hash, loop=self.loop)
            else:
                self.client = TelegramClient(StringSession(""), api_id, api_hash, loop=self.loop)
        if not self.client.is_connected():
            await self.client.connect()

    def get_status(self) -> Dict[str, Any]:
        """Check if client is currently logged in"""
        async def _check():
            try:
                await self._ensure_client()
                is_auth = await self.client.is_user_authorized()
                user_info = {}
                if is_auth:
                    me = await self.client.get_me()
                    user_info = {
                        "id": me.id,
                        "first_name": me.first_name,
                        "username": me.username or "",
                        "phone": me.phone or ""
                    }
                return {
                    "connected": True,
                    "authorized": is_auth,
                    "user": user_info,
                    "phone": self.phone_number,
                    "has_pending_otp": bool(self.phone_code_hash)
                }
            except Exception as e:
                return {"connected": False, "authorized": False, "error": str(e)}

        future = asyncio.run_coroutine_threadsafe(_check(), self.loop)
        return future.result(timeout=15)

    def request_login_code(self, phone: str) -> Dict[str, Any]:
        """Send OTP code to user's Telegram app/SMS with Thai number auto-formatting"""
        clean_phone = re.sub(r'[\s\-()]', '', phone.strip())
        if clean_phone.startswith("0"):
            clean_phone = "+66" + clean_phone[1:]
        elif not clean_phone.startswith("+"):
            clean_phone = "+" + clean_phone

        async def _req():
            try:
                await self._ensure_client()
                res = await self.client.send_code_request(clean_phone)
                self.phone_number = clean_phone
                self.phone_code_hash = res.phone_code_hash
                return {"success": True, "phone_code_hash": res.phone_code_hash, "phone": clean_phone}
            except Exception as e:
                return {"success": False, "error": str(e)}

        future = asyncio.run_coroutine_threadsafe(_req(), self.loop)
        return future.result(timeout=20)

    def verify_login_code(self, code: str, password: str = "") -> Dict[str, Any]:
        """Verify code and finish authorization"""
        clean_code = code.strip().replace(" ", "").replace("-", "")
        async def _verify():
            try:
                await self._ensure_client()
                try:
                    await self.client.sign_in(phone=self.phone_number, code=clean_code, phone_code_hash=self.phone_code_hash)
                except SessionPasswordNeededError:
                    if not password:
                        return {"success": False, "requires_password": True, "error": "บัญชีนี้เปิดใช้งาน 2FA กรุณากรอกรหัสผ่าน 2-Step Verification ในช่อง 2FA"}
                    await self.client.sign_in(password=password)

                me = await self.client.get_me()
                try:
                    self._register_listener()
                except Exception:
                    pass

                try:
                    session_str = self.client.session.save()
                    if session_str:
                        update_setting("TELETHON_STRING_SESSION", session_str)
                        print(f"[Telethon] Permanent StringSession saved to database ({len(session_str)} chars)", flush=True)
                except Exception as ex:
                    print(f"[Telethon] Warning: Could not save session string: {ex}", flush=True)

                user_info = {
                    "id": me.id,
                    "first_name": me.first_name,
                    "username": me.username or "",
                    "phone": me.phone or ""
                }
                return {"success": True, "user": user_info}
            except Exception as e:
                return {"success": False, "error": str(e)}

        future = asyncio.run_coroutine_threadsafe(_verify(), self.loop)
        return future.result(timeout=25)

    def list_dialogs(self) -> List[Dict[str, Any]]:
        """List groups that user belongs to"""
        async def _dialogs():
            try:
                await self._ensure_client()
                if not await self.client.is_user_authorized():
                    return []
                dialogs = await self.client.get_dialogs(limit=50)
                results = []
                for d in dialogs:
                    if d.is_group or d.is_channel:
                        results.append({
                            "id": d.id,
                            "title": d.title,
                            "is_online_group": "ออนไลน์" in d.title or "office" in d.title.lower(),
                            "is_kkc_group": "ขอนแก่น" in d.title or "kkc" in d.title.lower()
                        })
                return results
            except Exception as e:
                print("Error listing dialogs:", e)
                return []

        future = asyncio.run_coroutine_threadsafe(_dialogs(), self.loop)
        return future.result(timeout=20)

    def sync_group_history(self, chat_id: Any, channel: str, since_date: str = "2026-08-01") -> Dict[str, Any]:
        """
        Pull all past chat messages from chat_id since since_date,
        parse every order, and save to SQLite DB.
        """
        async def _sync():
            try:
                await self._ensure_client()
                if not await self.client.is_user_authorized():
                    return {"success": False, "error": "Not authorized"}

                since_dt = datetime.strptime(since_date, "%Y-%m-%d")
                sku_cost_map = get_sku_cost_map()

                scanned_count = 0
                imported_orders = 0
                live_msg_ids = set()

                async for msg in self.client.iter_messages(chat_id, limit=400):
                    tz_th = timezone(timedelta(hours=7))
                    dt_th = msg.date.astimezone(tz_th)
                    if dt_th.replace(tzinfo=None) < since_dt:
                        break

                    scanned_count += 1
                    text = msg.text or msg.message or ""
                    if not text.strip():
                        continue

                    # Extract sender name
                    sender_name = ""
                    try:
                        sender = await msg.get_sender()
                        if sender:
                            sender_name = getattr(sender, "first_name", "") or getattr(sender, "title", "")
                    except Exception:
                        pass

                    date_str = dt_th.strftime("%Y-%m-%d")
                    time_str = dt_th.strftime("%Y-%m-%d %H:%M:%S")
                    msg_id = str(msg.id)

                    raw_numbered = re.split(r"(?:^|\n)\s*\d+\.\s*\n", text)
                    if len(raw_numbered) > 1 and any("ลูกค้า" in b or "รหัส" in b or "สรุปออเดอร์" in b for b in raw_numbered):
                        blocks = [b.strip() for b in raw_numbered if b.strip()]
                        for b_idx, block_text in enumerate(blocks):
                            sub_msg_id = f"{msg_id}_{b_idx+1}"
                            live_msg_ids.add(sub_msg_id)
                            parsed = parse_order_message(
                                text=block_text,
                                source_channel=channel,
                                sku_cost_map=sku_cost_map,
                                sender_name=sender_name,
                                order_date=date_str,
                                order_time=time_str,
                                message_id=sub_msg_id
                            )
                            if parsed:
                                oid = save_order_to_db(parsed)
                                if oid:
                                    imported_orders += 1
                    else:
                        live_msg_ids.add(msg_id)
                        parsed = parse_order_message(
                            text=text,
                            source_channel=channel,
                            sku_cost_map=sku_cost_map,
                            sender_name=sender_name,
                            order_date=date_str,
                            order_time=time_str,
                            message_id=msg_id
                        )
                        if parsed:
                            oid = save_order_to_db(parsed)
                            if oid:
                                imported_orders += 1

                # Clean up deleted messages (orders in DB within date range that no longer exist in Telegram)
                deleted_orders = 0
                if live_msg_ids:
                    conn = get_db_connection()
                    cur = conn.cursor()
                    since_date_str = since_dt.strftime("%Y-%m-%d")
                    cur.execute(
                        "SELECT id, message_id FROM orders WHERE source_channel = ? AND order_date >= ?",
                        (channel, since_date_str)
                    )
                    db_rows = cur.fetchall()
                    for r in db_rows:
                        m_id = str(r["message_id"]) if r["message_id"] else ""
                        if m_id and m_id not in live_msg_ids:
                            cur.execute("DELETE FROM order_items WHERE order_id = ?", (r["id"],))
                            cur.execute("DELETE FROM orders WHERE id = ?", (r["id"],))
                            deleted_orders += 1
                    conn.commit()
                    conn.close()

                return {
                    "success": True,
                    "scanned_messages": scanned_count,
                    "imported_orders": imported_orders,
                    "deleted_orders": deleted_orders,
                    "channel": channel
                }

            except Exception as e:
                return {"success": False, "error": str(e)}

        future = asyncio.run_coroutine_threadsafe(_sync(), self.loop)
        return future.result(timeout=600)

    def _register_listener(self):
        """Register live event listener for forward streaming (new, edit, and delete)"""
        if self.client is None:
            return

        @self.client.on(events.NewMessage())
        @self.client.on(events.MessageEdited())
        async def _message_handler(event):
            try:
                chat = await event.get_chat()
                chat_title = getattr(chat, "title", "")
                text = event.message.message or ""
                if not text.strip():
                    return

                # Detect channel
                channel = "online"
                if "ขอนแก่น" in chat_title or "kkc" in chat_title.lower():
                    channel = "kkc"

                sender = await event.get_sender()
                sender_name = getattr(sender, "first_name", "") or ""

                tz_th = timezone(timedelta(hours=7))
                dt = event.message.date.astimezone(tz_th)
                sku_cost_map = get_sku_cost_map()

                parsed = parse_order_message(
                    text=text,
                    source_channel=channel,
                    sku_cost_map=sku_cost_map,
                    sender_name=sender_name,
                    order_date=dt.strftime("%Y-%m-%d"),
                    order_time=dt.strftime("%Y-%m-%d %H:%M:%S"),
                    message_id=str(event.message.id)
                )

                if parsed:
                    save_order_to_db(parsed)
            except Exception as ex:
                print("Live message/edit error:", ex)

        @self.client.on(events.MessageDeleted())
        async def _delete_handler(event):
            try:
                del_ids = [str(mid) for mid in event.deleted_ids]
                if del_ids:
                    conn = get_db_connection()
                    cur = conn.cursor()
                    placeholders = ",".join(["?"] * len(del_ids))
                    cur.execute(f"SELECT id FROM orders WHERE message_id IN ({placeholders})", del_ids)
                    to_delete = cur.fetchall()
                    for r in to_delete:
                        cur.execute("DELETE FROM order_items WHERE order_id = ?", (r["id"],))
                        cur.execute("DELETE FROM orders WHERE id = ?", (r["id"],))
                    conn.commit()
                    conn.close()
                    print(f"Live delete: removed {len(to_delete)} orders from DB")
            except Exception as ex:
                print("Live delete error:", ex)


telethon_manager = TelethonManager()
