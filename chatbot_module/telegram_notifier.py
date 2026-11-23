"""Telegram notifier for Order Handoff, Escalations & Boss-Mode Admin DM Alerts."""

import html
import os
import time
import requests
from typing import Dict, List, Tuple

from db import get_settings, update_setting

# In-memory cooldown tracker: (psid, alert_type) -> last_sent_epoch
_ALERT_COOLDOWN: Dict[Tuple[str, str], float] = {}

_COOLDOWN_SECONDS: Dict[str, int] = {
    "NEW_CUSTOMER_MSG": 900,         # 15 min per customer so ongoing chat doesn't spam Office group
    "ADMIN_ASSIST_PHOTO": 900,       # 15 min
    "COMMENT_ALERT": 1800,           # 30 min
    "BOT_CANNOT_HANDLE": 3600,       # 60 min (max 1 per hour, never spam)
    "IMAGE_RECEIVED": 600,           # 10 min
    "UNBILLED_SALE_ALERT": 86400,    # 24 hours (fire once max, never spam every 30m)
    "ADMIN_SLOW_SLA_1M": 3600,       # 60 min (never spam every 5m)
    "ADMIN_SLOW_SLA": 3600,
    "ADMIN_SLOW_SLA_CRITICAL": 86400,# 24 hours (fire critical once max)
    "FRAUD_ALERT": 3600,             # 60 min per psid
}

# Only send private DMs to Mew / Am / Gift for alerts needing immediate human action
_DM_ALERT_TYPES = {
    "UNBILLED_SALE_ALERT",
    "BOT_CANNOT_HANDLE",
    "IMAGE_RECEIVED",
    "COMMENT_ALERT",
    "ADMIN_SLOW_SLA_1M",
    "ADMIN_SLOW_SLA",
    "ADMIN_SLOW_SLA_CRITICAL",
}


def clear_alert_cooldowns() -> None:
    """Clear in-memory Telegram alert cooldowns (used by tests)."""
    _ALERT_COOLDOWN.clear()


def _should_skip_cooldown(psid: str, alert_type: str) -> bool:
    ttl = _COOLDOWN_SECONDS.get(alert_type, 300)
    if ttl <= 0 or not psid:
        return False
    # Unify general chat pings (NEW_CUSTOMER_MSG + ADMIN_ASSIST_PHOTO) so 1 customer never fires both within 15m
    cooldown_bucket = "GENERAL_CHAT_PING" if alert_type in ("NEW_CUSTOMER_MSG", "ADMIN_ASSIST_PHOTO") else alert_type
    key = (psid, cooldown_bucket)
    now = time.monotonic()
    last = _ALERT_COOLDOWN.get(key)
    if last is not None and (now - last) < ttl:
        return True
    _ALERT_COOLDOWN[key] = now
    return False


_JUNK_ACK_SET = {
    ".", "..", "...", "👍", "👌", "❤️", "🙏", "😊", "จ้า", "จร้า", "ค่ะ", "คะ", "ครับ",
    "โอเค", "ok", "รับทราบ", "อืม", "ขอบคุณ", "ขอบคุณค่ะ", "ขอบคุณคะ", "ขอบคุณครับ",
    "[ส่งรูปภาพ/สติกเกอร์]",
}


def _is_junk_customer_msg(msg: str) -> bool:
    """Filter out single-dot/emoji/filler acknowledgements that waste admin attention."""
    clean = (msg or "").strip().lower().rstrip("!.?~ ")
    if not clean or clean in _JUNK_ACK_SET:
        return True
    if len(clean) <= 2 and not any(ch.isdigit() for ch in clean):
        return True
    return False


def _build_sharp_action_hint(msg: str, branch: str) -> str:
    low = (msg or "").lower()
    if any(k in low for k in ["เอว", "สะโพก", "หนัก", "สูง", "ไซส์", "ไซด์", "ขนาด"]):
        return "🎯 ลูกค้าให้สัดส่วน/ถามไซส์ — เช็กสต็อก/ปิดไซส์ให้ไว"
    if any(k in low for k in ["สี", "ลาย", "แบบ", "รูป", "ด้านหลัง", "ข้างหลัง", "ยาว"]):
        return "📸 ลูกค้าถามแบบ/สี/รูป — ส่งรูปรีวิวจริงช่วยปิด"
    if branch in ("KORAT", "KKC", "UDN") or any(k in low for k in ["สาขา", "หน้าร้าน", "พิกัด", "แวะ", "ลอง"]):
        return "🏬 ลูกค้าสายหน้าร้าน — นัดวันเข้าลอง/เก็บเบอร์โทร"
    if any(k in low for k in ["ราคา", "เท่าไหร่", "เท่าไร", "โปร", "ลด", "ปลายทาง", "โอน", "ส่งฟรี"]):
        return "💰 ลูกค้าถามราคา/โปร — ปิดออเดอร์/เสนอโปรคู่"
    return "⚡ รีบเข้าตอบ/ช่วยปิดการขายในแชท"


def _humanize_reason(reason: str) -> str:
    r = (reason or "").strip()
    if "#10" in r or "นอกช่วงเวลา" in r:
        return "ลูกค้าเม้น/เกิน 24 ชม. ของ Meta (ต้องเข้ากดตอบใน Inbox)"
    if "#551" in r or "ไม่สามารถติดต่อ" in r:
        return "Meta ยังไม่เปิดหน้าต่างข้อความ (เข้าเช็กใน Inbox)"
    if "scontent" in r or "http://" in r or "https://" in r:
        return "ลูกค้าส่งรูปภาพ/สลิปเข้ามา"
    return r[:60] or "ต้องให้แอดมินตรวจสอบ"


def _clean_last_msg(msg: str) -> str:
    txt = (msg or "").strip().replace("\n", " ")
    if "http://" in txt or "https://" in txt:
        if "scontent" in txt or "fbcdn" in txt or "รูปภาพ" in txt:
            return "[ส่งรูปภาพ/สลิปเข้ามา]"
    return txt[:70]


def _send_tg(bot_token: str, chat_id: str, text: str) -> bool:
    if not bot_token or not chat_id:
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": chat_id.strip(), "text": text, "parse_mode": "HTML", "disable_web_page_preview": True},
            timeout=10,
        )
        return r.status_code == 200
    except Exception as e:
        print(f"[TelegramNotifier] Error sending to {chat_id}: {e}")
        return False


def _send_tg_photo(bot_token: str, chat_id: str, photo_url: str, caption: str) -> bool:
    """Try sending the customer's photo directly in Telegram; fallback to clean text if CDN fetch fails."""
    if not bot_token or not chat_id:
        return False
    if photo_url:
        try:
            r = requests.post(
                f"https://api.telegram.org/bot{bot_token}/sendPhoto",
                json={
                    "chat_id": chat_id.strip(),
                    "photo": photo_url,
                    "caption": caption[:1024],
                    "parse_mode": "HTML",
                },
                timeout=12,
            )
            if r.status_code == 200:
                return True
        except Exception as e:
            print(f"[TelegramNotifier] sendPhoto failed for {chat_id}: {e}")
    return _send_tg(bot_token, chat_id, caption)


def sync_telegram_admins() -> int:
    """Auto-bind Mew / Am / Gift private chat IDs from Telegram /start updates."""
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not bot_token:
        return 0
    try:
        r = requests.get(f"https://api.telegram.org/bot{bot_token}/getUpdates?limit=100", timeout=8)
        if r.status_code != 200:
            return 0
        s = get_settings()
        keys = ["TELEGRAM_ADMIN_MEW_ID", "TELEGRAM_ADMIN_AM_ID", "TELEGRAM_ADMIN_GIFT_ID"]
        existing_ids = {(s.get(k) or os.getenv(k, "")).strip() for k in keys if (s.get(k) or os.getenv(k, "")).strip()}
        bound = 0
        for upd in r.json().get("result", []):
            msg = upd.get("message") or {}
            chat = msg.get("chat") or {}
            if chat.get("type") != "private":
                continue
            cid = str(chat.get("id", "")).strip()
            if not cid or cid in existing_ids:
                continue
            label = f"{chat.get('first_name','')} {chat.get('username','')} {msg.get('text','')}".lower()
            target_key = None
            if any(w in label for w in ("mew", "มิว")):
                target_key = "TELEGRAM_ADMIN_MEW_ID"
            elif any(w in label for w in ("am", "แอม")):
                target_key = "TELEGRAM_ADMIN_AM_ID"
            elif any(w in label for w in ("gift", "กีฟ", "กิ๊ฟ")):
                target_key = "TELEGRAM_ADMIN_GIFT_ID"
            else:
                target_key = next((k for k in keys if not (s.get(k) or os.getenv(k, "")).strip()), None)
            if target_key:
                update_setting(target_key, cid)
                existing_ids.add(cid)
                bound += 1
        return bound
    except Exception:
        return 0


def get_admin_dm_ids() -> List[str]:
    s = get_settings()
    ids = []
    for k in ("TELEGRAM_ADMIN_MEW_ID", "TELEGRAM_ADMIN_AM_ID", "TELEGRAM_ADMIN_GIFT_ID"):
        val = (s.get(k) or os.getenv(k, "")).strip()
        if val and val not in ids:
            ids.append(val)
    return ids


def notify_admins_boss_mode(
    branch: str,
    customer_name: str,
    psid: str,
    alert_type: str,
    last_message: str,
    reason: str,
    context_summary: str = "",
    ad_name: str = "",
    wait_minutes: int = 0,
    image_url: str = "",
) -> int:
    """Send deduplicated, context-rich Boss-tone Telegram alerts to Office ลพบุรี (and private DMs for urgent alerts)."""
    if alert_type == "NEW_CUSTOMER_MSG" and _is_junk_customer_msg(last_message):
        return 0
    if _should_skip_cooldown(psid, alert_type):
        return 0

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not bot_token:
        return 0

    if alert_type in _DM_ALERT_TYPES and len(get_admin_dm_ids()) < 3:
        sync_telegram_admins()

    safe_name = html.escape(customer_name or "ลูกค้า")
    safe_branch = html.escape(branch or "ONLINE")
    safe_last = html.escape(_clean_last_msg(last_message))
    safe_reason = html.escape(_humanize_reason(reason))

    inbox_url = f"https://business.facebook.com/latest/inbox/all?asset_id={os.getenv('FB_PAGE_ID', '359833590537243')}"

    if alert_type == "NEW_CUSTOMER_MSG":
        safe_ad = html.escape((ad_name or "เพจ")[:35])
        action_verb = "ทักเข้ามาใหม่" if context_summary == "NEW_CONV" else "ตอบแชทกลับมา"
        sharp_hint = _build_sharp_action_hint(last_message, branch)
        text = (
            f"📩 <b>{safe_name} ({safe_branch})</b> {action_verb} ({safe_ad})\n"
            f"💬 \"{safe_last}\"\n"
            f"{sharp_hint} (<a href=\"{inbox_url}\">เปิดแชทเพจ</a>)"
        )
    elif alert_type == "UNBILLED_SALE_ALERT":
        text = (
            f"🧾🔥 <b>{safe_name} ({safe_branch}) ขายได้แล้วแต่ยังไม่เปิดบิล!!</b>\n"
            f"💬 \"{safe_last}\"\n"
            f"👉 มิว/แอม/กิ๊ฟ รีบกดเปิดบิลในแชท + ส่งสรุปยอดเข้ากลุ่ม (<a href=\"{inbox_url}\">เปิดแชทเพจ</a>)"
        )
    elif alert_type == "COMMENT_ALERT":
        text = (
            f"💬 <b>{safe_name} ({safe_branch})</b> เม้นมา: \"{safe_last}\"\n"
            f"👉 กดเข้าไปตอบใน Inbox (<a href=\"{inbox_url}\">เปิดแชทเพจ</a>)"
        )
    elif alert_type == "IMAGE_RECEIVED":
        text = (
            f"🖼️ <b>{safe_name} ({safe_branch})</b> ส่งรูป/สลิปเข้ามา\n"
            f"👉 มิว/แอม/กิ๊ฟ ตรวจรูป/ปิดบิลในแชท (<a href=\"{inbox_url}\">เปิดแชทเพจ</a>)"
        )
    elif alert_type == "ADMIN_ASSIST_PHOTO":
        safe_ad = html.escape((ad_name or "เพจ")[:35])
        text = (
            f"📸 <b>{safe_name} ({safe_branch})</b> ทักจาก \"{safe_ad}\" — \"{safe_last}\"\n"
            f"👉 บอทตอบเบื้องต้นแล้ว ส่งรูปสินค้า/รีวิวจริงช่วยปิดในแชท (<a href=\"{inbox_url}\">เปิดแชทเพจ</a>)"
        )
    elif alert_type in ("ADMIN_SLOW_SLA_1M", "ADMIN_SLOW_SLA", "ADMIN_SLOW_SLA_CRITICAL"):
        icon = "🔥" if wait_minutes >= 7 else "⏰"
        text = (
            f"{icon} <b>{safe_name} ({safe_branch})</b> รอแอดมิน <b>{wait_minutes} นาที</b> — \"{safe_last}\"\n"
            f"👉 มิว/แอม/กิ๊ฟ เข้าตอบด่วน (<a href=\"{inbox_url}\">เปิดแชทเพจ</a>)"
        )
    elif alert_type == "FRAUD_ALERT":
        text = (
            f"🕵️‍♂️🚨 <b>[ตรวจพบความผิดปกติ/ส่อทุจริต] {safe_name} ({safe_branch})</b>\n"
            f"⚠️ เหตุ: {safe_reason}\n"
            f"💬 ข้อความ: \"{safe_last}\"\n"
            f"👉 รีบตรวจสอบใน Inbox (<a href=\"{inbox_url}\">เปิดแชทเพจ</a>)"
        )
    else:
        text = (
            f"🚨 <b>{safe_name} ({safe_branch})</b> ({safe_reason}) — \"{safe_last}\"\n"
            f"👉 มิว/แอม/กิ๊ฟ เข้าดูแลต่อในแชท (<a href=\"{inbox_url}\">เปิดแชทเพจ</a>)"
        )

    def _deliver(cid: str) -> bool:
        if alert_type == "IMAGE_RECEIVED" and image_url:
            return _send_tg_photo(bot_token, cid, image_url, text)
        return _send_tg(bot_token, cid, text)

    sent_count = 0
    if alert_type in _DM_ALERT_TYPES:
        for admin_id in get_admin_dm_ids():
            if _deliver(admin_id):
                sent_count += 1

    # ONLY notify Office ลพบุรี (-5519732256) (never spam order groups)
    office_lopburi_id = os.getenv("TELEGRAM_OFFICE_LOPBURI_CHAT_ID", "-5519732256").strip()
    if office_lopburi_id and _deliver(office_lopburi_id):
        sent_count += 1

    return sent_count


def send_telegram_handoff(
    branch: str,
    customer_name: str,
    psid: str,
    event_type: str,
    last_message: str,
    reason: str,
) -> bool:
    if event_type == "HANDOFF_ESCALATE":
        return notify_admins_boss_mode(branch, customer_name, psid, "BOT_CANNOT_HANDLE", last_message, reason) > 0

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not bot_token:
        return False

    # Always route AI chatbot handoffs to Office ลพบุรี (-5519732256), never order groups (jeans around 2 / storefront groups)
    chat_id = os.getenv("TELEGRAM_OFFICE_LOPBURI_CHAT_ID", "-5519732256").strip()
    if not chat_id:
        return False

    text = (
        f"🛒 <b>[AI Chatbot Handoff - {html.escape(branch or 'ONLINE')}]</b>\n"
        f"<b>ลูกค้า:</b> {html.escape(customer_name or 'ลูกค้า')} (PSID: <code>{html.escape(psid or '')}</code>)\n"
        f"<b>ข้อความล่าสุด:</b> {html.escape((last_message or '')[:350])}\n"
        f"<b>เหตุผล:</b> {html.escape(reason or '')}"
    )
    return _send_tg(bot_token, chat_id, text)
