"""Jeans Around 24/7 Cloud AI Sales Chatbot (3-Enter + Grill Guard + Ad/Chat Learning)."""

import asyncio
import os
import re
import sys
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

from brain_3enter import _is_bot_style_msg, analyze_customer_image_with_gemini, generate_3enter_reply, pick_image_for_reply, pick_images_for_reply
from db import (
    get_bool_setting,
    get_conn,
    get_conversation,
    get_messages,
    get_settings,
    init_db,
    list_ad_knowledge,
    list_conversations,
    list_customers_crm,
    list_grill_logs,
    list_learned_patterns,
    list_media_assets,
    list_orders,
    list_self_audits,
    log_grill,
    record_self_audit,
    save_message,
    update_setting,
    upsert_conversation,
    utc_now_iso,
)
from ads_monitor import run_ads_monitor_cycle
from grill_engine import ADMIN_BILL_MARKERS, SYSTEM_ORDER_MARKERS, _dominant_ad_branch, detect_branch, grill_conversation, is_auto_ad_greeting_text, parse_iso_dt
from learner import learn_from_page_chats
from meta_client import meta_client
from order_closer import close_and_record_order, update_order_and_reconfirm
from telegram_notifier import notify_admins_boss_mode, send_telegram_handoff

_psid_locks: Dict[str, asyncio.Lock] = {}
_AD_POST_CACHE: Dict[str, str] = {}


def _get_followup_delays() -> List[int]:
    raw = get_settings().get("followup_delays_min", "5,10,20,30,60,120,180,240")
    out = []
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            out.append(int(part))
    return out or [5, 10, 20, 30, 60, 120, 180, 240]


def _compute_next_followup_iso(stage: int) -> Optional[str]:
    delays = _get_followup_delays()
    if stage >= len(delays):
        return None
    mins = delays[stage]
    return (datetime.now(timezone.utc) + timedelta(minutes=mins)).isoformat()


async def process_customer_turn(psid: str, trigger_type: str = "INSTANT_REPLY") -> Dict[str, Any]:
    """Run Grill Engine + 3-Enter AI Generator + Send (or Dry-Run / Handoff / Block)."""
    lock = _psid_locks.setdefault(psid, asyncio.Lock())
    async with lock:
        conv = get_conversation(psid) or {"psid": psid, "customer_name": "ลูกค้า"}
        messages = get_messages(psid, limit=30)
        last_cust_msg = next(
            (m.get("text", "") for m in reversed(messages) if m.get("sender_role") == "customer"),
            "",
        )
        settings = get_settings()
        max_fup = int(settings.get("max_auto_followups", "8") or "8")
        is_followup = trigger_type == "FOLLOWUP"

        grill = grill_conversation(
            psid=psid,
            customer_name=conv.get("customer_name", "ลูกค้า"),
            messages=messages,
            conv_meta=conv,
            is_followup=is_followup,
            max_followups=max_fup,
            trigger_type=trigger_type,
        )
        decision = grill["decision"]
        branch = grill.get("branch", conv.get("branch", "ONLINE"))
        intent = grill.get("intent", "GREETING_INTEREST")

        if decision == "BLOCK":
            if grill.get("blacklist"):
                upsert_conversation(
                    {
                        "psid": psid,
                        "status": "BLACKLISTED",
                        "blacklist_reason": grill["reason"],
                        "next_followup_at": None,
                    }
                )
            elif grill.get("end_conversation"):
                upsert_conversation(
                    {
                        "psid": psid,
                        "status": "CLOSED_GRACEFULLY",
                        "next_followup_at": None,
                    }
                )
            elif "already from admin" in (grill.get("reason") or "").lower() or "already replied" in (grill.get("reason") or "").lower():
                upsert_conversation(
                    {
                        "psid": psid,
                        "status": "ADMIN_REPLIED",
                        "next_followup_at": None,
                    }
                )
            log_grill(psid, conv.get("customer_name", "ลูกค้า"), trigger_type, "BLOCK", grill["reason"], [])
            return {"decision": "BLOCK", "reason": grill["reason"]}

        if decision == "HANDOFF_IMAGE":
            last_cust_msg = next(
                (m.get("text", "") for m in reversed(messages) if m.get("sender_role") == "customer"),
                "",
            )
            img_url = last_cust_msg[7:-1] if last_cust_msg.startswith("[IMAGE:") and last_cust_msg.endswith("]") else ""
            vision = await asyncio.to_thread(analyze_customer_image_with_gemini, img_url)
            if vision and vision.get("type") in ("SLIP", "ADDRESS"):
                extracted = vision.get("extracted_text") or "ส่งสลิป/ที่อยู่ทางรูปภาพ"
                synthetic_msgs = messages + [{"sender_role": "customer", "text": f"โอนแล้ว {extracted}", "created_at": utc_now_iso()}]
                dry_run = get_bool_setting("dry_run_mode", True)
                closed = await asyncio.to_thread(
                    close_and_record_order, psid, conv.get("customer_name", "ลูกค้า"), synthetic_msgs, branch, conv.get("ad_name") or "", dry_run
                )
                # Silent handoff on slip/address photo -> let human admin verify slip & bill (never send auto-summed bill!)
                upsert_conversation({"psid": psid, "branch": branch, "status": "WON", "next_followup_at": None})
                log_grill(psid, conv.get("customer_name", "ลูกค้า"), trigger_type, "HANDOFF_ORDER", f"Vision OCR ({vision.get('type')}, silent handoff): {extracted}", [])
                return {"decision": "HANDOFF_ORDER", "order": closed["order"], "bubbles": []}

            upsert_conversation({"psid": psid, "branch": branch, "status": "HANDOFF", "next_followup_at": None})
            await asyncio.to_thread(
                notify_admins_boss_mode,
                branch,
                conv.get("customer_name", "ลูกค้า"),
                psid,
                "IMAGE_RECEIVED",
                "[ส่งรูปภาพ/สลิปเข้ามา]",
                "ลูกค้าส่งรูปภาพ/สลิปเข้ามา",
                "",
                conv.get("ad_name") or "",
                0,
                img_url,
            )
            log_grill(psid, conv.get("customer_name", "ลูกค้า"), trigger_type, "HANDOFF_IMAGE", f"Escalated image to admins: {img_url}", [])
            return {"decision": "HANDOFF_IMAGE", "image_url": img_url}

        if decision == "HANDOFF_ORDER_EDIT":
            dry_run = get_bool_setting("dry_run_mode", True)
            last_cust_msg = next(
                (m.get("text", "") for m in reversed(messages) if m.get("sender_role") == "customer"),
                "",
            )
            edited = await asyncio.to_thread(
                update_order_and_reconfirm,
                psid,
                conv.get("customer_name", "ลูกค้า"),
                last_cust_msg,
                dry_run,
            )
            confirm_bubbles = edited.get("confirm_bubbles") or []
            if confirm_bubbles:
                send_res = await meta_client.send_3enter_sequence(psid, confirm_bubbles, dry_run=dry_run)
                if not dry_run and send_res.get("ok"):
                    now = utc_now_iso()
                    for idx, b_text in enumerate(confirm_bubbles):
                        mid = (send_res.get("msg_ids") or [])[idx] if idx < len(send_res.get("msg_ids") or []) else f"bot_{psid}_{now}_{idx}"
                        save_message(mid, psid, "bot", b_text, now)
            log_grill(psid, conv.get("customer_name", "ลูกค้า"), trigger_type, "HANDOFF_ORDER_EDIT", grill["reason"], confirm_bubbles)
            return {"decision": "HANDOFF_ORDER_EDIT", "order": edited.get("order"), "bubbles": confirm_bubbles}

        if decision == "HANDOFF_ORDER":
            dry_run = get_bool_setting("dry_run_mode", True)
            closed = await asyncio.to_thread(
                close_and_record_order,
                psid,
                conv.get("customer_name", "ลูกค้า"),
                messages,
                branch,
                conv.get("ad_name") or "",
                dry_run,
            )
            # Customer already sent address/phone/transfer -> stop bot silently in THIS chat only & let human admin step in!
            upsert_conversation(
                {
                    "psid": psid,
                    "branch": branch,
                    "status": "WON",
                    "followup_stage": 0,
                    "next_followup_at": None,
                }
            )
            log_grill(
                psid,
                conv.get("customer_name", "ลูกค้า"),
                trigger_type,
                "HANDOFF_ORDER",
                f"{grill['reason']} (Silent handoff to human admin) | Order #{closed['order']['id']} ({closed['order']['items']} {closed['order']['amount']}฿)",
                [],
            )
            return {"decision": "HANDOFF_ORDER", "order": closed["order"], "bubbles": []}

        if decision == "HANDOFF_ESCALATE":
            last_cust_msg = next(
                (m.get("text", "") for m in reversed(messages) if m.get("sender_role") == "customer"),
                "",
            )
            upsert_conversation(
                {
                    "psid": psid,
                    "branch": branch,
                    "status": "HANDOFF",
                    "next_followup_at": None,
                }
            )
            await asyncio.to_thread(
                send_telegram_handoff,
                branch,
                conv.get("customer_name", "ลูกค้า"),
                psid,
                decision,
                last_cust_msg,
                grill["reason"],
            )
            log_grill(psid, conv.get("customer_name", "ลูกค้า"), trigger_type, decision, grill["reason"], [])
            return {"decision": decision, "reason": grill["reason"]}

        # Generate 3-Enter bubbles (fetch full Ad post caption/price so reply matches exact post)
        stage = int(conv.get("followup_stage") or 0)
        ad_id_val = conv.get("ad_id") or ""
        if ad_id_val:
            if ad_id_val not in _AD_POST_CACHE:
                _AD_POST_CACHE[ad_id_val] = (await asyncio.to_thread(meta_client.get_ad_post_text, ad_id_val)) or ""
            ad_post_text = _AD_POST_CACHE[ad_id_val]
        else:
            ad_post_text = ""
        # Deep history lookup when customer asks to use their existing/saved address
        brain_messages = messages
        if (
            not is_followup
            and re.search(r"(ที่อยู่เดิม|ส่งที่เดิม|ใช้ที่อยู่เดิม|ตามที่อยู่เดิม|ที่อยู่เก่า|ส่งตามเดิม|ที่อยู่คุณ|ที่อยู่พี่|ที่อยู่แม่|ส่งที่อยู่|เหมือนเดิม)", last_cust_msg or "")
            and conv.get("conv_id")
        ):
            deep_msgs = await asyncio.to_thread(meta_client.fetch_conversation_messages, conv["conv_id"], 80)
            if deep_msgs and len(deep_msgs) > len(messages):
                brain_messages = deep_msgs

        bubbles = await asyncio.to_thread(
            generate_3enter_reply,
            conv.get("customer_name", "ลูกค้า"),
            branch,
            intent,
            brain_messages,
            grill.get("already_covered", {}),
            conv.get("ad_name") or "",
            conv.get("campaign_name") or "",
            is_followup,
            stage,
            ad_post_text,
        )
        if not bubbles:
            upsert_conversation({"psid": psid, "branch": branch, "status": "CLOSED_GRACEFULLY", "next_followup_at": None})
            log_grill(psid, conv.get("customer_name", "ลูกค้า"), trigger_type, "BLOCK", "All follow-up stages exhausted/deduplicated", [])
            return {"decision": "BLOCK", "reason": "Follow-up deduplicated / exhausted"}

        image_urls = await asyncio.to_thread(
            pick_images_for_reply,
            messages,
            intent,
            branch,
            conv.get("ad_name") or "",
            is_followup,
            stage,
        )
        dry_run = get_bool_setting("dry_run_mode", True)
        send_res = await meta_client.send_3enter_sequence(psid, bubbles, dry_run=dry_run, image_urls=image_urls)

        new_stage = (stage + 1) if is_followup else 0
        next_fup = _compute_next_followup_iso(new_stage)

        if not dry_run and send_res.get("ok"):
            now = utc_now_iso()
            sent_ids = send_res.get("msg_ids") or []
            for idx, b_text in enumerate(bubbles):
                mid = sent_ids[idx] if idx < len(sent_ids) else f"bot_{psid}_{now}_{idx}"
                save_message(mid, psid, "bot", b_text, now)
            img_count = int(send_res.get("image_count") or (1 if send_res.get("image_sent") else 0))
            for img_idx in range(img_count):
                msg_pos = len(bubbles) + img_idx
                img_mid = sent_ids[msg_pos] if len(sent_ids) > msg_pos else f"bot_img_{psid}_{now}_{img_idx}"
                save_message(img_mid, psid, "bot", "[BOT_SENT_IMAGE]", now)
            close_gracefully = bool(grill.get("close_after_send"))
            also_escalate = bool(grill.get("also_escalate"))
            if also_escalate:
                new_status = "HANDOFF"
                final_next_fup = None
            elif close_gracefully:
                new_status = "CLOSED_GRACEFULLY"
                final_next_fup = None
            else:
                new_status = "WAITING_REPLY"
                final_next_fup = next_fup
            upsert_conversation(
                {
                    "psid": psid,
                    "branch": branch,
                    "status": new_status,
                    "last_bot_msg_at": now,
                    "followup_stage": 0 if (close_gracefully or also_escalate) else new_stage,
                    "next_followup_at": final_next_fup,
                }
            )
            log_grill(psid, conv.get("customer_name", "ลูกค้า"), trigger_type, "SEND", grill["reason"], bubbles)
            last_cust_msg = next((m.get("text", "") for m in reversed(messages) if m.get("sender_role") == "customer"), "")
            if also_escalate:
                await asyncio.to_thread(
                    send_telegram_handoff,
                    branch,
                    conv.get("customer_name", "ลูกค้า"),
                    psid,
                    intent,
                    last_cust_msg,
                    grill["reason"],
                )
            photo_assist_intents = {
                "ASK_STOCK_MODEL",
                "ASK_COLOR_LENGTH",
                "ASK_STYLE_FIT",
                "ASK_PRICE_PROMO",
                "ASK_SIZE_CHART",
                "ASK_COD",
                "GENERAL_INQUIRY",
            }
            if (
                not close_gracefully
                and not is_followup
                and grill.get("intent") in photo_assist_intents
                and last_cust_msg.strip() not in ("", "[STICKER]")
            ):
                await asyncio.to_thread(
                    notify_admins_boss_mode,
                    branch,
                    conv.get("customer_name", "ลูกค้า"),
                    psid,
                    "ADMIN_ASSIST_PHOTO",
                    last_cust_msg,
                    "เข้าส่งรูป+ทวนลูกค้า",
                    "",
                    conv.get("ad_name") or "",
                    0,
                )
            return {"decision": "SEND", "bubbles": bubbles, "send_res": send_res}
        elif dry_run:
            upsert_conversation(
                {
                    "psid": psid,
                    "branch": branch,
                    "status": "WAITING_REPLY",
                    "followup_stage": new_stage,
                    "next_followup_at": next_fup,
                }
            )
            log_grill(psid, conv.get("customer_name", "ลูกค้า"), trigger_type, "DRY_RUN", grill["reason"], bubbles)
            return {"decision": "DRY_RUN", "bubbles": bubbles}
        else:
            err_str = str(send_res.get("errors") or "")
            log_grill(psid, conv.get("customer_name", "ลูกค้า"), trigger_type, "ERROR", err_str, bubbles)
            is_unreachable = ("#10" in err_str or "#551" in err_str or trigger_type == "COMMENT_BOT_FOLLOWUP")
            upsert_conversation({
                "psid": psid,
                "branch": branch,
                "status": "HANDOFF_UNREACHABLE" if is_unreachable else "HANDOFF",
                "next_followup_at": None,
            })
            last_cust_msg = next((m.get("text", "") for m in reversed(messages) if m.get("sender_role") == "customer"), "")
            alert_kind = "COMMENT_ALERT" if trigger_type == "COMMENT_BOT_FOLLOWUP" else "BOT_CANNOT_HANDLE"
            if trigger_type == "COMMENT_BOT_FOLLOWUP" or "#10" in err_str:
                reason_txt = "ลูกค้าเม้น/เกิน 24 ชม. ของ Meta (#10)"
            elif "#551" in err_str:
                reason_txt = "Meta ยังไม่เปิดหน้าต่างข้อความ (#551)"
            else:
                reason_txt = "บอทส่งไม่สำเร็จ"
            await asyncio.to_thread(
                notify_admins_boss_mode,
                branch,
                conv.get("customer_name", "ลูกค้า"),
                psid,
                alert_kind,
                last_cust_msg or "ทักเข้ามา",
                reason_txt,
            )
            return {"decision": "ERROR", "errors": send_res.get("errors")}


def _is_closing_or_no_reply_needed(text: str, recent_msgs: Optional[List[Dict[str, Any]]] = None) -> bool:
    """Return True when customer's last message is a sticker, emoji-only, or polite closing ack (no admin reply needed)."""
    t = (text or "").strip()
    if t in ("", "[STICKER]"):
        return True
    if t.startswith("[IMAGE:"):
        return False
    if not re.search(r"[ก-๙a-zA-Z0-9]", t):
        return True

    low = t.lower()
    has_question_or_negotiate = any(q in low for q in ("?", "ไหม", "มั้ย", "รึเปล่า", "หรือเปล่า", "เท่าไหร่", "เท่าไร", "ลดได้", "ลดอีก", "เปลี่ยน", "ผิด", "ตำหนิ"))

    # Early check for rejections, declines, deferrals, "just browsing", or "just letting you know" endings (even if text contains ดู/สั่ง/สี/แวะ/รูป/ส่ง)
    decline_or_busy_phrases = (
        "ยังไม่เอา", "ไม่เอา", "ยังไม่รับ", "ไม่รับ", "ยังก่อน", "ไม่ชอบ", "ไม่ถูกใจ",
        "ยังไม่สั่ง", "ยังไม่ได้สั่ง", "ไม่สั่งแล้ว", "ไม่ได้สั่ง", "ยังไม่ซื้อ",
        "แพงมาก", "แพงไป", "เกินงบ", "งบไม่ถึง", "ถามเฉย", "ดูเฉย", "ดูไว้ก่อน", "ไว้ดู", "ส่องเฉย",
        "ขอดูก่อน", "ขอคิดดูก่อน", "คิดดูก่อน", "ตัดสินใจก่อน", "ผ่านก่อน", "ไว้ก่อน", "งั้นไม่เป็นไร", "ไม่เป็นไร",
        "ไว้โอกาสหน้า", "ไว้แวะ", "เดี๋ยวแวะ", "เด่วแวะ", "เดวแวะ", "แวะมาดู", "แวะไปดู", "มาดูเอง", "ไปดูเอง", "แวะมาลอง", "แวะไปลอง", "เดวแวะมา", "เดวแวะไป", "เดี๋ยวไปดูต่อ", "ไปดูต่อ", "ขอตัดสินใจ", "เอาไว้ก่อน", "เดวค่อย", "เดี๋ยวค่อย", "แค่นี้นะ", "พอแล้ว", "ยังไม่สะดวก", "ไม่สะดวก", "ไม่ว่าง", "ติดธุระ",
        "พบหมอ", "หาหมอ", "ขับรถ", "จะรีบตอบกลับ", "เดี๋ยวตอบกลับ", "เดี๋ยวทัก", "ไว้ทัก",
        "ถ้ามีแบบ", "ส่งรูปมาให้ดู", "ส่งมาให้ดูบ้าง", "เดี๋ยวรอ", "บอกเฉย", "แจ้งไว้", "แค่นี้ก่อน", "มีแบบใหม่",
    )
    if not has_question_or_negotiate and any(p in low for p in decline_or_busy_phrases):
        return True

    # Early check for unambiguous closing acks / thank-you / already-ordered / post-purchase feedback endings before buying-signal match
    if len(low) <= 80 and any(p in low for p in ("รับทราบ", "ได้รับของแล้ว", "ได้รับแล้ว", "ได้ของแล้ว", "ขอบคุณ", "ขอบคุน", "ขอบพระคุณ", "ขอบใจ", "เรียบร้อยแล้ว", "ใส่ได้พอดี", "ใส่สวย", "ผ้าดีมาก", "สวยมาก", "ชอบมาก", "ตรงปก", "สั่งแล้ว", "สั่งแร้ว", "สั่งไปแล้ว", "สั่งเรียบร้อย", "กดสั่งแล้ว", "ซื้อแล้ว")) and not has_question_or_negotiate:
        return True

    # Keep alerting if there is ANY question, buying intent, sizing, payment, address, or after-sales signal
    keep_signals = (
        "?", "ไหม", "มั้ย", "รึเปล่า", "หรือเปล่า", "กี่", "เท่าไหร่", "เท่าไร", "ไหน", "อะไร", "ยังไง", "ตอนไหน", "วันไหน",
        "เอว", "สะโพก", "ไซส์", "ไซด์", "size", "xl", "โอน", "ปลายทาง", "cod", "สั่ง", "รับตัว", "รับไซ", "เอาตัว", "เอาไซ", "ส่ง", "ที่อยู่",
        "โทร", "สลิป", "เลขพัสดุ", "เปลี่ยน", "ตำหนิ", "ผิด", "ราคา", "ลด", "โปร", "สี", "ทรง", "ยาว",
        "กระโปรง", "ขาสั้น", "เสื้อ", "สนใจ", "ดู", "รูป", "ตาราง", "สาขา", "อยู่ตรงไหน",
    )
    if any(k in low for k in keep_signals) or re.search(r"\b0[689]\d", low):
        return False

    # Short polite closing / acknowledgement phrases (admin intentionally doesn't reply further)
    closing_phrases = (
        "ขอบคุณ", "ขอบพระคุณ", "ขอบใจ", "รับทราบ", "โอเค", "ok", "okja", "ok ja", "ok ka", "ok kha", "thank you", "thanks", "เคจ้า", "เคค่ะ", "เคคะ", "เคค่า",
        "ไว้แวะ", "เดี๋ยวแวะ", "เด่วแวะ", "ไว้โอกาสหน้า", "ไว้ก่อน", "ยังไม่สะดวก", "ยังไม่ได้ไป",
        "ไม่เป็นไร", "เรียบร้อย", "ได้รับของแล้ว", "ได้รับแล้ว", "สาธุ", "ยินดี", "เข้าใจแล้ว",
        "สวยมาก", "น่ารักมาก", "ถูกใจมาก", "ใส่พอดี", "ตรงปก",
    )
    if len(low) <= 65 and any(p in low for p in closing_phrases):
        return True

    # Pure short acknowledgement like "ค่ะ", "จ้า", "ได้ค่ะ", "อ่อค่ะ"
    if re.match(r"^(?:ได้|อ่อ|อ๋อ|อืม|จ้า|จร้า|จ้ะ|ค่ะ|คะ|ค่า|นะคะ|นะค่ะ|ครับ|คับ)+[!.\s🙏❤️🥰👍]*$", low):
        return True

    # After order is already closed/billed in recent messages, short trailing message needs no alert
    if recent_msgs and len(low) <= 45:
        recent_page = " ".join(
            (m.get("text") or "") for m in recent_msgs[-5:-1] if m.get("sender_role") != "customer"
        )
        if any(mk in recent_page for mk in ("สรุปออเดอร์การสั่งซื้อ", "รับออเดอร์ค่ะ", "คุณร้องขอไป ฿", "ทำเครื่องหมายคำสั่งซื้อว่า")):
            return True

    return False


_POST_CAPTION_CACHE: Dict[str, str] = {}


_FRAUD_SEEN_KEYS: set = set()


def _check_fraud_and_deletions(psid: str, cust_name: str, branch: str, raw_msgs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Detect deleted Meta messages (admin hid/deleted chat msg) & suspicious private bank/Line diversions."""
    findings: List[Dict[str, Any]] = []
    if len(raw_msgs) < 2:
        return findings
    raw_mids = {m.get("id") for m in raw_msgs if m.get("id")}
    oldest_dt = parse_iso_dt(raw_msgs[0].get("created_time"))
    if oldest_dt:
        now_utc_chk = datetime.now(timezone.utc)
        with get_conn() as conn:
            saved = conn.execute(
                "SELECT msg_id, sender_role, text, created_at FROM messages WHERE psid = ? AND sender_role != 'bot' AND msg_id LIKE 'm_%' ORDER BY created_at ASC",
                (psid,),
            ).fetchall()
        for row in saved:
            mid = row["msg_id"]
            s_dt = parse_iso_dt(row["created_at"])
            # Only flag messages strictly newer than oldest_dt AND older than 90s (avoid Meta indexing lag)
            if s_dt and s_dt > (oldest_dt + timedelta(seconds=5)) and (now_utc_chk - s_dt).total_seconds() > 90 and mid not in raw_mids:
                fkey = ("DEL", mid)
                if fkey not in _FRAUD_SEEN_KEYS:
                    _FRAUD_SEEN_KEYS.add(fkey)
                    txt = (row["text"] or "")[:120]
                    reason = f"ข้อความ ({row['sender_role']}) ถูกลบออกจากแชทเพจ!"
                    log_grill(psid, cust_name, "FRAUD_AUDIT", "FRAUD_MSG_DELETED", f"{reason} | {txt}", [])
                    findings.append({"type": "FRAUD_MSG_DELETED", "psid": psid, "customer_name": cust_name, "text": txt})
                    notify_admins_boss_mode(branch, cust_name, psid, "FRAUD_ALERT", txt, reason)
    # Check admin messages for unauthorized personal bank numbers / Line IDs
    official_whitelist = set(
        x.strip() for x in (get_settings().get("OFFICIAL_BANK_WHITELIST", "") or "").split(",") if x.strip()
    )
    for m in raw_msgs[-6:]:
        mid = m.get("id") or ""
        from_id = (m.get("from") or {}).get("id")
        txt = (m.get("message") or "").strip()
        if from_id != meta_client.page_id or not txt or _is_bot_style_msg(txt):
            continue
        if any(mk in txt for mk in SYSTEM_ORDER_MARKERS) or any(mk in txt for mk in ADMIN_BILL_MARKERS):
            continue
        if any(st in txt for st in ("📍", "เซนทรัล", "เซ็นทรัล", "พิกัดหน้าร้าน", "จัดส่งไปที่", "ผู้รับ:", "ที่อยู่:", "ที่อยู่ :", "0932135716", "082-927-1808", "0829271808", "098-110-8961", "0981108961")):
            continue
        digits_list = re.findall(r"\b\d[\d\-]{8,14}\d\b", txt)
        clean_nums = [re.sub(r"\D", "", d) for d in digits_list if 10 <= len(re.sub(r"\D", "", d)) <= 13]
        has_bank_ctx = any(k in txt.lower() for k in ("บัญชี", "โอน", "พร้อมเพย์", "กสิกร", "ไทยพาณิชย์", "กรุงไทย", "กรุงเทพ", "ออมสิน", "kbank", "scb", "ktb"))
        suspicious_num = [n for n in clean_nums if not any(w in n for w in official_whitelist)] if (clean_nums and has_bank_ctx) else []
        has_line_divert = bool(re.search(r"(?:แอดไลน์|id\s*line|ไลน์ส่วนตัว|ทักไลน์)\s*[:@]?\s*[a-zA-Z0-9._-]{3,}", txt, re.IGNORECASE))
        if suspicious_num or has_line_divert:
            fkey = ("LEAK", mid)
            if fkey not in _FRAUD_SEEN_KEYS:
                _FRAUD_SEEN_KEYS.add(fkey)
                reason = "แอดมินส่งเลขบัญชี/พร้อมเพย์" if suspicious_num else "แอดมินชวนลูกค้าแอดไลน์ส่วนตัว"
                log_grill(psid, cust_name, "FRAUD_AUDIT", "FRAUD_BANK_OR_LINE_LEAK", f"{reason} | {txt[:120]}", [])
                findings.append({"type": "FRAUD_BANK_OR_LINE_LEAK", "psid": psid, "customer_name": cust_name, "text": txt[:120]})
                notify_admins_boss_mode(branch, cust_name, psid, "FRAUD_ALERT", txt[:120], reason)
    return findings


async def poller_loop() -> None:
    """24/7 Turbo Cloud Poller: 1-second fast poll (top 8 chats) + deep 25-chat sync every 10th cycle so AI beats human admins."""
    await asyncio.sleep(2)
    _poll_cycle = 0
    while True:
        try:
            auto_pilot = get_bool_setting("auto_pilot_enabled", False)
            _poll_cycle += 1
            if _poll_cycle == 1 or (_poll_cycle % 10 == 0):
                convs = await asyncio.to_thread(meta_client.fetch_conversations, 25, 15)
            else:
                convs = await asyncio.to_thread(meta_client.fetch_conversations, 8, 8)
            ad_rows = list_ad_knowledge()
            for c in convs:
                participants = (c.get("participants") or {}).get("data", [])
                cust_p = next((p for p in participants if p.get("id") != meta_client.page_id), None)
                if not cust_p:
                    continue
                psid = cust_p.get("id")
                if _psid_locks.get(psid) and _psid_locks[psid].locked():
                    continue
                cust_name = cust_p.get("name", "ลูกค้า")
                raw_msgs = list(reversed((c.get("messages") or {}).get("data", [])))
                if not raw_msgs:
                    continue

                existing = get_conversation(psid)
                latest_raw_mid = raw_msgs[-1].get("id")
                unread_cnt = c.get("unread_count")
                if existing and existing.get("last_msg_id") == latest_raw_mid:
                    # If admin already opened & read a HANDOFF chat in Meta Inbox (unread_count == 0) -> silence SLA nags only (never kill OPEN bot replies)
                    if unread_cnt == 0 and existing.get("status") in ("HANDOFF", "HANDOFF_ALERTED", "HANDOFF_CRITICAL"):
                        upsert_conversation({"psid": psid, "status": "ADMIN_REPLIED"})
                    ex_st = existing.get("status")
                    ex_now = datetime.now(timezone.utc)
                    ex_cust_dt = parse_iso_dt(existing.get("last_customer_msg_at"))
                    ex_bot_dt = parse_iso_dt(existing.get("last_bot_msg_at"))
                    ex_adm_dt = parse_iso_dt(existing.get("last_admin_msg_at"))
                    # 1) Smart Human-Admin Grace (600s = 10m): if human admin replied within 10m, DO NOT interrupt live human chat!
                    ex_admin_active = bool(ex_adm_dt and (ex_now - ex_adm_dt).total_seconds() <= 600)
                    if (
                        not ex_admin_active
                        and ex_st not in ("WON", "BLACKLISTED", "CLOSED_GRACEFULLY", "HANDOFF", "HANDOFF_ALERTED", "HANDOFF_CRITICAL")
                        and ex_cust_dt
                        and (not ex_bot_dt or ex_cust_dt > ex_bot_dt)
                        and (not ex_adm_dt or ex_cust_dt > ex_adm_dt)
                        and (ex_now - ex_cust_dt).total_seconds() <= 1800
                    ):
                        pass
                    # 2) If admin replied > 10m ago and customer is silent inside 23h window -> arm 8-Step Follow-up!
                    elif ex_st == "ADMIN_REPLIED" and ex_adm_dt and ex_cust_dt and (ex_now - ex_adm_dt).total_seconds() > 600 and (ex_now - ex_cust_dt).total_seconds() <= 82800:
                        upsert_conversation({
                            "psid": psid,
                            "status": "WAITING_REPLY",
                            "next_followup_at": existing.get("next_followup_at") or _compute_next_followup_iso(int(existing.get("followup_stage") or 0)),
                        })
                        continue
                    elif ex_st != "OPEN":
                        continue

                new_customer_msg = False
                new_human_admin_msg = False
                last_bill_at = None
                ad_click_after_bill = False
                new_comment_bot_msg = None
                last_cust_at = None
                last_admin_at = None
                last_human_admin_at = None
                last_real_role = "customer"
                prev_raw_text = ""
                last_ad_click_dt = None
                _db_bot_msgs = [m for m in get_messages(psid, limit=40) if m.get("sender_role") == "bot"]
                bot_mids = {(m.get("msg_id") or m.get("mid")) for m in _db_bot_msgs}
                bot_texts = {(m.get("text") or "").strip() for m in _db_bot_msgs if (m.get("text") or "").strip()}

                for m in raw_msgs:
                    mid = m.get("id")
                    from_id = (m.get("from") or {}).get("id")
                    text = m.get("message") or ""
                    is_sys_order_event = any(mk in text for mk in SYSTEM_ORDER_MARKERS)
                    role = "admin" if (from_id == meta_client.page_id or is_sys_order_event) else "customer"
                    atts = (m.get("attachments") or {}).get("data", [])
                    if not text and atts and role == "customer":
                        first_att = atts[0]
                        img_data = first_att.get("image_data") or {}
                        img_url = img_data.get("url") or ""
                        w = int(img_data.get("width") or 0)
                        h = int(img_data.get("height") or 0)
                        mime = (first_att.get("mime_type") or "").lower()
                        is_small_emoji = (0 < w <= 160 and 0 < h <= 160 and "png" in mime) or any(k in img_url for k in ("t39.1997-6", "851557", "emoji"))
                        is_sticker = is_small_emoji or ("sticker" in mime) or ("webp" in mime and not first_att.get("name"))
                        text = "[STICKER]" if is_sticker else f"[IMAGE:{img_url}]"
                    elif not text and atts and role == "admin":
                        text = "[ADMIN_SENT_IMAGE]"
                    created_at = m.get("created_time") or utc_now_iso()

                    if any(mk in text for mk in ADMIN_BILL_MARKERS):
                        last_bill_at = created_at
                        ad_click_after_bill = False
                    elif "ตอบกลับโฆษณา" in text and last_bill_at is not None:
                        ad_click_after_bill = True

                    inserted = save_message(mid, psid, role, text, created_at)
                    is_auto_comment_msg = (not _is_bot_style_msg(text)) and (
                        "คุณลูกค้าแจ้งรอบเอว" in text
                        or text.strip().startswith(('"', '“'))
                        or "สวัสดีค่า เห็นพี่เม้นมา" in text
                        or "กำลังตอบกลับความคิดเห็น" in text
                    )
                    cur_m_dt = parse_iso_dt(created_at)
                    if "ตอบกลับโฆษณา" in text and cur_m_dt:
                        last_ad_click_dt = cur_m_dt
                    within_ad_burst = bool(role == "admin" and last_ad_click_dt and cur_m_dt and 0 <= (cur_m_dt - last_ad_click_dt).total_seconds() <= 10)
                    is_auto_ad_greeting = within_ad_burst or is_auto_ad_greeting_text(text, prev_raw_text)
                    is_bot_sent = (mid in bot_mids) or (text.strip() in bot_texts) or _is_bot_style_msg(text)
                    if text != "[ADMIN_SENT_IMAGE]":
                        prev_raw_text = text

                    if role == "customer":
                        last_cust_at = created_at
                        last_real_role = "customer"
                    else:
                        last_admin_at = created_at
                        if is_bot_sent:
                            last_real_role = "bot"
                        elif not is_auto_ad_greeting and not is_auto_comment_msg:
                            last_real_role = "admin"

                    if role == "admin" and not is_sys_order_event and not is_auto_ad_greeting and not is_auto_comment_msg and not is_bot_sent:
                        last_human_admin_at = created_at
                    if inserted and role == "customer":
                        new_customer_msg = True
                    elif inserted and role == "admin" and is_auto_comment_msg:
                        if not any(p in text for p in ("1,290", "990", "2,400", "หน้าร้านของเรา", "ขอบพระคุณมากๆ")):
                            new_comment_bot_msg = (mid, text, created_at)
                    elif inserted and role == "admin" and not is_sys_order_event and not is_auto_ad_greeting and not is_bot_sent:
                        new_human_admin_msg = True

                last_role = last_real_role
                matched_ad = None
                recent_texts_newest = [
                    (rm.get("message") or "")
                    for rm in reversed(raw_msgs)
                    if rm.get("message") and not _is_bot_style_msg(rm.get("message") or "")
                ]
                db_msgs_cache: Optional[List[Dict[str, Any]]] = None
                if len(recent_texts_newest) < 20:
                    db_msgs_cache = get_messages(psid, limit=25)
                    extra_db = [
                        (dm.get("text") or "")
                        for dm in reversed(db_msgs_cache)
                        if dm.get("text") and not _is_bot_style_msg(dm.get("text") or "") and (dm.get("text") or "") not in recent_texts_newest
                    ]
                    recent_texts_newest.extend(extra_db)
                # 1. Direct Meta Reel / Post / Photo ID lookup in latest ad/comment messages
                for msg_txt in recent_texts_newest:
                    m_story = re.search(r"(?:reel|posts|videos|fbid=|story_fbid=)[/?=]?(\d{8,})", msg_txt)
                    if not m_story:
                        continue
                    oid = m_story.group(1)
                    for ad_row in ad_rows:
                        if oid in (ad_row.get("creative_summary") or ""):
                            matched_ad = ad_row
                            break
                    if not matched_ad:
                        if oid not in _POST_CAPTION_CACHE:
                            _POST_CAPTION_CACHE[oid] = (await asyncio.to_thread(meta_client.fetch_post_message, oid)) or ""
                        post_cap = _POST_CAPTION_CACHE[oid]
                        if post_cap:
                            p_branch = detect_branch(post_cap)
                            if p_branch != "ONLINE":
                                matched_ad = {
                                    "ad_id": f"post_{oid}",
                                    "ad_name": f"Post/Reel {oid} ({p_branch})",
                                    "campaign_name": f"POST_BRANCH:{p_branch}",
                                    "branch": p_branch,
                                }
                    if matched_ad:
                        break
                # 2. Whitespace-normalized caption snippet lookup across recent messages (scanning 0..24, 24..52, 52..80, 80..108)
                if not matched_ad:
                    thread_blob = " ".join(" ".join(recent_texts_newest).split()).lower()
                    for msg_txt in recent_texts_newest:
                        low_msg = " ".join(msg_txt.split()).lower()
                        for ad_row in ad_rows:
                            csum = " ".join((ad_row.get("creative_summary") or "").split()).lower()
                            body_full = csum.split("—", 1)[-1].strip() if "—" in csum else ""
                            if len(body_full) < 12:
                                continue
                            chunks = [body_full[pos : pos + 24].strip() for pos in (0, 24, 52, 80) if len(body_full[pos:].strip()) >= 14]
                            if any(ch in low_msg or ch in thread_blob for ch in chunks):
                                matched_ad = ad_row
                                break
                        if matched_ad:
                            break

                eff_ad_name = (matched_ad or {}).get("ad_name") or (existing or {}).get("ad_name")
                eff_camp_name = (matched_ad or {}).get("campaign_name") or (existing or {}).get("campaign_name")
                eff_branch = (matched_ad or {}).get("branch") if (matched_ad or {}).get("branch") in ("KKC", "KORAT", "UDN") else None
                if not eff_branch:
                    ad_pin = next((t for t in recent_texts_newest if _dominant_ad_branch(t)), "")
                    cust_recent = " ".join((rm.get("message") or "") for rm in raw_msgs if (rm.get("from") or {}).get("id") != meta_client.page_id)
                    eff_branch = detect_branch(
                        " ".join(recent_texts_newest[:6]),
                        eff_ad_name or "",
                        eff_camp_name or "",
                        cust_text=cust_recent,
                        latest_ad_text=ad_pin,
                    )
                upsert_data: Dict[str, Any] = {
                    "psid": psid,
                    "conv_id": c.get("id"),
                    "customer_name": cust_name,
                    "branch": eff_branch or (existing or {}).get("branch") or "ONLINE",
                    "ad_id": (matched_ad or {}).get("ad_id") or (existing or {}).get("ad_id"),
                    "ad_name": eff_ad_name,
                    "campaign_name": eff_camp_name,
                    "last_customer_msg_at": last_cust_at,
                    "last_admin_msg_at": last_admin_at,
                    "last_msg_id": raw_msgs[-1].get("id"),
                }
                # Mark OPEN for instant reply only for recent messages created after (or within 2m of) bot boot
                now_utc = datetime.now(timezone.utc)
                cust_dt = parse_iso_dt(last_cust_at)
                last_bot_dt = parse_iso_dt((existing or {}).get("last_bot_msg_at"))
                cust_age_sec = (now_utc - cust_dt).total_seconds() if cust_dt else 999999
                is_recent_msg = bool(cust_dt and cust_age_sec <= 14400)
                # Allow answering unanswered messages from up to 4h ago even across Render restarts
                is_after_boot = bool(cust_dt and (cust_dt >= (BOT_STARTED_AT - timedelta(seconds=120)) or cust_age_sec <= 14400))
                admin_dt = parse_iso_dt(last_human_admin_at)
                admin_within_23h = bool(admin_dt and (now_utc - admin_dt).total_seconds() <= 82800)
                admin_active_recent = bool(admin_dt and (now_utc - admin_dt).total_seconds() <= 600)
                # Smart AI: answer every unanswered customer message immediately when human admin is NOT actively chatting (3m grace)
                bot_needs_reply = bool(
                    last_role == "customer"
                    and not admin_active_recent
                    and cust_dt
                    and (not last_bot_dt or cust_dt > last_bot_dt)
                    and (new_customer_msg or cust_age_sec <= 1800)
                )
                bill_dt = parse_iso_dt(last_bill_at)
                admin_billed_active = bool(bill_dt and (now_utc - bill_dt).total_seconds() <= 82800 and not ad_click_after_bill)
                recover_unanswered = bool(
                    bot_needs_reply
                    and (not existing or existing.get("status") not in ("BLACKLISTED", "CLOSED_GRACEFULLY", "HANDOFF", "HANDOFF_ALERTED", "HANDOFF_CRITICAL"))
                )
                if admin_billed_active and not new_customer_msg:
                    upsert_data["status"] = "WON"
                    upsert_data["next_followup_at"] = None
                elif admin_active_recent and last_role == "admin":
                    if not (existing and existing.get("status") in ("WON", "BLACKLISTED", "CLOSED_GRACEFULLY")):
                        upsert_data["status"] = "ADMIN_REPLIED"
                        upsert_data["next_followup_at"] = None
                elif last_role == "customer" and (new_customer_msg or recover_unanswered) and (not existing or existing.get("status") != "BLACKLISTED"):
                    if admin_billed_active:
                        upsert_data["status"] = "WON"
                        upsert_data["next_followup_at"] = None
                    elif admin_active_recent:
                        upsert_data["status"] = "ADMIN_REPLIED"
                        upsert_data["next_followup_at"] = None
                    else:
                        upsert_data["status"] = "OPEN" if (is_recent_msg and is_after_boot) else "SYNCED_OLD"
                        upsert_data["followup_stage"] = 0
                        upsert_data["next_followup_at"] = None
                elif last_role == "admin" and (not existing or new_human_admin_msg or existing.get("status") in ("OPEN", "ADMIN_REPLIED", "HANDOFF", "HANDOFF_ALERTED", "HANDOFF_CRITICAL")):
                    if not (existing and existing.get("status") in ("WON", "BLACKLISTED", "CLOSED_GRACEFULLY")):
                        admin_idle_sec = (now_utc - admin_dt).total_seconds() if admin_dt else 999999
                        if (not admin_billed_active) and admin_idle_sec > 600 and cust_dt and cust_age_sec <= 82800:
                            upsert_data["status"] = "WAITING_REPLY"
                            upsert_data["next_followup_at"] = (existing or {}).get("next_followup_at") or _compute_next_followup_iso(int((existing or {}).get("followup_stage") or 0))
                        else:
                            upsert_data["status"] = "ADMIN_REPLIED"
                            upsert_data["next_followup_at"] = None
                elif last_role == "bot" and (not existing or existing.get("status") == "OPEN" or not (existing.get("next_followup_at"))):
                    # Survive Render ephemeral DB restarts: re-arm 8-Step Follow-up for unclosed bot-replied chats inside 23h window!
                    if (not admin_billed_active) and cust_dt and cust_age_sec <= 82800 and (not existing or existing.get("status") not in ("WON", "BLACKLISTED", "CLOSED_GRACEFULLY", "HANDOFF", "HANDOFF_ALERTED", "HANDOFF_CRITICAL")):
                        upsert_data["status"] = "WAITING_REPLY"
                        upsert_data["next_followup_at"] = _compute_next_followup_iso(int((existing or {}).get("followup_stage") or 0))

                upsert_conversation(upsert_data)
                asyncio.create_task(asyncio.to_thread(_check_fraud_and_deletions, psid, cust_name, upsert_data["branch"], raw_msgs))

                # Fire AI instant reply FIRST (non-blocking) on EVERY customer message — never yields to human admin!
                is_turn_locked = bool(_psid_locks.get(psid) and _psid_locks[psid].locked())
                if auto_pilot and bot_needs_reply and is_recent_msg and is_after_boot and not is_turn_locked:
                    conv_now = get_conversation(psid)
                    if conv_now and (conv_now.get("status") == "OPEN" or (conv_now.get("status") == "WON" and new_customer_msg)):
                        asyncio.create_task(process_customer_turn(psid, trigger_type="INSTANT_REPLY"))
                elif auto_pilot and last_role == "admin" and new_comment_bot_msg and not is_turn_locked:
                    cb_mid, cb_text, cb_at = new_comment_bot_msg
                    cb_dt = parse_iso_dt(cb_at)
                    if cb_dt and (datetime.now(timezone.utc) - cb_dt).total_seconds() <= 900:
                        quoted = cb_text.splitlines()[0].strip(' "“”') or cb_text[:120]
                        cb_quote_at = (cb_dt + timedelta(seconds=1)).isoformat()
                        save_message(f"cb_quote_{cb_mid}", psid, "customer", quoted, cb_quote_at)
                        upsert_conversation({"psid": psid, "status": "OPEN", "followup_stage": 0})
                        asyncio.create_task(process_customer_turn(psid, trigger_type="COMMENT_BOT_FOLLOWUP"))

                if (
                    new_customer_msg
                    and last_role == "customer"
                    and is_recent_msg
                    and is_after_boot
                    and (not existing or existing.get("status") != "BLACKLISTED")
                ):
                    latest_saved = get_messages(psid, limit=5)
                    latest_saved_txt = (latest_saved[-1].get("text") or "").strip() if latest_saved else ""
                    is_urgent_cust = any(k in latest_saved_txt for k in ("ยกเลิก", "เปลี่ยน", "ผิด", "ไม่ครบ", "ตาม", "คืน", "ตำหนิ"))
                    if is_urgent_cust or not _is_closing_or_no_reply_needed(latest_saved_txt, latest_saved):
                        last_c_txt = next(
                            ((rm.get("message") or "").strip() for rm in reversed(raw_msgs) if (rm.get("from") or {}).get("id") != meta_client.page_id and (rm.get("message") or "").strip()),
                            "[ส่งรูปภาพ]",
                        )
                        asyncio.create_task(asyncio.to_thread(
                            notify_admins_boss_mode,
                            upsert_data["branch"],
                            cust_name,
                            psid,
                            "NEW_CUSTOMER_MSG",
                            last_c_txt,
                            "ลูกค้าทักแชทเข้ามา",
                            "NEW_CONV" if not existing else "EXISTING_CONV",
                            eff_ad_name or "",
                            0,
                        ))

            await asyncio.sleep(1)
        except Exception as e:
            print(f"[PollerLoop] Error: {e}")
            await asyncio.sleep(30)


BKK_TZ = timezone(timedelta(hours=7))
os.environ.setdefault("TZ", "Asia/Bangkok")
if hasattr(time, "tzset"):
    time.tzset()

def _is_unbilled_sale(psid: str, messages: List[Dict[str, Any]]) -> bool:
    """Detect if a sale happened in chat (slip/phone+address/admin confirmation) without an order recorded yet."""
    with get_conn() as conn:
        if conn.execute("SELECT 1 FROM orders WHERE psid = ? LIMIT 1", (psid,)).fetchone():
            return False
    cust_joined = " ".join((m.get("text") or "") for m in messages if m.get("sender_role") == "customer")
    admin_joined = " ".join((m.get("text") or "") for m in messages if m.get("sender_role") in ("admin", "bot"))
    if any(k in admin_joined for k in ("สรุปออเดอร์การสั่งซื้อ", "เปิดบิลแล้ว", "รับยอด", "ทำเครื่องหมายคำสั่งซื้อ")):
        return False
    has_cust_buy = any(k in cust_joined for k in ("โอนแล้ว", "ส่งสลิป"))
    has_phone_addr = bool(re.search(r"0[689]\d[\s\-]?\d{3}[\s\-]?\d{4}", cust_joined)) and any(
        k in cust_joined for k in ("บ้านเลขที่", "ต.", "ตำบล", "อ.", "อำเภอ", "จ.", "จังหวัด", "ซอย", "ถนน")
    )
    has_admin_confirm = any(k in admin_joined for k in ("รับออเดอร์", "จัดส่งให้", "ส่งของให้", "ยอดโอนเรียบร้อย", "ขอบคุณที่อุดหนุน"))
    return has_cust_buy or has_phone_addr or has_admin_confirm


BOT_STARTED_AT = datetime.now(BKK_TZ)


async def followup_loop() -> None:
    """24/7 Slow-Reply Follow-up Daemon: sends 3-Enter follow-up when customer replies slowly."""
    await asyncio.sleep(10)
    while True:
        try:
            if get_bool_setting("auto_pilot_enabled", False):
                now_dt = datetime.now(timezone.utc)
                with get_conn() as conn:
                    rows = conn.execute(
                        "SELECT psid, next_followup_at, last_customer_msg_at FROM conversations WHERE status IN ('WAITING_REPLY') AND next_followup_at IS NOT NULL"
                    ).fetchall()
                    sla_rows = conn.execute(
                        "SELECT psid, customer_name, branch, ad_name, status, last_customer_msg_at FROM conversations WHERE status IN ('HANDOFF', 'HANDOFF_ALERTED', 'OPEN') AND last_customer_msg_at IS NOT NULL"
                    ).fetchall()
                    unbilled_rows = conn.execute(
                        "SELECT psid, customer_name, branch, ad_name, last_customer_msg_at FROM conversations WHERE status IN ('ADMIN_REPLIED', 'WAITING_REPLY', 'HANDOFF', 'HANDOFF_ALERTED', 'HANDOFF_CRITICAL') AND last_customer_msg_at IS NOT NULL"
                    ).fetchall()
                for ur in unbilled_rows:
                    u_dt = parse_iso_dt(ur["last_customer_msg_at"])
                    if not u_dt or u_dt < BOT_STARTED_AT:
                        continue
                    if 180 <= (now_dt - u_dt).total_seconds() <= 86400:
                        u_msgs = get_messages(ur["psid"], limit=10)
                        if _is_unbilled_sale(ur["psid"], u_msgs):
                            last_txt = next((m.get("text", "") for m in reversed(u_msgs) if m.get("sender_role") == "customer"), "")
                            await asyncio.to_thread(
                                notify_admins_boss_mode,
                                ur["branch"] or "ONLINE",
                                ur["customer_name"] or "ลูกค้า",
                                ur["psid"],
                                "UNBILLED_SALE_ALERT",
                                last_txt,
                                "ขายได้แล้วแต่ยังไม่เปิดบิล",
                                "",
                                ur["ad_name"] or "",
                                0,
                            )
                bkk_now = datetime.now(BKK_TZ)
                is_late_night = (bkk_now.hour == 23 and bkk_now.minute >= 30) or (bkk_now.hour < 7) or (bkk_now.hour == 7 and bkk_now.minute < 30)
                for r in rows:
                    due_dt = parse_iso_dt(r["next_followup_at"])
                    if due_dt and due_dt <= now_dt:
                        if is_late_night:
                            # Context-aware late-night rule: if customer is actively chatting (<= 30m ago), keep replying;
                            # if customer has been silent > 30m at night, wait until morning so we never wake sleeping customers!
                            lc_dt = parse_iso_dt(r["last_customer_msg_at"])
                            if not lc_dt or (now_dt - lc_dt).total_seconds() > 1800:
                                continue
                        await process_customer_turn(r["psid"], trigger_type="FOLLOWUP")
                        await asyncio.sleep(2.5)
                if get_bool_setting("sla_nag_enabled", True):
                    for sr in sla_rows:
                        cust_dt = parse_iso_dt(sr["last_customer_msg_at"])
                        if not cust_dt or cust_dt < BOT_STARTED_AT:
                            continue
                        wait_sec = (now_dt - cust_dt).total_seconds()
                        min_wait = 180 if sr["status"] in ("OPEN", "ADMIN_REPLIED") else 120
                        if wait_sec > 1800:
                            # Never nag repeatedly beyond 30 minutes for the same message
                            upsert_conversation({"psid": sr["psid"], "status": "ADMIN_REPLIED"})
                            continue
                        if min_wait <= wait_sec <= 1800:
                            msgs = get_messages(sr["psid"], limit=5)
                            if msgs and msgs[-1].get("sender_role") == "customer":
                                last_sla_txt = (msgs[-1].get("text") or "").strip()
                                low_sla = last_sla_txt.lower()
                                has_real_q_or_order = (
                                    any(k in low_sla for k in ("?", "ไหม", "มั้ย", "รึเปล่า", "เท่าไหร่", "เท่าไร", "กี่", "ไหน", "อะไร", "ยังไง", "เปลี่ยน", "ตำหนิ", "ผิด", "โอน", "ปลายทาง", "ที่อยู่", "เลขบัญชี", "สลิป"))
                                    or bool(re.search(r"\b0[689]\d", low_sla))
                                )
                                # Stop SLA alerts if message is a closing/ending phrase OR waited > 5m without an active question/order cue
                                if _is_closing_or_no_reply_needed(last_sla_txt, msgs) or (wait_sec > 300 and not has_real_q_or_order and len(low_sla) <= 80):
                                    upsert_conversation({"psid": sr["psid"], "status": "ADMIN_REPLIED"})
                                    continue
                                if sr["status"] == "HANDOFF_CRITICAL":
                                    continue
                                wait_min = max(2, int(wait_sec // 60))
                                alert_type = "ADMIN_SLOW_SLA_CRITICAL" if wait_min >= 7 else "ADMIN_SLOW_SLA_1M"
                                await asyncio.to_thread(
                                    notify_admins_boss_mode,
                                    sr["branch"] or "ONLINE",
                                    sr["customer_name"] or "ลูกค้า",
                                    sr["psid"],
                                    alert_type,
                                    msgs[-1].get("text", ""),
                                    f"รอ {wait_min} นาที",
                                    "",
                                    sr["ad_name"] or "",
                                    wait_min,
                                )
                                new_st = "HANDOFF_CRITICAL" if wait_min >= 7 else "HANDOFF_ALERTED"
                                if sr["status"] != new_st:
                                    upsert_conversation({"psid": sr["psid"], "status": new_st})
            await asyncio.sleep(60)
        except Exception as e:
            print(f"[FollowupLoop] Error: {e}")
            await asyncio.sleep(60)


async def learner_loop() -> None:
    """Periodic background learner (every 6 hours)."""
    await asyncio.sleep(90)
    while True:
        try:
            await asyncio.to_thread(learn_from_page_chats, 80)
        except Exception as e:
            print(f"[LearnerLoop] Error: {e}")
        await asyncio.sleep(6 * 3600)


async def self_grill_loop() -> None:
    """Self-audit loop: evaluates outcomes, unanswered timeouts, repetition, and length/return risks."""
    from db import get_messages
    await asyncio.sleep(20)
    while True:
        try:
            now_dt = datetime.now(BKK_TZ)
            convs = list_conversations(limit=100)
            for c in convs:
                psid = c["psid"]
                status = c.get("status")
                if status == "WON":
                    record_self_audit(psid, "WIN", f"Closed order for {c.get('customer_name')}")
                    continue
                if status == "BLACKLISTED":
                    record_self_audit(psid, "BLOCKED_SAFE", f"Auto-stopped safely: {c.get('blacklist_reason')}")
                    continue

                msgs = get_messages(psid, limit=30)
                if not msgs:
                    continue
                last_m = msgs[-1]
                if not last_m.get("is_from_page"):
                    last_txt = (last_m.get("text") or "").lower()
                    last_dt = parse_iso_dt(last_m.get("created_at"))
                    if last_dt and (now_dt - last_dt).total_seconds() >= 900:
                        record_self_audit(psid, "RISK_UNANSWERED", f"Waiting >15m: {last_txt[:60]}")
                    if any(k in last_txt for k in ["ตัดปลายขา", "ตัดขา", "ยาวเกิน", "ส่งคืน", "คืนเงิน"]):
                        record_self_audit(psid, "RISK_LOST_SALE", f"Length/return concern: {last_txt[:60]}")

                bot_prefixes = [
                    (m.get("text") or "").strip()[:30]
                    for m in msgs
                    if m.get("is_from_page") and len((m.get("text") or "").strip()) >= 30
                ]
                if len(bot_prefixes) != len(set(bot_prefixes)):
                    record_self_audit(psid, "WARN_REPEAT", f"Duplicate bot prefix detected in {c.get('customer_name')}")
        except Exception as e:
            print(f"[SelfGrillLoop] Error: {e}")
        await asyncio.sleep(1800)


async def keepalive_loop() -> None:
    """Mutual keepalive ping every 8 min to prevent Render Free idle sleep."""
    import requests as _req
    await asyncio.sleep(45)
    self_url = os.getenv("RENDER_EXTERNAL_URL", "https://jeans-around-ai-chatbot.onrender.com")
    while True:
        for url in (f"{self_url}/api/health", "https://jeans-finance-os-gma9.onrender.com/api/health"):
            try:
                await asyncio.to_thread(_req.get, url, timeout=15)
            except Exception:
                pass
        await asyncio.sleep(480)


async def ads_monitor_loop() -> None:
    """24/7 Meta Ads Spend Watchdog: checks today's spend every 5 min and pauses underperforming Ad Sets."""
    await asyncio.sleep(30)
    while True:
        try:
            dry_run = get_bool_setting("dry_run_mode", False) or (not get_bool_setting("ads_auto_cut_enabled", False))
            res = await asyncio.to_thread(run_ads_monitor_cycle, dry_run)
            if res.get("paused_count"):
                print(f"[AdsMonitor] Paused {res['paused_count']} adsets: {[p['adset_id'] for p in res['paused']]}")
        except Exception as e:
            print(f"[AdsMonitor] Error: {e}")
        await asyncio.sleep(300)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    meta_client.reload_env()
    t1 = asyncio.create_task(poller_loop())
    t2 = asyncio.create_task(followup_loop())
    t3 = asyncio.create_task(learner_loop())
    t4 = asyncio.create_task(self_grill_loop())
    t5 = asyncio.create_task(keepalive_loop())
    t6 = asyncio.create_task(ads_monitor_loop())
    yield
    t1.cancel()
    t2.cancel()
    t3.cancel()
    t4.cancel()
    t5.cancel()
    t6.cancel()


app = FastAPI(title="Jeans Around 24/7 AI Sales Chatbot", lifespan=lifespan)

static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
async def index():
    return FileResponse(os.path.join(static_dir, "index.html"))


@app.get("/api/health")
async def health():
    from brain_3enter import LAST_LLM_STATUS
    return {"status": "ok", "time": utc_now_iso(), "page_id": meta_client.page_id, "llm_status": LAST_LLM_STATUS}


# ---------------- META MESSENGER WEBHOOK ---------------- #

@app.get("/webhook")
async def verify_webhook(
    hub_mode: Optional[str] = Query(None, alias="hub.mode"),
    hub_verify_token: Optional[str] = Query(None, alias="hub.verify_token"),
    hub_challenge: Optional[str] = Query(None, alias="hub.challenge"),
):
    verify_token = os.getenv("FB_VERIFY_TOKEN", "jeans_around_webhook_2026")
    if hub_mode == "subscribe" and hub_verify_token == verify_token:
        return Response(content=hub_challenge or "", media_type="text/plain")
    raise HTTPException(status_code=403, detail="Invalid verify token")


@app.post("/webhook")
async def receive_webhook(request: Request):
    body = await request.json()
    if body.get("object") != "page":
        return {"status": "ignored"}

    for entry in body.get("entry", []):
        for event in entry.get("messaging", []):
            sender_id = (event.get("sender") or {}).get("id")
            if not sender_id or sender_id == meta_client.page_id:
                continue

            msg = event.get("message") or {}
            if msg.get("is_echo"):
                continue

            referral = event.get("referral") or msg.get("referral") or (event.get("postback") or {}).get("referral") or {}
            ads_ctx = referral.get("ads_context_data") or {}
            ad_id = referral.get("ad_id")
            mid = msg.get("mid") or f"wh_{sender_id}_{utc_now_iso()}"
            text = msg.get("text") or ""
            created_at = utc_now_iso()

            if ad_id or ads_ctx:
                ads = list_ad_knowledge()
                matched = next((a for a in ads if a.get("ad_id") == ad_id), None) if ad_id else None
                wh_ad_name = matched.get("ad_name") if matched else ads_ctx.get("ad_title")
                wh_camp = matched.get("campaign_name") if matched else None
                wh_branch = matched.get("branch") if matched else None
                if not matched and ad_id:
                    ad_obj = await asyncio.to_thread(meta_client.fetch_ad_by_id, ad_id)
                    if ad_obj:
                        from grill_engine import detect_branch as _det_wh_branch
                        wh_ad_name = ad_obj.get("name") or wh_ad_name
                        wh_camp = (ad_obj.get("campaign") or {}).get("name")
                        cr = ad_obj.get("creative") or {}
                        wh_branch = _det_wh_branch(cr.get("body") or cr.get("title") or "", wh_ad_name or "", wh_camp or "")
                if (not wh_branch or wh_branch == "ONLINE") and (ads_ctx.get("ad_title") or ads_ctx.get("post_id")):
                    from grill_engine import detect_branch as _det_wh_branch
                    post_cap = await asyncio.to_thread(meta_client.fetch_post_message, ads_ctx.get("post_id") or "")
                    wh_branch = _det_wh_branch(f"{ads_ctx.get('ad_title') or ''} {post_cap}", wh_ad_name or "", wh_camp or "")
                upsert_conversation(
                    {
                        "psid": sender_id,
                        "ad_id": ad_id,
                        "ad_name": wh_ad_name,
                        "campaign_name": wh_camp,
                        "branch": wh_branch,
                    }
                )

            if text:
                if any(mk in text for mk in SYSTEM_ORDER_MARKERS) or any(mk in text for mk in ADMIN_BILL_MARKERS):
                    save_message(mid, sender_id, "admin", text, created_at)
                    upsert_conversation(
                        {
                            "psid": sender_id,
                            "status": "WON",
                            "last_admin_msg_at": created_at,
                            "followup_stage": 0,
                            "next_followup_at": None,
                        }
                    )
                    continue
                save_message(mid, sender_id, "customer", text, created_at)
                existing_wh = get_conversation(sender_id)
                if existing_wh and existing_wh.get("status") == "WON":
                    upsert_conversation({"psid": sender_id, "last_customer_msg_at": created_at})
                    continue
                upsert_conversation(
                    {
                        "psid": sender_id,
                        "status": "OPEN",
                        "last_customer_msg_at": created_at,
                        "followup_stage": 0,
                        "next_followup_at": None,
                    }
                )
                if get_bool_setting("auto_pilot_enabled", False):
                    asyncio.create_task(process_customer_turn(sender_id, trigger_type="INSTANT_REPLY"))

    return {"status": "ok"}


# ---------------- DASHBOARD API ---------------- #

@app.get("/api/status")
async def api_status():
    settings = get_settings()
    convs = list_conversations(limit=500)
    ads = list_ad_knowledge()
    patterns = list_learned_patterns()
    return {
        "page_id": meta_client.page_id,
        "ad_account_id": meta_client.ad_account_id,
        "has_fb_token": bool(meta_client.get_page_token()),
        "has_gemini_key": bool(os.getenv("GEMINI_API_KEY") or settings.get("GEMINI_API_KEY")),
        "auto_pilot_enabled": get_bool_setting("auto_pilot_enabled", False),
        "dry_run_mode": get_bool_setting("dry_run_mode", True),
        "settings": settings,
        "stats": {
            "total_conversations": len(convs),
            "waiting_reply": sum(1 for c in convs if c.get("status") == "WAITING_REPLY"),
            "blacklisted": sum(1 for c in convs if c.get("status") == "BLACKLISTED"),
            "won_orders": sum(1 for c in convs if c.get("status") == "WON"),
            "ads_learned": len(ads),
            "patterns_learned": len(patterns),
        },
    }


class SettingsUpdate(BaseModel):
    auto_pilot_enabled: Optional[bool] = None
    dry_run_mode: Optional[bool] = None
    poll_interval_sec: Optional[int] = None
    followup_delays_min: Optional[str] = None
    max_auto_followups: Optional[int] = None
    gemini_model: Optional[str] = None
    GEMINI_API_KEY: Optional[str] = None
    TELEGRAM_ADMIN_MEW_ID: Optional[str] = None
    TELEGRAM_ADMIN_AM_ID: Optional[str] = None
    TELEGRAM_ADMIN_GIFT_ID: Optional[str] = None


@app.post("/api/settings")
async def api_update_settings(payload: SettingsUpdate):
    data = payload.model_dump(exclude_none=True)
    for k, v in data.items():
        if isinstance(v, bool):
            update_setting(k, "true" if v else "false")
        else:
            update_setting(k, str(v))
    return {"ok": True, "settings": get_settings()}


@app.get("/api/conversations")
async def api_conversations(limit: int = 80):
    return {"conversations": list_conversations(limit=limit)}


@app.get("/api/conversations/{psid}/messages")
async def api_conversation_messages(psid: str):
    return {"conversation": get_conversation(psid), "messages": get_messages(psid, limit=50)}


@app.post("/api/conversations/{psid}/blacklist")
async def api_toggle_blacklist(psid: str, blacklist: bool = True):
    upsert_conversation(
        {
            "psid": psid,
            "status": "BLACKLISTED" if blacklist else "OPEN",
            "blacklist_reason": "Manual dashboard mute" if blacklist else "",
            "next_followup_at": None,
        }
    )
    return {"ok": True}


@app.get("/api/grill-logs")
async def api_grill_logs(limit: int = 50):
    return {"logs": list_grill_logs(limit=limit)}


@app.get("/api/ad-knowledge")
async def api_ad_knowledge():
    return {"ads": list_ad_knowledge(), "patterns": list_learned_patterns()}


@app.get("/api/orders")
async def api_orders(limit: int = 50):
    return {"orders": list_orders(limit=limit)}


@app.get("/api/crm")
async def api_crm(limit: int = 80):
    return {"customers": list_customers_crm(limit=limit), "media": list_media_assets(limit=30), "audits": list_self_audits(limit=30)}


@app.get("/api/telegram/discover-admins")
async def api_discover_admins():
    import requests as req
    tok = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not tok:
        return {"users": [], "error": "Missing TELEGRAM_BOT_TOKEN"}
    try:
        r = req.get(f"https://api.telegram.org/bot{tok}/getUpdates", timeout=10).json()
        seen = {}
        for u in r.get("result", []):
            frm = (u.get("message") or {}).get("from") or {}
            uid = frm.get("id")
            if uid and str(uid) not in seen:
                seen[str(uid)] = {
                    "id": str(uid),
                    "name": f"{frm.get('first_name', '')} {frm.get('last_name', '')}".strip(),
                    "username": frm.get("username", ""),
                }
        return {"users": list(seen.values())}
    except Exception as e:
        return {"users": [], "error": str(e)}


@app.post("/api/learn-now")
async def api_learn_now(limit: int = 400, background: bool = True):
    if background:
        asyncio.create_task(asyncio.to_thread(learn_from_page_chats, limit))
        return {"ok": True, "status": "learning_started", "limit": limit}
    res = await asyncio.to_thread(learn_from_page_chats, limit)
    return {"ok": True, "result": res}


class SimulateRequest(BaseModel):
    customer_name: str = "คุณแอน"
    customer_message: str
    ad_name: str = ""
    campaign_name: str = ""
    is_followup: bool = False
    followup_stage: int = 0
    prior_admin_message: str = ""


@app.get("/api/ads-monitor")
async def api_ads_monitor(dry_run: bool = True):
    return await asyncio.to_thread(run_ads_monitor_cycle, dry_run)


@app.post("/api/simulate")
async def api_simulate(req: SimulateRequest):
    now = utc_now_iso()
    sim_msgs = [{"sender_role": "customer", "text": req.customer_message, "created_at": now}]
    if req.prior_admin_message.strip():
        sim_msgs.append({"sender_role": "admin", "text": req.prior_admin_message.strip(), "created_at": now})

    conv_meta = {
        "psid": "SIM_USER",
        "customer_name": req.customer_name,
        "ad_name": req.ad_name,
        "campaign_name": req.campaign_name,
        "status": "OPEN",
        "followup_stage": req.followup_stage,
    }
    grill = grill_conversation(
        psid="SIM_USER",
        customer_name=req.customer_name,
        messages=sim_msgs,
        conv_meta=conv_meta,
        is_followup=req.is_followup,
    )
    if grill["decision"] != "SEND":
        return {"grill": grill, "bubbles": []}

    bubbles = await asyncio.to_thread(
        generate_3enter_reply,
        req.customer_name,
        grill["branch"],
        grill["intent"],
        sim_msgs,
        grill["already_covered"],
        req.ad_name,
        req.campaign_name,
        req.is_followup,
        req.followup_stage,
    )
    return {"grill": grill, "bubbles": bubbles}
