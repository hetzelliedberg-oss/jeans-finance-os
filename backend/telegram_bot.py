import os
import re
import time
import threading
import requests
import json
from datetime import datetime
from typing import Optional, Dict, Any
from backend.database import get_settings, get_sku_cost_map
from backend.parser import parse_order_message
from backend.order_importer import save_order_to_db

class TelegramBotWorker:
    def __init__(self):
        self.is_running = False
        self.last_update_id = 0
        self.thread: Optional[threading.Thread] = None

    def start(self):
        if self.is_running:
            return
        self.is_running = True
        self.thread = threading.Thread(target=self._poll_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.is_running = False

    def _poll_loop(self):
        while self.is_running:
            try:
                settings = get_settings()
                token = settings.get("TELEGRAM_BOT_TOKEN", "").strip()
                if not token:
                    time.sleep(5)
                    continue

                online_chat_id = settings.get("TELEGRAM_ONLINE_CHAT_ID", "").strip()
                kkc_chat_id = settings.get("TELEGRAM_KKC_CHAT_ID", "").strip()

                url = f"https://api.telegram.org/bot{token}/getUpdates"
                params = {"offset": self.last_update_id + 1, "timeout": 15}

                res = requests.get(url, params=params, timeout=20)
                import json as _json
                data = _json.loads(res.content.decode('utf-8'))

                if not data.get("ok"):
                    time.sleep(5)
                    continue

                sku_cost_map = get_sku_cost_map()

                for update in data.get("result", []):
                    self.last_update_id = max(self.last_update_id, update.get("update_id", 0))

                    msg = update.get("message") or update.get("channel_post")
                    if not msg:
                        continue

                    text = msg.get("text", "") or msg.get("caption", "")
                    if not text:
                        continue

                    chat = msg.get("chat", {})
                    chat_id = str(chat.get("id", ""))
                    chat_title = chat.get("title", "")
                    sender = msg.get("from", {}).get("first_name", "") or msg.get("sender_chat", {}).get("title", "")
                    msg_id = str(msg.get("message_id", ""))
                    date_ts = msg.get("date", int(time.time()))
                    dt = datetime.fromtimestamp(date_ts)
                    order_date = dt.strftime("%Y-%m-%d")
                    order_time = dt.strftime("%Y-%m-%d %H:%M:%S")

                    # Identify channel & auto-register chat ID if matched
                    channel = "online"
                    is_kkc_group = (
                        (kkc_chat_id and chat_id == kkc_chat_id) or
                        "ขอนแก่น" in chat_title or
                        "kkc" in chat_title.lower() or
                        "หน้าร้าน" in chat_title
                    )
                    is_online_group = (
                        (online_chat_id and chat_id == online_chat_id) or
                        "ออนไลน์" in chat_title or
                        "online" in chat_title.lower() or
                        "ออฟฟิต" in chat_title or
                        "ออฟฟิศ" in chat_title or
                        "office" in chat_title.lower()
                    )

                    if is_kkc_group:
                        channel = "kkc"
                        if not kkc_chat_id or kkc_chat_id != chat_id:
                            from backend.database import update_setting
                            update_setting("TELEGRAM_KKC_CHAT_ID", chat_id)
                            kkc_chat_id = chat_id
                            print(f"[Telegram Bot] Auto-registered KKC chat_id={chat_id} ('{chat_title}')", flush=True)
                    elif is_online_group:
                        channel = "online"
                        if not online_chat_id or online_chat_id != chat_id:
                            from backend.database import update_setting
                            update_setting("TELEGRAM_ONLINE_CHAT_ID", chat_id)
                            online_chat_id = chat_id
                            print(f"[Telegram Bot] Auto-registered ONLINE chat_id={chat_id} ('{chat_title}')", flush=True)
                    else:
                        # Unknown group -> treat as online, auto-register if ONLINE_CHAT_ID not set yet
                        channel = "online"
                        print(f"[Telegram Bot] Unknown group '{chat_title}' ({chat_id}) -> routed as ONLINE", flush=True)
                        if not online_chat_id:
                            from backend.database import update_setting
                            update_setting("TELEGRAM_ONLINE_CHAT_ID", chat_id)
                            online_chat_id = chat_id
                            print(f"[Telegram Bot] Auto-registered ONLINE chat_id={chat_id} ('{chat_title}') [unknown group]", flush=True)

                    print(f"[Telegram Bot] New message received: id={msg_id}, sender='{sender}', chat='{chat_title}' ({chat_id}), channel={channel}", flush=True)

                    # Check if the message contains multiple numbered order blocks (e.g. 1. \n ลูกค้า : ... \n 2. \n ลูกค้า : ...)
                    raw_numbered = re.split(r"(?:^|\n)\s*\d+\.\s*\n", text)
                    if len(raw_numbered) > 1 and any("ลูกค้า" in b or "รหัส" in b for b in raw_numbered):
                        blocks = [b.strip() for b in raw_numbered if b.strip()]
                        for b_idx, block_text in enumerate(blocks):
                            sub_msg_id = f"{msg_id}_{b_idx+1}"
                            parsed = parse_order_message(
                                text=block_text,
                                source_channel=channel,
                                sku_cost_map=sku_cost_map,
                                sender_name=sender,
                                order_date=order_date,
                                order_time=order_time,
                                message_id=sub_msg_id
                            )
                            if parsed:
                                oid = save_order_to_db(parsed)
                                print(f"[Telegram Bot] SAVED MULTI-ORDER #{oid}: date={parsed.get('order_date')}, sales={parsed.get('total_sales')}, pieces={parsed.get('total_pieces')}", flush=True)
                    else:
                        parsed = parse_order_message(
                            text=text,
                            source_channel=channel,
                            sku_cost_map=sku_cost_map,
                            sender_name=sender,
                            order_date=order_date,
                            order_time=order_time,
                            message_id=msg_id
                        )
                        if parsed:
                            oid = save_order_to_db(parsed)
                            print(f"[Telegram Bot] SAVED ORDER #{oid}: date={parsed.get('order_date')}, sales={parsed.get('total_sales')}, pieces={parsed.get('total_pieces')}", flush=True)
                        else:
                            print(f"[Telegram Bot] Skipped non-order text: {text[:50]!r}", flush=True)

            except Exception as ex:
                print(f"[Telegram Bot] Error in poll loop: {ex}", flush=True)
                time.sleep(5)

            time.sleep(1)


telegram_bot_instance = TelegramBotWorker()
