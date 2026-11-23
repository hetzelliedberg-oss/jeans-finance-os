"""Page Chat & Meta Ads Context Learner for Jeans Around."""

import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List

from db import (
    get_conversation,
    save_message,
    update_setting,
    upsert_ad_knowledge,
    upsert_conversation,
    upsert_customer_crm,
    upsert_learned_pattern,
    upsert_media_asset,
    utc_now_iso,
)
from grill_engine import detect_branch, detect_intent, parse_iso_dt, PHONE_RE
from meta_client import meta_client

SKU_RE = re.compile(r"\b(XRP\s*\d+|AR\s*\d+|JA\s*\d+)\b", re.IGNORECASE)


def _infer_topic(text: str) -> str:
    t = (text or "").lower()
    if "กระโปรง" in t:
        return "กระโปรงยีนส์ปักฉลุ"
    if "เสื้อ" in t:
        return "เสื้อยีนส์"
    if "ขาสั้น" in t:
        return "กางเกงขาสั้น"
    if any(k in t for k in ["2xl", "3xl", "4xl", "ไซส์ใหญ่", "1,100", "1100"]):
        return "ไซส์ใหญ่ 2XL-4XL"
    if any(k in t for k in ["สาขา", "หน้าร้าน", "ขอนแก่น", "โคราช", "อุดร"]):
        return "หน้าร้าน/สาขา"
    return "กางเกงยีนส์ปักฉลุ"


def _extract_geo_hint(adset: Dict[str, Any]) -> str:
    targeting = adset.get("targeting") or {}
    geo = targeting.get("geo_locations") or {}
    parts: List[str] = []
    for key in ("cities", "regions"):
        for loc in geo.get(key) or []:
            if isinstance(loc, dict):
                parts.append(str(loc.get("name") or ""))
    joined = " ".join(parts).lower()
    hints = []
    if any(k in joined for k in ("nakhon ratchasima", "korat", "นครราชสีมา", "โคราช")):
        hints.append("โคราช")
    if any(k in joined for k in ("khon kaen", "ขอนแก่น")):
        hints.append("ขอนแก่น")
    if any(k in joined for k in ("udon thani", "อุดรธานี", "อุดร")):
        hints.append("อุดร")
    # Only pin geo branch when adset targets a SINGLE branch province (nationwide ads remain ONLINE)
    return hints[0] if len(hints) == 1 else ""


def sync_ads_knowledge() -> int:
    ads = meta_client.fetch_ads_metadata(limit=400)
    count = 0
    for ad in ads:
        ad_id = ad.get("id")
        if not ad_id:
            continue
        ad_name = ad.get("name", "")
        campaign_name = (ad.get("campaign") or {}).get("name", "")
        adset = ad.get("adset") or {}
        adset_name = adset.get("name", "")
        geo_hint = _extract_geo_hint(adset)
        creative = ad.get("creative") or {}
        oss = creative.get("object_story_spec") or {}
        oss_msg = (
            (oss.get("link_data") or {}).get("message")
            or (oss.get("video_data") or {}).get("message")
            or (oss.get("photo_data") or {}).get("caption")
            or ""
        )
        body = (creative.get("body") or creative.get("title") or oss_msg or "").strip()
        story_id = (creative.get("effective_object_story_id") or "").strip()
        post_text = ""
        if story_id and len(body) < 120:
            post_text = meta_client.fetch_post_message(story_id)
        full_body = body or post_text
        if post_text and body and post_text not in body:
            full_body = f"{body} | {post_text}"
        branch = detect_branch(f"{full_body} {geo_hint} {adset_name}", ad_name, campaign_name)
        story_tag = f"[STORY:{story_id}]" if story_id else ""
        summary_parts = [p for p in [campaign_name, adset_name, ad_name, geo_hint, story_tag] if p]
        summary = " | ".join(summary_parts)
        if full_body:
            summary += f" — {full_body[:450]}"
        upsert_ad_knowledge(
            ad_id=ad_id,
            ad_name=ad_name,
            campaign_name=campaign_name,
            branch=branch,
            creative_summary=summary,
            top_questions=[],
            winning_replies=[],
        )
        count += 1
    return count


def learn_from_page_chats(conv_limit: int = 200) -> Dict[str, Any]:
    """Fetch recent Page conversations + Meta Ads, ingest messages, and extract winning Q&A patterns."""
    ads_count = sync_ads_knowledge()
    convs = meta_client.fetch_conversations(limit=50, msg_limit=25, max_total=conv_limit)

    ingested_convs = 0
    ingested_msgs = 0
    patterns_learned = 0
    media_learned = 0
    crm_learned = 0
    ad_buckets: Dict[str, List[str]] = defaultdict(list)

    for c in convs:
        conv_id = c.get("id")
        participants = (c.get("participants") or {}).get("data", [])
        cust_p = next((p for p in participants if p.get("id") != meta_client.page_id), None)
        if not cust_p:
            continue
        psid = cust_p.get("id")
        cust_name = cust_p.get("name", "ลูกค้า")

        raw_msgs = list(reversed((c.get("messages") or {}).get("data", [])))
        if not raw_msgs:
            continue
        upd_dt = parse_iso_dt(c.get("updated_time"))
        if upd_dt and (datetime.now(timezone.utc) - upd_dt).total_seconds() <= 900:
            continue

        last_cust_at = None
        last_admin_at = None
        last_msg_id = raw_msgs[-1].get("id")
        all_cust_text = []

        for m in raw_msgs:
            mid = m.get("id")
            from_id = (m.get("from") or {}).get("id")
            role = "admin" if from_id == meta_client.page_id else "customer"
            text = m.get("message") or ""
            created_at = m.get("created_time") or utc_now_iso()

            if role == "customer":
                last_cust_at = created_at
                if text:
                    all_cust_text.append(text)
                ph_m = PHONE_RE.search(text)
                if ph_m:
                    skus_found = [re.sub(r"\s+", "", s).upper() for s in SKU_RE.findall(" ".join(all_cust_text))]
                    upsert_customer_crm(
                        fb_name=cust_name,
                        recipient_name=cust_name,
                        phone=ph_m.group(0).replace(" ", "").replace("-", ""),
                        address=text[:240],
                        last_sku=skus_found[-1] if skus_found else "",
                    )
                    crm_learned += 1
            else:
                last_admin_at = created_at
                atts = (m.get("attachments") or {}).get("data", [])
                for att in atts:
                    im = att.get("image_data") or {}
                    img_url = im.get("url") or ""
                    mime = (att.get("mime_type") or "").lower()
                    w, h = im.get("width") or 0, im.get("height") or 0
                    if not img_url or mime == "image/gif" or ".gif" in img_url.lower() or (w and w < 400):
                        continue
                    own_txt = (text or "").lower()
                    ctx = f"{text or ''} {all_cust_text[-1] if all_cust_text else ''}".lower()
                    # Skip old promo sheets so price flyers don't leak into regular chats
                    if any(k in own_txt for k in ("โละ", "ลดแรง", "690", "850")):
                        continue
                    skus_m = SKU_RE.findall(ctx)
                    sku_tag = re.sub(r"\s+", "", skus_m[-1]).upper() if skus_m else ""
                    if any(k in own_txt for k in ("เซ็นทรัลขอนแก่น", "เซนทรัลขอนแก่น", "ชั้น g")):
                        tag = "BRANCH_KKC"
                    elif any(k in own_txt for k in ("เซ็นทรัลอุดร", "เซนทรัลอุดร", "ชั้น 3")):
                        tag = "BRANCH_UDN"
                    elif any(k in own_txt for k in ("เซ็นทรัลโคราช", "เซนทรัลโคราช", "showcase")):
                        tag = "BRANCH_KORAT"
                    elif "ตารางไซส์" in own_txt:
                        tag = "SIZE_CHART"
                    elif "กระโปรง" in ctx:
                        tag = "SKIRT"
                    elif "ขาม้า" in ctx:
                        tag = "STYLE_FLARE"
                    else:
                        tag = "PRODUCT"
                    upsert_media_asset(tag=tag, url=img_url, sku=sku_tag, title=(text[:60] or tag))
                    media_learned += 1

            if save_message(mid, psid, role, text, created_at):
                ingested_msgs += 1

        existing = get_conversation(psid)
        branch = detect_branch(" ".join(all_cust_text), (existing or {}).get("ad_name") or "", (existing or {}).get("campaign_name") or "")

        upsert_conversation(
            {
                "psid": psid,
                "conv_id": conv_id,
                "customer_name": cust_name,
                "branch": branch,
                "last_customer_msg_at": last_cust_at,
                "last_admin_msg_at": last_admin_at,
                "last_msg_id": last_msg_id,
            }
        )
        ingested_convs += 1

        # Extract Q&A pairs from this conversation (especially winning chats with phone/order!)
        is_won = any(PHONE_RE.search(m.get("message") or "") for m in raw_msgs if (m.get("from") or {}).get("id") != meta_client.page_id)
        win_weight = 3 if is_won else 1

        _bot_sigs = (
            "หนูแนะนำเป็นไซส์",
            "หนูขออนุญาตส่งข้อมูล",
            "ฟอกแล้ว ซักไม่หด",
            "ตอบโจทย์คนกังวล",
            "หน้าร้านของเราอยู่ที่",
            "ข้อความอัตโนมัติ",
            "ขออภัยนะคะ ข้อความซ้ำ",
            "สรุปออเดอร์การสั่งซื้อ",
            "ตอบกลับโฆษณา",
            "ตอบกลับโพสต์",
        )
        for idx in range(len(raw_msgs) - 1):
            m_curr = raw_msgs[idx]
            m_next = raw_msgs[idx + 1]
            curr_from = (m_curr.get("from") or {}).get("id")
            next_from = (m_next.get("from") or {}).get("id")
            if curr_from != meta_client.page_id and next_from == meta_client.page_id:
                q_text = (m_curr.get("message") or "").strip()
                a_text = (m_next.get("message") or "").strip()
                if len(q_text) >= 2 and len(a_text) >= 5 and not any(sig in a_text for sig in _bot_sigs):
                    intent = detect_intent(q_text)
                    topic = _infer_topic(q_text + " " + a_text)
                    upsert_learned_pattern(
                        topic=topic,
                        branch=branch,
                        customer_intent=intent,
                        customer_example=q_text[:200],
                        admin_reply_example=a_text[:350],
                        win_count=win_weight,
                    )
                    patterns_learned += 1
                    ad_buckets[branch].append(q_text[:80])

    update_setting("last_learn_at", utc_now_iso())
    return {
        "ads_synced": ads_count,
        "conversations_scanned": ingested_convs,
        "new_messages_saved": ingested_msgs,
        "patterns_learned": patterns_learned,
        "media_learned": media_learned,
        "crm_learned": crm_learned,
    }
