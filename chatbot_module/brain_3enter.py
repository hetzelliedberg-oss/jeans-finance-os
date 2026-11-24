"""3-Enter Context-Aware AI Response Generator (Master Zero-Key NLU + Optional Gemini)."""

import json
import os
import re
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from db import find_customer_crm, find_media_for_context, get_settings, list_ad_knowledge, list_learned_patterns
from grill_engine import is_auto_ad_greeting_text

BRAND_KNOWLEDGE = """
ร้าน Jeans Around (ยีนส์ อะราวด์) — กางเกงยีนส์ กระโปรงยีนส์ งานปักฉลุพรีเมียม และรุ่นเสื้อใส่เข้าชุด (รวมเซ็ตเสื้อ+กางเกง 1,590 บาท):
- จุดเด่น: ผ้ายีนส์ยืดเนื้อนิ่ม ใส่สบาย ไม่อึดอัด พรางหน้าท้องและสะโพก ยืดหยุ่นได้อีก 1-2 นิ้ว
- สีของสินค้า: กางเกง/กระโปรงแต่ละรุ่นจะมี **สีเดียวตรงตามแบบในรูป** (ห้ามถามลูกค้าว่าชอบสีเข้มหรือสีฟอกสว่าง และห้ามถามจุกจิกหลายคำถามเด็ดขาด)
- ตารางไซส์จริงหน้าร้าน:
  • M: เอว 26–28 / สะโพก 36–38 นิ้ว
  • L: เอว 28–30 / สะโพก 38–40 นิ้ว
  • XL: เอว 30–32 / สะโพก 40–42 นิ้ว
  • 2XL: เอว 32–34 / สะโพก 42–44 นิ้ว
  • 3XL: เอว 34–36 / สะโพก 44–46 นิ้ว
  • 4XL: เอว 38–40 (ยืดเต็มที่ได้ ~41–42) / สะโพก 48–50 นิ้ว (ถ้าลูกค้าเอว >= 43 นิ้วให้แจ้งตรงๆ ว่ายังไม่มีไซส์รองรับ)
- ราคา & บริการเพิ่มเติม:
  • งานขาสั้น / รุ่นโปรเคลียร์ไซส์ 2XL-4XL / รุ่นเพชรแถบเส้นเล็กขากระบอก: 990 หรือ 1,100 บาท | เสื้อแยกตัวละ 590 บาท (มี 2 สี งานใหม่เพิ่งมา; หากลูกค้าสั่งกางเกงก่อนแล้วซื้อเสื้อทีหลังก็ลดราคาเซ็ตให้เหมือนเดิม)
  • กางเกงยีนส์ขายาว / กระโปรงงานปักฉลุละเอียด: 1,290 บาท (ความยาวขายาวมาตรฐาน 39 นิ้ว / ขาบาน 35 นิ้ว — บริการตัดขากางเกงได้)
  • เซ็ตเสื้อ+กางเกงยีนส์: 1,590 บาท | โปรจับคู่ 2 ตัว (รุ่น 1,290): 2,400 บาท | รับ 3 ตัวลดพิเศษ (เช่น 3,570 เหลือ 3,400 บาท)
- การชำระเงิน & จัดส่ง:
  • ส่งฟรี EMS ทั่วไทย + มีบริการเก็บเงินปลายทาง (COD) ไม่บวกเพิ่ม แกะเช็คของก่อนได้
  • ใส่ไม่พอดี เปลี่ยนไซส์ได้สบายใจ
  • รายละเอียดเพิ่มเติมจากลูกค้าจริง: ไม่มีซับในแต่ด้านในเก็บเรียบร้อยผ้านุ่มไม่คัน | ไม่ใช่เอวยางยืดสม็อกแต่เป็นผ้ายีนส์ยืดทั้งตัว | เป้าสูง ~13 นิ้ว ปลายขาหน้าผ้ากว้าง ~10–14 นิ้ว (รอบขา 20–28 นิ้ว) | ปกติเย็บมาจากโรงงาน หากให้จ้างช่างนอกเย็บปลายขาเพิ่มคิดค่าบริการ 50 บาท
- หน้าร้าน 3 สาขาเท่านั้น (เปิดทุกวัน 10:30-21:00 โปรหน้าร้าน: ซื้อ 1 ตัวลด 10%, 2 ตัวลด 20%, ครบ 3,000 แถมเสื้อ 1 ตัว — จังหวัดอื่นเช่น กทม./อุบลฯ ยังไม่มีหน้าร้าน แต่สั่งออนไลน์ส่ง EMS 1-2 วันถึงได้):
  • ขอนแก่น (KKC): เซ็นทรัลขอนแก่น ชั้น G ตรงข้ามแว่นท็อปเจริญ (โทร 082-927-1808)
  • โคราช (KORAT): เซ็นทรัลโคราช ชั้น 1 โซน showcase ติดบันไดเลื่อน ตรงข้ามร้านยืดเปล่า (โทร 098-110-8961)
  • อุดรธานี (UDN): เซ็นทรัลอุดรธานี ชั้น 3 ตรงข้ามร้าน moshi moshi (โทร 093-213-5716)
""".strip()

BRANCH_MAP = {
    "KKC": "เซ็นทรัลขอนแก่น ชั้น G (ตรงข้ามแว่นท็อปเจริญ โทร 082-927-1808)",
    "KORAT": "เซ็นทรัลโคราช ชั้น 1 โซน showcase (ติดบันไดเลื่อน ตรงข้ามร้านยืดเปล่า โทร 098-110-8961)",
    "UDN": "เซ็นทรัลอุดรธานี ชั้น 3 (ตรงข้ามร้าน moshi moshi โทร 093-213-5716)",
    "ONLINE": "ออนไลน์ (ส่งฟรี EMS 1-2 วันถึง / เก็บปลายทาง COD ไม่บวกเพิ่ม)",
}


def _clean_short_name(customer_name: str) -> str:
    raw = (customer_name or "").strip()
    if not raw or raw == "ลูกค้า":
        return ""
    first = raw.split()[0]
    for prefix in ("คุณ", "พี่", "น้อง"):
        if first.startswith(prefix) and len(first) > len(prefix):
            first = first[len(prefix):]
    return first


def _normalize_thai_sizes(text: str) -> str:
    """Normalize Thai phonetic spellings like '4เอ้กแอล', '3เอ็กแอล' into standard XL tokens."""
    t = text or ""
    t = re.sub(r"(?:เอ้กซ์แอล|เอ็กซ์แอล|เอ้กแอล|เอ็กแอล|เอกแอล|เอ้กl|เอ็กl)", "xl", t, flags=re.IGNORECASE)
    t = re.sub(r"(?:ไซส์|ไซด์|เบอร์)\s*แอล\b", "ไซส์ l", t, flags=re.IGNORECASE)
    t = re.sub(r"(?:ไซส์|ไซด์|เบอร์)\s*เอ็ม\b", "ไซส์ m", t, flags=re.IGNORECASE)
    return t


def _extract_body_facts(text: str, last_cust_only: str = "", asked_waist: bool = False) -> Dict[str, Any]:
    raw_t = re.sub(r"\[image:[^\]]+\]|\[sticker\]", " ", (text or "").lower())
    raw_last = re.sub(r"\[image:[^\]]+\]|\[sticker\]", " ", (last_cust_only or "").lower())
    t = _normalize_thai_sizes(raw_t)
    # Strip size-chart range mentions (e.g. "26-42", "26 ถึง 42", "M-4XL") so shop range never triggers M
    t_clean = re.sub(r"\b(?:2[4-9]|3[0-9]|4[0-2])\s*[-–ถึง~]\s*(?:3[0-9]|4[0-4])\b", " ", t)
    last_clean = re.sub(r"\b(?:2[4-9]|3[0-9]|4[0-2])\s*[-–ถึง~]\s*(?:3[0-9]|4[0-4])\b", " ", _normalize_thai_sizes(raw_last))

    w_matches_last = re.findall(r"(?:หนัก|น้ำหนัก)\s*(\d{2,3})|(\d{2,3})\s*(?:กก|กิโล|kg)", last_clean)
    w_matches_all = re.findall(r"(?:หนัก|น้ำหนัก)\s*(\d{2,3})|(\d{2,3})\s*(?:กก|กิโล|kg)", t_clean)
    w_pair = (w_matches_last or w_matches_all)[-1] if (w_matches_last or w_matches_all) else None
    weight = int(w_pair[0] or w_pair[1]) if w_pair else None

    h_matches = re.findall(r"(?:สูง|ส่วนสูง)\s*(\d{3})|(\d{3})\s*(?:ซม|cm)", last_clean) or re.findall(r"(?:สูง|ส่วนสูง)\s*(\d{3})|(\d{3})\s*(?:ซม|cm)", t_clean)
    height = int(h_matches[-1][0] or h_matches[-1][1]) if h_matches else None

    waist_matches = re.findall(r"(?:เอว|รอบเอว)\D{0,18}(\d{2})(?!\d)", last_clean) or re.findall(r"(?:เอว|รอบเอว)\D{0,18}(\d{2})(?!\d)", t_clean)
    waist = int(waist_matches[-1]) if waist_matches else None
    if waist in (62, 63, 72, 73, 82, 83, 92, 93):
        waist = int(str(waist)[::-1])
    elif waist is not None and not (20 <= waist <= 60):
        waist = None
    if waist is None and asked_waist:
        m_bare = re.match(r"^\s*(\d{2})\s*(?:นิ้ว)?\s*$", (last_cust_only or "").strip())
        if m_bare and 20 <= int(m_bare.group(1)) <= 55:
            waist = int(m_bare.group(1))

    hip_matches = re.findall(r"(?:สะโพก|สพ\.?)\D{0,10}(\d{2})(?!\d)", last_clean) or re.findall(r"(?:สะโพก|สพ\.?)\D{0,10}(\d{2})(?!\d)", t_clean)
    hip = int(hip_matches[-1]) if hip_matches and (32 <= int(hip_matches[-1]) <= 62) else None
    hip_too_big = bool(hip and hip >= 53)
    waist_too_big = bool((waist and waist >= 43) or hip_too_big)
    waist_too_small = bool(waist and waist <= 24)

    rec_size = None
    if waist:
        if waist <= 24:
            rec_size = None
        elif waist <= 25:
            rec_size = "M (เอว 26–28 สะโพก 36–38 — อาจหลวมช่วงเอวนิดหน่อยค่ะ)"
        elif waist <= 28:
            rec_size = "M (เอว 26–28 / สะโพก 36–38\")"
        elif waist <= 30:
            rec_size = "L (เอว 28–30 / สะโพก 38–40\")"
        elif waist <= 32:
            rec_size = "XL (เอว 30–32 / สะโพก 40–42\")"
        elif waist <= 34:
            rec_size = "2XL (เอว 32–34 / สะโพก 42–44\")"
        elif waist <= 36 or (waist == 37 and (hip is None or hip <= 46)):
            rec_size = "3XL (เอว 34–36 ยืดได้ 37–38 / สะโพก 44–46\")"
        elif waist <= 40:
            rec_size = "4XL (เอว 38–40 / สะโพก 48–50\")"
        elif waist <= 42:
            rec_size = "4XL (เอวมาตรฐาน 38–40 ยืดเต็มที่ได้ ~41–42\" / สะโพก 48–50\")"
        else:
            rec_size = None

        # Joint waist + hip refinement (learned from real admin sizing; never force M on waist >= 29)
        if hip is not None and 25 <= waist <= 42:
            if hip >= 47 and waist <= 36:
                rec_size = "4XL (เอว 38–40 / สะโพก 48–50\" เผื่อสะโพกใส่สบายไม่อึดอัดค่ะ)"
            elif hip >= 45 and waist <= 34:
                rec_size = "3XL (เอว 34–36 / สะโพก 44–46\" เผื่อสะโพกใส่สบายค่ะ)"
            elif hip >= 43 and waist <= 32:
                rec_size = "2XL (เอว 32–34 / สะโพก 42–44\" เผื่อสะโพกใส่สบายค่ะ)"
            elif hip >= 41 and waist <= 30:
                rec_size = "XL (เอว 30–32 / สะโพก 40–42\" เผื่อสะโพกใส่สบายค่ะ)"
    elif hip:
        if hip <= 38:
            rec_size = "M (สะโพก 36–38\")"
        elif hip <= 40:
            rec_size = "L (สะโพก 38–40\")"
        elif hip <= 42:
            rec_size = "XL (สะโพก 40–42\")"
        elif hip <= 44:
            rec_size = "2XL (สะโพก 42–44\")"
        elif hip <= 47:
            rec_size = "3XL (สะโพก 44–46\")"
        elif hip <= 51:
            rec_size = "4XL (สะโพก 48–50\")"
    elif weight:
        if weight < 53:
            rec_size = "M"
        elif weight <= 59:
            rec_size = "L"
        elif weight <= 66:
            rec_size = "XL"
        elif weight <= 74:
            rec_size = "2XL (หรือ XL หากชอบพอดีทรง)"
        elif weight <= 84:
            rec_size = "3XL"
        else:
            rec_size = "4XL"

    return {
        "weight": weight,
        "height": height,
        "waist": waist,
        "hip": hip,
        "waist_too_big": waist_too_big,
        "waist_too_small": waist_too_small,
        "rec_size": rec_size,
        "wants_plain": any(k in t for k in ["ไม่ปัก", "ไม่เอาลาย", "แบบเรียบ", "สีพื้น", "ไม่มีลาย"]),
        "wants_black": "สีดำ" in t or "ดำล้วน" in t,
        "wants_dark": "สีเข้ม" in t or "ยีนส์เข้ม" in t,
        "wants_light": "สีฟอก" in t or "สีอ่อน" in t or "สีฟ้า" in t,
    }


def _recent_session_messages(messages: List[Dict[str, Any]], hours: int = 18) -> List[Dict[str, Any]]:
    """Restrict thread context to the active conversation session when ISO timestamps are available."""
    if not messages:
        return []
    last_cust_dt = None
    for m in reversed(messages):
        if m.get("sender_role") == "customer" and m.get("created_time"):
            try:
                last_cust_dt = datetime.fromisoformat(str(m["created_time"]).replace("Z", "+00:00"))
                break
            except Exception:
                pass
    if not last_cust_dt:
        return messages
    cutoff = last_cust_dt - timedelta(hours=hours)
    recent: List[Dict[str, Any]] = []
    for m in messages:
        ts = m.get("created_time")
        if not ts:
            recent.append(m)
            continue
        try:
            dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
            if dt >= cutoff:
                recent.append(m)
        except Exception:
            recent.append(m)
    return recent or messages


def _is_dup_bubble(bubble: str, recent_texts: List[str]) -> bool:
    norm = re.sub(r"\s+", "", (bubble or "")).lower()
    if len(norm) < 12:
        return False
    probe = norm[:38]
    for prev in recent_texts or []:
        pnorm = re.sub(r"\s+", "", prev or "").lower()
        if probe in pnorm or (len(pnorm) >= 24 and pnorm[:38] in norm):
            return True
    return False


def _detect_ad_price_label(ad_intro: str, cust_text: str, is_shorts: bool) -> str:
    # Prioritize explicit selling/promo price in right-side ad_intro first, ignoring "ปกติ 1,590" anchor prices
    for src in (ad_intro or "", cust_text or ""):
        cleaned = re.sub(r"ปกติ\s*(?:ราคา\s*)?[12],?\d{3}", "", src)
        m_promo = re.search(
            r"(?:เหลือ|ราคา(?:พิเศษ|โปร)?|ตัวละ|ลดเหลือ|โปรโมชั่น)\D{0,10}(990|1[,]?090|1[,]?100|1[,]?190|1[,]?290|1[,]?590)",
            cleaned,
        )
        if m_promo:
            val = m_promo.group(1).replace(",", "")
            return f"{int(val):,} บาท"
        for num, label in (
            ("990", "990 บาท"),
            ("1,090", "1,090 บาท"), ("1090", "1,090 บาท"),
            ("1,100", "1,100 บาท"), ("1100", "1,100 บาท"),
            ("1,190", "1,190 บาท"), ("1190", "1,190 บาท"),
            ("1,290", "1,290 บาท"), ("1290", "1,290 บาท"),
            ("1,590", "1,590 บาท"), ("1590", "1,590 บาท"),
        ):
            if num in cleaned:
                return label
    return "990 บาท" if is_shorts else "1,290 บาท"


def _is_bot_style_msg(txt: str) -> bool:
    low = (txt or "").lower()
    return any(
        mk in low
        for mk in (
            "จากคลิป/แอดที่พี่ทักเข้ามา",
            "หนูขออนุญาตส่งข้อมูลเพิ่มเติม",
            "เก็บข้อมูลไว้ค่อยตัดสินใจ",
            "ใส่ไม่พอดีทางร้านเปลี่ยนไซส์",
            "ได้รับข้อมูลครบถ้วนแล้วนะคะ",
            "รอบส่งวันนี้ยังทันตัดรอบ",
            "ส่งฟรี ems หรือเก็บเงินปลายทางไม่บวกเพิ่ม",
            "อยากให้หนูจับคู่ลายสวยๆ",
        )
    )


def _extract_saved_address_from_history(messages: List[Dict[str, Any]]) -> str:
    """Scan full conversation history (newest first) to extract a returning customer's real shipping address + phone."""
    if not messages:
        return ""
    shop_exclude = re.compile(r"(093-?213-?5716|082-?927-?1808|098-?110-?8961|752-?0-?60883-?2|กรุงไทย|สุพัตรา|เซ็นทรัล|หน้าร้าน|โปรหน้าร้าน|ลด 10%|ลด 20%)")
    phone_re = re.compile(r"(?:\+66|0)[689]\d[\s-]?\d{3}[\s-]?\d{4}")
    addr_kw = re.compile(r"(หมู่|ม\.|ต\.|ตำบล|อ\.|อำเภอ|จ\.|จังหวัด|ซอย|ซ\.|ถ\.|ถนน|แขวง|เขต|บ้านเลขที่|รหัสไปรษณีย์|\b[1-9]\d{4}\b)")
    for m in reversed(messages):
        txt = (m.get("text") or m.get("message") or "").strip()
        if len(txt) < 22 or shop_exclude.search(txt):
            continue
        role = m.get("sender_role", "")
        # Prefer customer-sent shipping address, or admin/system shipping summary ("จัดส่งไปที่:" / "ผู้รับ:")
        is_cust_addr = (role == "customer") and bool(phone_re.search(txt)) and (bool(addr_kw.search(txt)) or len(txt) >= 32)
        is_admin_summary = (role in ("admin", "bot")) and bool(re.search(r"(จัดส่งไปที่|ผู้รับ\s*:)", txt)) and bool(addr_kw.search(txt))
        if is_cust_addr or is_admin_summary:
            cleaned = re.sub(r"\s+", " ", txt).strip()
            # Trim overly verbose bill headers if admin summary
            cleaned = re.sub(r"^.*?จัดส่งไปที่\s*[:：]?\s*", "", cleaned).strip()
            if len(cleaned) > 190:
                cleaned = cleaned[:187].rstrip() + "..."
            return cleaned
    return ""


def _polish_human_flow(
    bubbles: List[str],
    call_name: str,
    branch: str,
    branch_desc: str,
    already_covered: Dict[str, Any],
    facts: Dict[str, Any],
) -> List[str]:
    """Strip repeated boilerplate across continuing turns so replies sound natural and human."""
    if len(bubbles) < 2:
        return bubbles
    recent_texts = already_covered.get("recent_bot_texts") or []
    short_branch = {"KORAT": "เซ็นทรัลโคราช", "KKC": "เซ็นทรัลขอนแก่น", "UDN": "เซ็นทรัลอุดรธานี"}.get(branch, branch_desc)
    out = list(bubbles)

    # Shorten repeated full branch address on continuing turns
    if branch != "ONLINE" and already_covered.get(f"sent_branch_{branch.lower()}"):
        out = [b.replace(branch_desc, short_branch) for b in out]

    # Replace duplicate or price-spam middle value-add bubble (NEVER repeat price/EMS when already stated!)
    _price_spam = bool(
        already_covered.get("sent_price")
        and any(k in out[1] for k in ("1,290", "ราคาตัวละ", "ราคา 1,", "ส่งฟรี EMS 1–2"))
        and not any(k in (facts.get("_last_cust") or "") for k in ("ราคา", "กี่บาท", "เท่าไหร่", "โปร"))
    )
    _cod_spam = bool(
        already_covered.get("sent_cod")
        and "ปลายทาง" in out[1]
        and "เปลี่ยนไซส์" not in out[1]
        and not any(k in (facts.get("_last_cust") or "") for k in ("ปลายทาง", "cod", "โอน", "จ่าย"))
    )
    if len(out) >= 3 and not out[1].startswith("📍") and (
        _is_dup_bubble(out[1], recent_texts)
        or _price_spam
        or _cod_spam
    ):
        alt_mid = [
            f"ตัวนี้ผ้ายีนส์ยืดนิ่มฟอกแล้ว ซักไม่หด สีไม่ตก ใส่สบายไม่อึดอัดเลยค่ะ{call_name}",
            "งานปักสวยตรงปกมากค่ะ ถ้าใส่ไม่พอดีที่ร้านเปลี่ยนไซส์ได้ค่ะ",
            (f"หน้าร้าน {short_branch} มีห้องลองให้ลองใส่จริง พร้อมโปร 1 ตัวลด 10% / 2 ตัวลด 20% เลยนะคะ" if branch != "ONLINE" else "ทรงนี้เก็บพุงเก็บสะโพกสวยมากค่ะ ใส่แล้วดูเพรียวขึ้นเลย"),
        ]
        for cand in alt_mid:
            if not _is_dup_bubble(cand, recent_texts) and cand not in out:
                out[1] = cand
                break

    # Replace duplicate or already-asked-size closing question
    last_q = out[-1]
    reasks_size = any(k in last_q for k in ("เอว-สะโพก", "เอวประมาณเท่าไหร่", "ใส่เอว"))
    if _is_dup_bubble(last_q, recent_texts) or (already_covered.get("asked_size") and reasks_size):
        rec_sz = facts.get("rec_size")
        alt_q = []
        if rec_sz:
            alt_q.extend([
                f"รับไซส์ {rec_sz} เป็นโอน หรือเก็บปลายทางดีคะ",
                f"ส่งชื่อ-ที่อยู่-เบอร์โทรมาได้เลยค่า",
            ])
        else:
            alt_q.extend([
                f"ปกติ{call_name}ใส่เอวเท่าไหร่แจ้งหนูเช็กไซส์ให้ได้เลยค่า",
                f"ถ้า{call_name}สนใจรับ แจ้งไซส์หรือชื่อ-ที่อยู่-เบอร์โทรจัดส่งไว้ได้เลยค่า",
            ])
        for cand in alt_q:
            if not _is_dup_bubble(cand, recent_texts) and cand not in out:
                out[-1] = cand
                break

    return out


def _is_size_chart_request(text: str) -> bool:
    """Detect Thai size-chart requests including common spelling variants (ไซส์/ไซด์/ตาราง/ขนาด)."""
    t = (text or "").lower()
    return any(
        k in t
        for k in [
            "ตารางขนาด", "ตารางไซ", "ขอตาราง", "ดูตาราง",
            "ขอดูไซ", "ดูไซ", "ขอดูขนาด", "ขยาด", "สัดส่วน",
            "มีไซส์อะไร", "มีไซด์อะไร", "ขนาดไหนบ้าง", "ขอไซ", "รายละเอียดไซ",
        ]
    ) or ("ขนาด" in t and "ขนาดนั้น" not in t)


def _is_english_query(text: str) -> bool:
    """Always reply in 100% Thai only as instructed by the shop owner."""
    return False


def _build_fallback_3enter(
    customer_name: str,
    branch: str,
    intent: str,
    already_covered: Dict[str, Any],
    ad_context: str = "",
    is_followup: bool = False,
    followup_stage: int = 0,
    messages: Optional[List[Dict[str, Any]]] = None,
) -> List[str]:
    short_name = _clean_short_name(customer_name)
    call_name = f"พี่{short_name}" if short_name else "พี่"
    branch_desc = BRANCH_MAP.get(branch, BRANCH_MAP["ONLINE"])
    session_msgs = _recent_session_messages(messages or [], hours=18)
    bill_markers = ("สรุปออเดอร์การสั่งซื้อ", "เปิดบิลแล้ว", "marked the order as", "ทำเครื่องหมายคำสั่งซื้อ", "คุณร้องขอไป")
    last_bill_idx = -1
    for i, m in enumerate(session_msgs):
        if any(mk in (m.get("text") or "") for mk in bill_markers):
            last_bill_idx = i
    if last_bill_idx >= 0 and any(m.get("sender_role") == "customer" for m in session_msgs[last_bill_idx + 1 :]):
        session_msgs = session_msgs[last_bill_idx + 1 :]
    cust_text = " ".join((m.get("text") or "") for m in session_msgs if m.get("sender_role") == "customer").lower()
    ad_intro = " ".join(
        (m.get("text") or "")
        for m in session_msgs[:6]
        if m.get("sender_role") != "bot" and not _is_bot_style_msg(m.get("text") or "")
    ).lower()
    last_cust = next(((m.get("text") or "").lower() for m in reversed(messages or []) if m.get("sender_role") == "customer"), "")
    has_prior_reply = any(
        (m.get("sender_role") == "bot")
        or (
            m.get("sender_role") == "admin"
            and not is_auto_ad_greeting_text(
                m.get("text") or "",
                session_msgs[idx - 1].get("text") or "" if idx > 0 else "",
            )
        )
        for idx, m in enumerate(session_msgs[:-1])
    )
    combined_ctx = f"{cust_text} {ad_intro} {(ad_context or '').lower()}"

    sku_matches = re.findall(r"\b(XRP\s*\d+|AR\s*\d+|JA\s*\d+)\b", combined_ctx, re.IGNORECASE)
    ad_sku = re.sub(r"\s+", "", sku_matches[-1]).upper() if sku_matches else ""

    raw_last_cust = last_cust
    cust_text = _normalize_thai_sizes(cust_text)
    last_cust = _normalize_thai_sizes(last_cust)

    facts_last = _extract_body_facts(last_cust, last_cust_only=last_cust, asked_waist=bool(already_covered.get("asked_size")))
    facts = _extract_body_facts(cust_text, last_cust_only=last_cust, asked_waist=bool(already_covered.get("asked_size")))
    # Strip [sticker], [image:...], and size-chart ranges ("M-4XL", "S-4XL") before extracting customer's picked size
    clean_cust_for_sz = re.sub(r"\[image:[^\]]+\]|\[sticker\]", " ", cust_text)
    clean_cust_for_sz = re.sub(r"(?:[sml]|2?xl)\s*[-–ถึง~]\s*4\s*xl", " ", clean_cust_for_sz, flags=re.IGNORECASE)
    clean_last_for_sz = re.sub(r"\[image:[^\]]+\]|\[sticker\]", " ", last_cust)
    clean_last_for_sz = re.sub(r"(?:[sml]|2?xl)\s*[-–ถึง~]\s*4\s*xl", " ", clean_last_for_sz, flags=re.IGNORECASE)

    # Always respect customer's explicit size pick in latest message first (supports "4xlนะคะ", "รับ1ตัวค่ะ.Lใส่สวยค่ะ", "ไซส์ 2XL")
    customer_picked_size = False
    _sz_pat = (
        r"(?:รับ|เอา|ขอ|สั่ง|เลือก|ใส่|ไซส์|ไซด์|size)\s*[:.]?\s*(4\s*XL|3\s*XL|2\s*XL|XL|L|M)(?![A-Za-z0-9\-–])"
        r"|(?<![A-Za-z0-9])(4\s*XL|3\s*XL|2\s*XL)(?![A-Za-z0-9\-–])"
        r"|(?<![A-Za-z0-9])\.?(XL|L|M)(?=(?:\s|$|ค่ะ|คะ|ค่า|จ้า|นะ|ใส่))"
    )
    m_cust_picks = re.findall(_sz_pat, clean_last_for_sz, re.IGNORECASE) or re.findall(_sz_pat, clean_cust_for_sz, re.IGNORECASE)
    if m_cust_picks:
        last_pick = m_cust_picks[-1]
        picked = re.sub(r"\s+", "", (last_pick[0] or last_pick[1] or last_pick[2])).upper()
        facts["rec_size"] = picked
        facts_last["rec_size"] = picked
        customer_picked_size = True
    ask_model_size = any(k in last_cust for k in ["แม่ค้า", "นางแบบ", "คนใส่"]) and any(k in last_cust for k in ["ไซส์", "ไซด์", "เอว", "เท่าไหร่", "ใส่ไร"])
    is_skirt = "กระโปรง" in combined_ctx or "โปรง" in combined_ctx
    is_shirt = "เสื้อ" in last_cust and "กางเกง" not in last_cust and "กระโปรง" not in last_cust
    is_compliment = (not is_shirt) and any(k in last_cust for k in ["สวย", "น่ารัก", "ปัง", "ดูดี", "เก๋", "ชอบจัง", "ชอบมาก"])
    is_shorts = "ขาสั้น" in combined_ctx
    price_label = _detect_ad_price_label(f"{ad_intro} {(ad_context or '').lower()}", cust_text, is_shorts)
    allow_2400 = (branch == "ONLINE") and (price_label == "1,290 บาท") and (not already_covered.get("sent_2400"))

    pain_thigh_belly = any(k in last_cust for k in ["ต้นขา", "สะโพก", "พุง", "หน้าท้อง", "อึดอัด", "ใส่คับ", "กลัวคับ", "เอวคับ", "ขาคับ", "รัด"])
    pain_price = any(k in last_cust for k in ["แพง", "ลดได้", "ลดอีก", "แรง", "3 ตัว", "4 ตัว", "หลายตัว"])
    ask_bank = any(k in last_cust for k in ["เลขบัญชี", "พร้อมเพย์", "คิวอาร์", "qr", "โอนเงิน", "โอนเข้า"])
    ask_branch_promo = (branch != "ONLINE") and any(k in last_cust for k in ["จัดถึงวันไหน", "มีถึงวันไหน", "ถึงวันไหน", "หมดเขต", "กี่โมง", "เปิดกี่โมง"])
    ask_delivery_time = (not ask_branch_promo) and any(k in last_cust for k in ["กี่วัน", "นานไหม", "ทันไหม", "ถึงวันไหน", "ส่งวันไหน"])
    ask_fabric_care = any(k in last_cust for k in ["หด", "สีตก", "ร้อน", "หนา", "บาง", "ย้วย", "ซัก"])
    ask_exchange = any(k in last_cust for k in ["เปลี่ยนไซส์", "ไม่พอดี", "คืนได้", "ส่งคืน", "เปลี่ยนได้"])
    concern_too_long = any(k in last_cust for k in ["ตัดปลายขา", "ตัดขา", "ตัดต่อขา", "ยาวเกิน", "ขากอง", "ขาจะยาว"])
    ask_size_chart = _is_size_chart_request(last_cust)

    if not is_followup and _is_english_query(raw_last_cust):
        en_price = price_label.replace("บาท", "THB").strip()
        if intent == "ASK_BRANCH" or any(k in last_cust for k in ("where", "shop", "store", "branch", "location", "mall", "bangkok", "address")):
            return [
                "Hi! We have 3 physical stores in Thailand: Central Khon Kaen (G Fl.), Central Korat (1st Fl.), and Central Udon Thani (3rd Fl.).",
                f"We also ship nationwide via free EMS (1–2 days delivery, {en_price}) and support Cash on Delivery (COD) with free size exchange if it doesn't fit!",
                "What is your waist and hip size (in inches)? Would you prefer bank transfer or COD so we can check available stock for you?",
            ]
        if ask_exchange or "exchange" in last_cust:
            return [
                "Yes! You can easily exchange the size if it doesn't fit (just keep the tag attached and unwashed).",
                f"Our stretch embroidered denim is super soft and comfortable (sizes M to 4XL, waist 26–42 inches), priced at {en_price} with free EMS shipping.",
                "What is your waist/hip size, and would you prefer transfer or Cash on Delivery (COD)?",
            ]
        if ask_size_chart or intent == "ASK_SIZE":
            return [
                'Here is our size chart (stretch denim, stretches 1–2 inches): M (Waist 26–28" Hip 36–38") | L (28–30" / 38–40") | XL (30–32" / 40–42") | 2XL (32–34" / 42–44") | 3XL (34–36" / 44–46") | 4XL (38–40" / 48–50").',
                f"Price is {en_price} with free EMS shipping (1–2 days) or Cash on Delivery (COD) at no extra cost.",
                "Which size or waist measurement do you wear, and would you like transfer or COD?",
            ]
        return [
            "Hi! Our premium stretch embroidered denim is available in sizes M–4XL (waist 26–42 inches), soft and comfy.",
            f"Price is {en_price} with free EMS shipping (1–2 days) or Cash on Delivery (COD), plus easy size exchange.",
            "What is your waist and hip size (in inches), and would you prefer transfer or COD?",
        ]

    # -1. Waist >= 43 or Hip >= 53: honest max-size response ONLY when current message mentions out-of-range size
    if not is_followup and facts_last["waist_too_big"]:
        if facts_last.get("waist") and facts_last["waist"] >= 43:
            limit_txt = f"ยังไม่มีถึงเอว {facts_last['waist']} นิ้วค่ะ"
        else:
            limit_txt = "รุ่นนี้สะโพกสูงสุดได้ 50 นิ้ว (4XL) ยังไม่มีถึงขนาดที่พี่แจ้งค่ะ"
        return [
            f"ขออภัยด้วยนะคะ{call_name} รุ่นกางเกงและกระโปรงยีนส์ปักฉลุของร้านเราไซส์ใหญ่สุดจะเป็น 4XL (เอวสูงสุด 40–42 นิ้ว / สะโพกสูงสุด 50 นิ้ว) {limit_txt}",
            f"เกรงว่าใส่แล้วช่วงเอว/สะโพกจะรัดเกินไปไม่สบายตัวนะคะ ขอบคุณ{call_name}มากๆ ที่ทักเข้ามาสอบถามค่ะ",
            f"ถ้าอนาคตร้านเราผลิตรุ่นไซส์ใหญ่พิเศษเพิ่ม หรือพี่ต้องการดูขนาดสำหรับท่านอื่น ทักหาหนูได้ตลอดเลยนะคะ?",
        ]

    # -1b. Waist <= 24: honest min-size response (never tell waist 24 to wear M 26-28!)
    if not is_followup and facts_last["waist_too_small"]:
        return [
            f"ขออภัยด้วยนะคะ{call_name} รุ่นกางเกงและกระโปรงของร้านเราไซส์เล็กสุดจะเป็น M (เอว 26–28 นิ้ว) ค่ะ ถ้าเอว {facts_last['waist']} นิ้วเกรงว่าช่วงเอวจะหลวมไปนะคะ",
            f"ถ้าชอบทรงเอว 26 นิ้วขึ้นไปจะใส่สวยพอดีเก็บหน้าท้องเลยค่ะ (หรือลูกค้านำไปเก็บเอวเพิ่มเล็กน้อยก็ใส่ได้นะคะ)",
            f"ไม่ทราบว่า{call_name}ต้องการดูขนาดสำหรับท่านอื่นที่เอว 26 นิ้วขึ้นไปด้วยไหมคะ หรือให้หนูช่วยแนะนำเพิ่มบอกได้เลยค่ะ?",
        ]

    # -1c. After-sales / in-store purchase confirmation -> warm thank-you & fabric care ONLY (zero re-selling!)
    if not is_followup and intent == "AFTER_SALES_THANKS":
        is_store_purchase = (branch != "ONLINE") or any(
            k in cust_text for k in ["หน้าร้าน", "สาขา", "ไปซื้อ", "ได้เกง", "ลดให้", "ลอง"]
        )
        if is_store_purchase:
            return [
                f"ขอบคุณ{call_name}มากๆ เลยนะคะ ❤️ ดีใจมากเลยค่ะที่แวะมาอุดหนุนที่สาขา และชอบใส่ถูกใจนะคะ",
                "แนะนำซักด้วยมือหรือใส่ถุงถนอมผ้า ตากในที่ร่ม ผ้ายีนส์จะคงทรงสวยและสีสวยนานเลยค่ะ",
                "ใส่สวยๆ ปังๆ นะคะพี่ ไว้โอกาสหน้าอยากดูลายใหม่หรือรุ่นอื่นเพิ่ม แวะมาหรือทักหาหนูได้ตลอดเลยค่ะ 🙏",
            ]
        return [
            f"ขอบคุณ{call_name}มากๆ เลยนะคะ ❤️ ดีใจมากเลยค่ะที่ได้รับสินค้าเรียบร้อยแล้ว และใส่พอดีถูกใจค่ะ",
            "แนะนำซักด้วยมือหรือใส่ถุงถนอมผ้า ตากในที่ร่ม ผ้ายีนส์จะคงทรงสวยและสีสวยนานเลยนะคะ",
            "ไว้โอกาสหน้าอยากดูลายใหม่หรือรุ่นอื่นเพิ่ม ทักหาหนูได้ตลอดเลยนะคะ ขอบคุณอีกครั้งค่ะ 🙏",
        ]

    # -1d. Shipping / parcel tracking inquiry -> polite immediate acknowledgement while escalating to admin
    if not is_followup and intent == "SHIPPING_TRACKING":
        return [
            f"รับเรื่องเช็กสถานะพัสดุให้ด่วนเลยค่ะ{call_name} 🙏",
            "ตอนนี้หนูส่งเรื่องให้แอดมินตรวจสอบเลขพัสดุกับขนส่ง EMS ให้ทันทีเลยนะคะ รอสักครู่นะคะ",
            "ถ้าพี่รีบใช้ใช้งานวันไหนแจ้งไว้ได้เลยค่ะ เดี๋ยวแอดมินรีบเช็กและแจ้งกลับให้ไวที่สุดค่ะ",
        ]

    if not is_followup and ask_model_size:
        e1 = f"{call_name}คะ แม่ค้า/นางแบบในรูปใส่ไซส์ M–L ค่ะ แต่รุ่นนี้ร้านเราผลิตครบไซส์ตั้งแต่ M ถึง 4XL เลยนะคะ (เอว 26–42 นิ้วค่ะ)"
        e2 = (
            f"ผ้ายีนส์ยืดเนื้อนิ่มยืดตามตัวอีก 1–2 นิ้ว ราคาตัวละ {price_label} "
            + (f"แวะลองที่ {branch_desc} ลด 10–20% ได้เลยค่ะ" if branch != "ONLINE" else "ส่งฟรี EMS 1–2 วันถึง และเก็บปลายทางไม่บวกเพิ่มค่ะ")
        )
        e3 = f"ปกติ{call_name}ใส่เอว-สะโพกประมาณเท่าไหร่คะ แจ้งมาให้หนูเทียบไซส์ที่ใส่สวยพอดีตัวให้ได้เลยค่ะ?"
        return [e1, e2, e3]

    # -1e. Customer confirms EXISTING ADDRESS / RECIPIENT NAME (e.g. "ที่อยู่เดิม", "ที่อยู่คุณวาสนา", "ส่งที่เดิม")
    # Scan FULL conversation history to pull & paste their exact saved address + phone!
    _existing_addr_re = re.search(
        r"(ที่อยู่เดิม|ส่งที่เดิม|ใช้ที่อยู่เดิม|ตามที่อยู่เดิม|ที่อยู่เก่า|ส่งตามเดิม|ส่งที่เก่า|ที่อยู่คุณ|ที่อยู่พี่|ที่อยู่แม่|ส่งที่อยู่|เหมือนเดิม)",
        last_cust,
    )
    if not is_followup and _existing_addr_re and not any(k in last_cust for k in ["เปลี่ยน", "แก้", "ผิด", "ไม่ถึง", "ตามของ"]):
        saved_addr = _extract_saved_address_from_history(messages or [])
        rec_sz = facts.get("rec_size")
        has_pay = bool(re.search(r"(ปลายทาง|cod|โอน|พร้อมเพย์)", " ".join(
            [(m.get("text") or m.get("message") or "") for m in session_msgs[-6:] if m.get("sender_role") == "customer"]
        ), re.I))
        if saved_addr:
            e1 = f"ได้เลยค่ะ{call_name} หนูดึงที่อยู่เดิมมาให้แล้วนะคะ"
            e2 = f"📍 {saved_addr}"
            if rec_sz and has_pay:
                e3 = f"ส่งตามที่อยู่นี้ ไซส์ {rec_sz} เลยนะคะ เดี๋ยวเปิดบิลให้เลยค่า"
            elif rec_sz:
                e3 = f"ส่งตามที่อยู่นี้ ไซส์ {rec_sz} รับปลายทางหรือโอนดีคะ"
            else:
                e3 = "ส่งตามที่อยู่นี้นะคะ รับไซส์เดิม โอนหรือปลายทางดีคะ"
            return [e1, e2, e3]
        if rec_sz:
            e1 = f"ได้เลยค่ะ{call_name} ใช้ที่อยู่เดิมเลยนะคะ"
            e2 = f"สรุปไซส์ {rec_sz} ส่งฟรี EMS ค่ะ"
            e3 = (
                "เดี๋ยวให้แอดมินดึงที่อยู่เปิดบิลแพ็กส่งให้เลยนะคะ 🙏"
                if has_pay
                else "รับปลายทางหรือโอนดีคะ เดี๋ยวให้แอดมินเปิดบิลให้เลยค่า"
            )
            return [e1, e2, e3]
        return [
            f"ได้เลยค่ะ{call_name} ใช้ที่อยู่เดิมเลยนะคะ",
            "รอบนี้รับไซส์เดิม หรือไซส์ไหนดีคะ",
            "เอาปลายทางหรือโอนแจ้งหนูได้เลยค่า",
        ]

    # -1f. Short order-ready confirmation when size is ALREADY picked (e.g. "เอาเลย", "จัดเลย", "ได้ค่ะ", "ตกลง")
    if (
        not is_followup
        and facts.get("rec_size")
        and re.match(r"^(?:เอาเลย|จัดเลย|รับเลย|สั่งเลย|ได้ค่ะ|ได้คะ|ได้จ้า|โอเค|ok|ตกลง|ค่ะ|คะ|ค่า|จ้า)[!.\s🙏❤️👍]*$", last_cust.strip(), re.I)
    ):
        rec_sz = facts["rec_size"]
        return [
            f"ได้เลยค่ะ{call_name} ล็อกไซส์ {rec_sz} ไว้ให้เลยนะคะ",
            "ส่งชื่อ-ที่อยู่-เบอร์โทรมาได้เลยค่ะ",
            "รับโอนหรือปลายทางดีคะ",
        ]

    # 0. Multi-fact intelligent response (ONLY if not already recommended in recent bot messages, and never on COD/address/length-concern turns)
    recent_bot_joined = " ".join(already_covered.get("recent_bot_texts", []))
    already_recommended_size = "หนูแนะนำเป็นไซส์" in recent_bot_joined
    ask_cod_or_pay = any(k in last_cust for k in ["ปลายทาง", "cod", "โอน", "เลขบัญชี", "พร้อมเพย์"])
    def _pick_var(variants: List[str], salt: str = "") -> str:
        recent_b = already_covered.get("recent_bot_texts") or []
        fresh = [v for v in variants if not _is_dup_bubble(v, recent_b)] or variants
        idx = sum(ord(ch) for ch in f"{customer_name}:{last_cust}:{salt}") % len(fresh)
        return fresh[idx]

    has_cust_measurements = bool(customer_picked_size or facts.get("waist") or facts.get("hip") or facts.get("weight"))
    if (
        not is_followup
        and (
            (has_cust_measurements and (facts_last["rec_size"] or (facts["rec_size"] and not already_recommended_size)))
            or facts["wants_plain"]
            or facts["wants_black"]
        )
        and not (already_recommended_size and not facts_last["waist"] and not facts_last["weight"] and not customer_picked_size)
        and intent not in {"ASK_WAIST_RISE", "ASK_COLOR_LENGTH", "ASK_STYLE_FIT", "ASK_BRANCH", "ASK_COD"}
        and not (branch != "ONLINE" and any(k in last_cust for k in ["หน้าร้าน", "สาขา", "อยู่ไหน", "อยู่ตรงไหน", "พิกัด", "แผนที่"]))
        and not any([ask_size_chart, ask_bank, ask_exchange, concern_too_long, ask_delivery_time, ask_fabric_care, ask_cod_or_pay])
    ):
        parts_e1 = []
        if facts["rec_size"] and has_cust_measurements:
            stat_txt = []
            if facts["height"]:
                stat_txt.append(f"สูง {facts['height']}")
            if facts["weight"]:
                stat_txt.append(f"หนัก {facts['weight']} กก.")
            if facts["waist"]:
                stat_txt.append(f"เอว {facts['waist']}")
            if facts.get("hip"):
                stat_txt.append(f"สะโพก {facts['hip']}")
            stat_label = " ".join(stat_txt)
            if customer_picked_size and not stat_txt:
                parts_e1.append(_pick_var([
                    f"{call_name}คะ รับเป็นไซส์ {facts['rec_size']} นะคะ (ผ้ายีนส์ยืดนิ่ม ยืดหยุ่นได้อีก 1–2 นิ้ว)",
                    f"ได้เลยค่ะ{call_name} ไซส์ {facts['rec_size']} มีของพร้อมส่งเลยนะคะ ผ้ายืดนิ่มใส่สบายค่ะ",
                    f"รับทราบไซส์ {facts['rec_size']} นะคะ{call_name} รุ่นนี้ผ้ายืดนิ่มเก็บทรงสวย ใส่สบายไม่อึดอัดค่ะ",
                ], "pick"))
            elif stat_label:
                parts_e1.append(_pick_var([
                    f"{call_name}คะ จาก{stat_label} หนูแนะนำเป็นไซส์ {facts['rec_size']} จะใส่สบายพอดีตัวที่สุดเลยค่ะ (ผ้ายีนส์ยืดนิ่ม ยืดหยุ่นได้อีก 1–2 นิ้ว)",
                    f"จาก{stat_label} ใส่ไซส์ {facts['rec_size']} กำลังสวยพอดีเลยค่ะ{call_name} เนื้อผ้ายีนส์ยืดตามตัวได้อีก 1–2 นิ้วไม่อึดอัดค่ะ",
                    f"{call_name}ใส่ไซส์ {facts['rec_size']} ได้พอดีเลยนะคะรุ่นนี้ จาก{stat_label}ผ้ายืดนิ่มเก็บทรงสวย ใส่แล้วดูเพรียวเลยค่ะ",
                    f"สัดส่วน{stat_label} หนูเทียบให้เป็นไซส์ {facts['rec_size']} นะคะ{call_name} ตัวนี้ผ้ายีนส์ยืดนิ่มใส่สบายค่ะ",
                ], "stat"))
            if facts["height"] and facts["height"] <= 158 and not is_skirt and not is_shorts:
                parts_e1.append("ช่วงความยาวขายาวประมาณ 38–39 นิ้ว สามารถพับปลายขาหรือตัดขาให้พอดีทรงสวยได้ค่ะ")
        if facts["wants_plain"] or facts["wants_black"]:
            if facts["wants_plain"] and not facts["wants_black"]:
                parts_e1.append("รุ่นเรียบไม่ปักลายเลยที่ร้านยังไม่มีนะคะพี่ จุดเด่นของร้านเราจะเป็นงานยีนส์ปักฉลุทั้งหมดเลยค่ะ (แต่มีรุ่นปักลายน้อยๆ ดูเรียบหรูสุภาพด้วยนะคะ)")
            elif facts["wants_black"]:
                parts_e1.append("โทนสีดำ/ยีนส์เข้ม ที่ร้านมีรุ่นปักฉลุลายน้อยๆ ดูเรียบหรูสุภาพ เดี๋ยวหนูให้แอดมินคัดรูปงานจริงส่งเทียบให้ชมนะคะ")

        e1 = " ".join(parts_e1)
        e2 = (
            _pick_var([
                f"ราคาตัวละ {price_label} ส่งฟรี EMS 1–2 วันถึง หรือเก็บเงินปลายทางไม่บวกเพิ่ม และถ้าใส่ไม่พอดีสามารถเปลี่ยนไซส์ได้ค่ะ",
                f"ตัวนี้ราคา {price_label} ส่งฟรี EMS ถึงบ้านเลยค่ะ เก็บปลายทางไม่บวกเพิ่ม แกะเช็คหน้าบ้านก่อนจ่ายได้ด้วยนะคะ",
                f"งานตรงปก 100% ราคาตัวละ {price_label} ส่งฟรี EMS / เก็บเงินปลายทางไม่บวกเพิ่ม ใส่ไม่ได้เปลี่ยนไซส์ได้ค่ะ",
            ], "e2_sz")
            if branch == "ONLINE"
            else f"ราคาตัวละ {price_label} ส่งฟรี EMS 1–2 วันถึง หรือเก็บเงินปลายทางไม่บวกเพิ่ม (แวะลองที่ {branch_desc} ลด 10–20% ได้เลยค่ะ)"
        )
        if is_skirt:
            e3 = (
                f"มีของพร้อมส่งเลยนะคะ รับกระโปรงไซส์ {facts['rec_size']} เป็นโอนส่งฟรี EMS หรือเก็บเงินปลายทางดีคะ ส่งชื่อ-ที่อยู่-เบอร์โทรมาได้เลยค่า?"
                if facts.get("rec_size")
                else f"{call_name}ชอบกระโปรงทรงเอไลน์ยาวประมาณคลุมเข่า หรือยาวพอดีข้อเท้าดีคะ เดี๋ยวหนูคัดรุ่นสวยๆ ส่งรูปให้ชมค่ะ?"
            )
        elif is_shorts:
            e3 = (
                f"มีของพร้อมส่งเลยนะคะ รับขาสั้นไซส์ {facts['rec_size']} เป็นโอนส่งฟรี EMS หรือเก็บเงินปลายทางดีคะ ส่งชื่อ-ที่อยู่-เบอร์โทรมาได้เลยค่า?"
                if facts.get("rec_size")
                else f"{call_name}ชอบกางเกงขาสั้นความยาวประมาณเหนือเข่านิดหน่อย หรือคลุมเข่าดีคะ เดี๋ยวหนูคัดรุ่นที่ตรงใจส่งรูปให้ชมค่ะ?"
            )
        elif facts.get("rec_size") and not facts["wants_plain"]:
            if branch != "ONLINE":
                short_branch = {"KORAT": "เซ็นทรัลโคราช", "KKC": "เซ็นทรัลขอนแก่น", "UDN": "เซ็นทรัลอุดรธานี"}.get(branch, branch_desc)
                e3 = (
                    f"ที่{short_branch}มีพร้อมลอง หรือถ้าไม่สะดวกแวะรับจัดส่งฟรี EMS / เก็บเงินปลายทางได้เลยค่ะ "
                    f"รับไซส์ {facts['rec_size']} เป็นโอน ปลายทาง หรือแวะลองที่สาขาดีคะ?"
                )
            else:
                e3 = (
                    f"มีของพร้อมส่งเลยนะคะ รับไซส์ {facts['rec_size']} เป็นโอนส่งฟรี EMS หรือเก็บเงินปลายทางดีคะ "
                    f"ส่งชื่อ-ที่อยู่-เบอร์โทรมาได้เลยค่า?"
                )
        else:
            e3 = (
                f"{call_name}ชอบทรงขากระบอกเล็กเก็บทรง หรือทรงปล่อยใส่สบายๆ มากกว่ากันคะ เดี๋ยวหนูคัดรุ่นที่ตรงใจส่งรูปให้ชมค่ะ?"
                if not facts["wants_plain"]
                else f"{call_name}ดูเป็นขายาวเรียบๆ หรือมีดีเทลกระเป๋าดีคะ เดี๋ยวส่งรูปให้เลือกค่ะ"
            )
        return [e1, e2, e3]

    # 1. Proactive Slow-Reply Follow-ups (3-Enter: บอกเล่า + บอกเล่า + ตั้งคำถาม, context-matched to Ad/SKU/Branch, anti-spam!)
    if is_followup:
        recent_texts = already_covered.get("recent_bot_texts", [])
        base_fup_item = "กระโปรงยีนส์ปักฉลุ" if is_skirt else ("กางเกงยีนส์ขาสั้น" if is_shorts else "กางเกงยีนส์ปักฉลุ")
        item_label = f"{base_fup_item} ({ad_sku})" if ad_sku else base_fup_item
        if branch != "ONLINE":
            short_branch = {"KORAT": "เซ็นทรัลโคราช", "KKC": "เซ็นทรัลขอนแก่น", "UDN": "เซ็นทรัลอุดร"}.get(branch, branch_desc)
            stages = [
                [
                    f"{call_name}คะ ตัวที่ดูไว้ที่{short_branch}มีของน้า",
                    "แวะมาลองวันไหนดีคะ",
                    "แจ้งเอวไว้ให้หนูเก็บไซส์ให้ได้ค่า",
                ],
                [
                    f"หน้าร้าน{short_branch}มีห้องลองให้ชิลๆ น้า",
                    "โปร 1 ตัวลด 10% ซื้อ 2 ตัวลด 20% ค่า",
                    f"ปกติ{call_name}ใส่เอวเท่าไหร่เอ่ย",
                ],
                [
                    "ผ้าตัวนี้ยืดนิ่มซักไม่หดสีไม่ตกน้า",
                    f"ที่{short_branch}มีหลายทรงให้ลองเทียบเลย",
                    "ชอบทรงกระบอกหรือขาม้าดีคะ",
                ],
                [
                    f"{call_name}คะ ถ้ายังไม่สะดวกแวะ{short_branch}",
                    "สั่งออนไลน์ส่งฟรี EMS ถึงบ้านได้น้า",
                    "มีปลายทางไม่บวกเพิ่ม เปลี่ยนไซส์ได้ค่า",
                ],
                [
                    f"ไซส์ฮิตที่{short_branch}กำลังขายดีเลยน้า",
                    "กลัวแวะมาแล้วไซส์หมดก่อนค่ะ",
                    "บอกไซส์ให้หนูเช็กไซส์ไว้ให้ก่อนได้ค่า",
                ],
                [
                    f"{short_branch}มีโปรคู่ 2 ตัวลด 20% คุ้มมากน้า",
                    "หยิบคู่กระโปรงหรืออีกสีสลับใส่ได้เลย",
                    "แวะมาวันไหนทักบอกหนูได้เลยค่า",
                ],
                [
                    f"{call_name}คะ เผื่อวันว่างแวะมาลองที่ร้านได้น้า",
                    f"เปิดทุกวัน 10:30–21:00 ที่{short_branch}ค่า",
                    "อยากดูรุ่นไหนเพิ่มทักบอกหนูได้ตลอดน้า",
                ],
                [
                    f"{call_name}คะ หนูไม่รบกวนแล้วน้า",
                    "ว่างวันไหนแวะมาลองหรือทักมาได้ตลอดเลย",
                    "ขอบคุณมากๆ ค่า 🙏",
                ],
            ]
        else:
            rec_sz = facts.get("rec_size") or ""
            sz_phrase = f"ไซส์ {rec_sz}" if rec_sz else "ตัวนี้"
            stages = [
                [
                    f"ยังสนใจมั้ยคะ{call_name} {sz_phrase}พร้อมส่งน้า",
                    f"ราคา {price_label} ส่งฟรีมีปลายทางค่ะ",
                    f"รับ{sz_phrase}โอนหรือปลายทางดีคะ" if rec_sz else f"ปกติ{call_name}ใส่เอวเท่าไหร่คะ",
                ],
                [
                    "กำลังแพ็กของตัดรอบส่งวันนี้เลยน้า",
                    "ของตรงปกแกะเช็กหน้าบ้านได้ เปลี่ยนไซส์ได้ค่ะ",
                    f"รับ{sz_phrase}ส่งรอบนี้เลยไหมคะ" if rec_sz else "บอกเอวมาเดี๋ยวหนูเช็กไซส์ส่งวันนี้ให้ค่า",
                ],
                [
                    f"{call_name}คะ เก็บปลายทางไม่บวกเพิ่มน้า",
                    "ใส่ไม่พอดีที่ร้านเปลี่ยนไซส์ได้ค่ะ",
                    f"ส่งชื่อที่อยู่เบอร์โทรให้หนูจอง{sz_phrase}เลยไหมคะ",
                ],
                [
                    "รอบนี้คนรับคู่ 2 ตัวเยอะมากเลยน้า",
                    "โปร 2 ตัวเหลือ 2,400 ส่งฟรีคุ้มกว่าเยอะค่ะ" if allow_2400 else "ส่งฟรี EMS 1-2 วันถึงหน้าบ้านเลยค่ะ",
                    f"รับ{sz_phrase}กี่ตัวดีแจ้งหนูได้เลยค่า",
                ],
                [
                    "ผ้าตัวนี้ยืดนิ่มเก็บพุงดีไม่อึดอัดเลยน้า",
                    "ลูกค้าใส่แล้วกลับมาซื้อซ้ำกันเยอะมากค่ะ",
                    f"ให้หนูล็อก{sz_phrase}ไว้ให้เลยไหมคะ",
                ],
                [
                    f"แจ้งเผื่อไว้หน่อยน้า {sz_phrase}เหลือไม่กี่ตัวแล้ว",
                    "กลัวรอบนี้หมดต้องรอล็อตหน้านานค่ะ",
                    "รับโอนหรือปลายทางแจ้งชื่อที่อยู่ได้เลยค่า",
                ],
                [
                    f"{call_name}คะ เผื่อยังลังเลเรื่องไซส์หรือสีอยู่",
                    "บอกเอวสะโพกมาให้หนูช่วยเทียบเป๊ะๆ ได้น้า",
                    "ไม่ซื้อไม่เป็นไรทักคุยกันได้ค่า",
                ],
                [
                    f"{call_name}คะ หนูไม่รบกวนแล้วน้า",
                    "พร้อมรับวันไหนทักหาหนูได้ตลอดเลยค่ะ",
                    "ขอบคุณมากๆ ค่า 🙏",
                ],
            ]
        start_idx = max(0, followup_stage)
        has_known_waist = bool(facts.get("waist") or facts.get("rec_size"))
        has_known_weight = bool(facts.get("weight"))
        for cand_idx in range(start_idx, len(stages)):
            cand = stages[cand_idx]
            cand_joined = " ".join(cand)
            if has_known_waist and ("ใส่เอว" in cand_joined or "เอวหรือสะโพก" in cand_joined or "เทียบไซส์พอดีตัว" in cand_joined):
                continue
            if (has_known_weight or has_known_waist) and "น้ำหนัก-ส่วนสูง" in cand_joined:
                continue
            if already_covered.get("sent_2400") and "2,400" in cand_joined:
                continue
            if not _is_dup_bubble(cand[0], recent_texts):
                return cand
        return []

    # Helper for high-converting closing question (varied phrasing, never copy-pasted)
    def _close_e3(default_ask_waist: str) -> str:
        rec = facts.get("rec_size")
        if rec and branch == "ONLINE":
            return _pick_var([
                f"รับไซส์ {rec} โอนหรือปลายทางดีคะ ส่งที่อยู่ได้เลยน้า",
                f"ไซส์ {rec} พร้อมส่งวันนี้ค่ะ เอาโอนหรือปลายทางดีคะ",
                f"จัดไซส์ {rec} เลยไหมคะ แจ้งชื่อที่อยู่เบอร์โทรได้เลยค่า",
            ], "close_onl")
        if rec and branch != "ONLINE":
            sb = {"KORAT": "โคราช", "KKC": "ขอนแก่น", "UDN": "อุดร"}.get(branch, branch_desc)
            return f"รับไซส์ {rec} แวะลองที่{sb}หรือให้ส่งฟรีดีคะ"
        return default_ask_waist

    if ask_bank and not is_followup:
        e1 = f"ได้ค่ะ{call_name} ที่ร้านรองรับทั้งโอนชำระและเก็บเงินปลายทาง (COD) ส่งฟรี EMS เหมือนกันค่ะ (เดี๋ยวหนูให้แอดมินส่งเลขบัญชี/QR ให้ในแชทนี้ได้เลยนะคะ)"
        e2 = (
            f"ยอดปกติตัวละ {price_label} (โปรจับคู่ 2 ตัว 2,400 บาทค่ะ) โอนเสร็จส่งสลิปพร้อมชื่อ-ที่อยู่-เบอร์โทรได้เลย"
            if allow_2400
            else f"ตัวละ {price_label} ส่งฟรี EMS โอนเสร็จส่งสลิปพร้อมชื่อ-ที่อยู่-เบอร์โทรได้เลยค่ะ"
        )
        e3 = f"รอบนี้{call_name}รับเป็นรุ่นไหน ไซส์อะไรดีคะ เดี๋ยวหนูสรุปยอดสุทธิให้ค่ะ?"
        return [e1, e2, e3]

    if ask_branch_promo and not is_followup:
        e1 = f"{call_name}คะ สาขา {branch_desc} เปิดให้บริการทุกวัน 10:30–21:00 น. เลยค่ะ สินค้ารุ่นงานปักฉลุมีให้ลองครบไซส์ M–4XL ค่ะ"
        e2 = "โปรหน้าร้านตอนนี้ซื้อ 1 ตัวลด 10%, 2 ตัวลด 20% และซื้อครบ 3,000 บาทแถมฟรีเสื้อยืด 1 ตัวด้วยนะคะ"
        e3 = f"{call_name}วางแผนแวะมาช่วงวันไหน หรือใส่เอวประมาณเท่าไหร่คะ เดี๋ยวหนูเช็กไซส์ที่สาขาไว้ให้ค่า?"
        return [e1, e2, e3]

    if ask_delivery_time and not is_followup:
        e1 = f"{call_name}คะ ที่ร้านส่งด่วน EMS ทุกวันค่ะ กทม./อีสานรอประมาณ 1–2 วันถึง ต่างจังหวัดประมาณ 2–3 วันถึงค่ะ"
        e2 = "ส่งฟรีไม่มีค่าส่งเพิ่ม และเก็บเงินปลายทางได้ไม่ต้องบวกเพิ่มด้วยนะคะ"
        e3 = _close_e3(f"รับกี่ตัวดีคะ{call_name} เอวเท่าไหร่ เอาโอนหรือปลายทางส่งที่อยู่มาได้เลยค่า")
        return [e1, e2, e3]

    if ask_fabric_care and not is_followup:
        e1 = f"{call_name}คะ ผ้ายีนส์ยืดของร้านเป็นผ้าฟอกนิ่มใส่สบาย ระบายอากาศดีไม่ร้อน ผ่านการฟอกแล้วซักไม่หดและสีไม่ตกค่ะ"
        e2 = "ใส่ไปนานๆ ผ้ายังอยู่ทรงเก็บหน้าท้องได้ดี ไม่ย้วยง่าย และใส่ไม่พอดีเปลี่ยนไซส์ได้ค่ะ"
        e3 = _close_e3(f"มีของพร้อมส่งเลยนะคะ ปกติ{call_name}ใส่เอวเท่าไหร่คะ รับโอนหรือเก็บเงินปลายทางดีคะ?")
        return [e1, e2, e3]

    if concern_too_long and not is_followup:
        e1 = f"เข้าใจเลยค่ะ{call_name} ถ้าไม่อยากตัดปลายขาทิ้งลายปัก ที่ร้านมีรุ่นความยาว 35–37 นิ้ว (ทรงขา 8–9 ส่วน) ที่ใส่พอดีสำหรับคนตัวเล็กด้วยนะคะ"
        e2 = (
            f"เดี๋ยวหนูแจ้งแอดมินคัดรูปรุ่นความยาวสั้นที่พร้อมส่งตรงตามไซส์ส่งให้{call_name}เลือกเทียบดูก่อนเลยค่ะ"
            + (f" (หรือแวะลองใส่เทียบความยาวจริงที่ {branch_desc} ได้เลยนะคะ)" if branch != "ONLINE" else "")
        )
        e3 = f"ปกติ{call_name}สูงประมาณเท่าไหร่ และอยากได้ความยาวประมาณกี่นิ้วคะ หนูจะได้ให้แอดมินส่งรุ่นที่ใส่สวยไม่กองให้ทันทีเลยค่ะ?"
        return [e1, e2, e3]

    if ask_exchange and not is_followup:
        e1 = f"{call_name}คะ รับรองใส่ได้ค่ะ และถ้าลองแล้วไม่พอดี สามารถส่งเปลี่ยนไซส์กับที่ร้านได้เลยค่ะ (มีหน้าร้านจริง ของตรงปกค่ะ)"
        e2 = f"ราคา {price_label} ส่งฟรี EMS 1–2 วันถึง หรือเก็บเงินปลายทางไม่บวกเพิ่มค่ะ"
        e3 = _close_e3(f"ปกติ{call_name}ใส่เอวเท่าไหร่คะ รับโอนหรือเก็บเงินปลายทางดีคะ เดี๋ยวหนูเช็กไซส์พร้อมส่งให้เลยค่ะ?")
        return [e1, e2, e3]

    if pain_price:
        e1 = f"เข้าใจเลยค่ะ{call_name} รุ่นนี้เป็นงานปักฉลุละเอียดบนผ้ายีนส์ยืดนิ่ม ตัดเย็บเก็บทรงเฉพาะของร้านเรา ใส่แล้วอยู่ทรงสวยนานไม่ย้วยค่ะ"
        e2 = (
            f"ตอนนี้ราคา {price_label} ส่งฟรี EMS "
            + (f"หรือแวะหน้าร้าน {branch_desc} ซื้อ 1 ตัวลด 10% / 2 ตัวลด 20% นะคะ" if branch != "ONLINE" else ("และถ้าจับคู่ 2 ตัวเหลือเพียง 2,400 บาท (ตกตัวละ 1,200) คุ้มกว่ามากค่ะ" if allow_2400 else "เก็บปลายทางไม่บวกเพิ่มและเปลี่ยนไซส์ได้ค่ะ"))
        )
        e3 = _close_e3(f"ปกติ{call_name}ใส่เอวเท่าไหร่คะ รับแบบไหนดีคะ เดี๋ยวหนูดูตัวที่โปรคุ้มที่สุดพร้อมส่งให้เลยค่ะ?")
        return [e1, e2, e3]

    if ask_size_chart:
        e1 = (
            f"{call_name}คะ ตารางไซส์รุ่นนี้ค่ะ (ผ้ายีนส์ยืดนิ่ม ยืดได้อีก 1–2 นิ้ว)\n"
            f"M : เอว 26–28\" สะโพก 36–38\"\n"
            f"L : เอว 28–30\" สะโพก 38–40\"\n"
            f"XL : เอว 30–32\" สะโพก 40–42\"\n"
            f"2XL : เอว 32–34\" สะโพก 42–44\"\n"
            f"3XL : เอว 34–36\" สะโพก 44–46\"\n"
            f"4XL : เอว 38–40\" สะโพก 48–50\""
        )
        e2 = (
            f"ของพร้อมส่งราคาตัวละ {price_label} "
            + (
                f"(โปรหน้าร้าน {branch_desc}: 1 ตัวลด 10%, 2 ตัวลด 20%)"
                if branch != "ONLINE"
                else (
                    "ส่งฟรี EMS 1–2 วันถึง / เก็บปลายทางไม่บวกเพิ่ม สินค้าตรงปก แกะเช็คของหน้าบ้านก่อนจ่ายได้ ใส่ไม่พอดีเปลี่ยนไซส์ได้ค่ะ (โปรคู่ 2 ตัว 2,400 บาทค่ะ)"
                    if allow_2400
                    else "ส่งฟรี EMS 1–2 วันถึง / เก็บปลายทางไม่บวกเพิ่ม สินค้าตรงปก แกะเช็คของหน้าบ้านก่อนจ่ายได้ ใส่ไม่พอดีเปลี่ยนไซส์ได้ค่ะ"
                )
            )
        )
        e3 = _close_e3(f"{call_name}รับเป็นไซส์ไหนดีคะ หรือบอกเอว-สะโพกพร้อมชื่อ ที่อยู่ เบอร์โทร ให้แอดมินทำออเดอร์แพ็กส่งรอบวันนี้ได้เลยค่ะ?")
        return [e1, e2, e3]

    if intent == "ASK_WAIST_RISE":
        if any(k in last_cust for k in ["เอวต่ำ", "เอวกลาง", "เอวปกติ"]):
            e1 = f"{call_name}คะ รุ่นส่วนใหญ่ของร้านเราจะเป็นทรงเอวสูงเก็บพุงเหนือสะดือเล็กน้อยค่ะ ยังไม่ค่อยมีรุ่นเอวต่ำมากนักนะคะ ถ้าชอบใส่สบายไม่รัด อาจขยับเผื่อ 1 ไซส์หรือมาลองทรงที่สาขาได้เลยค่ะ"
        else:
            e1 = f"{call_name}คะ รุ่นนี้เป็นทรงเอวสูงเก็บทรง (ระดับสะดือพอดี) ช่วยเก็บหน้าท้องและไม่รั้งเป้าเวลานั่งค่ะ ผ้ายีนส์ยืดนิ่มยืดตามตัวอีก 1–2 นิ้วด้วยนะคะ"
        e2 = (
            f"ของพร้อมส่งราคาตัวละ {price_label} "
            + (f"ที่ {branch_desc} มีโปรลดหน้าร้าน 10–20% และห้องลองให้ลองเทียบได้เลยค่ะ" if branch != "ONLINE" else ("ส่งฟรี EMS เก็บปลายทางไม่บวกเพิ่ม (จับคู่ 2 ตัว 2,400 บาทค่ะ)" if allow_2400 else "ส่งฟรี EMS เก็บปลายทางไม่บวกเพิ่ม ใส่ไม่พอดีเปลี่ยนไซส์ได้ค่ะ"))
        )
        e3 = _close_e3(f"ปกติ{call_name}ใส่กางเกงเอวเท่าไหร่คะ รับโอนหรือเก็บเงินปลายทางดีคะ เดี๋ยวหนูเช็กไซส์ให้เลยค่ะ?")
        return [e1, e2, e3]

    asking_back_view = ("ด้านหลัง" in last_cust or "ข้างหลัง" in last_cust)
    if intent == "ASK_COLOR_LENGTH" or asking_back_view:
        m_len = re.search(r"ความยาว\s*(\d{2}(?:\s*[-–]\s*\d{2})?)\s*นิ้ว", combined_ctx)
        len_txt = f"{m_len.group(1)} นิ้ว" if m_len else ("15–17 นิ้ว" if is_shorts else ("32–34 นิ้ว" if is_skirt else "38–39 นิ้ว"))
        item_name = "กระโปรงยีนส์ปักฉลุ" if is_skirt else ("กางเกงยีนส์ขาสั้น" if is_shorts else "กางเกงยีนส์ปักฉลุ")
        if ad_sku:
            item_name = f"{item_name} ({ad_sku})"
        if asking_back_view:
            e1 = f"{call_name}คะ รุ่น{item_name}ด้านหลังจะเป็นทรงเก็บสะโพกสวย พร้อมงานกระเป๋าหลังประณีตค่ะ ความยาวประมาณ {len_txt} (เดี๋ยวหนูส่งรูปเพิ่ม/ให้แอดมินส่งมุมด้านหลังให้นะคะ)"
        else:
            e1 = f"{call_name}คะ รุ่น{item_name}ตัวนี้ความยาวประมาณ {len_txt} ค่ะ มีสีเดียวตรงตามแบบในรูปเลยนะคะ งานผ้ายีนส์ยืดนิ่มเก็บทรงสวยค่ะ"
        e2 = (
            f"ของพร้อมส่งราคาตัวละ {price_label} "
            + (f"ที่ {branch_desc} มีโปรลดหน้าร้าน 10–20% แวะลองเทียบขนาดจริงได้เลยค่ะ" if branch != "ONLINE" else ("ส่งฟรี EMS เก็บปลายทางไม่บวกเพิ่ม (จับคู่ 2 ตัว 2,400 บาทค่ะ)" if allow_2400 else "ส่งฟรี EMS เก็บปลายทางไม่บวกเพิ่ม ใส่ไม่พอดีเปลี่ยนไซส์ได้ค่ะ"))
        )
        e3 = _close_e3(f"ปกติ{call_name}ใส่เอวเท่าไหร่คะ รับโอนหรือเก็บเงินปลายทางดีคะ เดี๋ยวหนูจัดไซส์พร้อมส่งให้เลยค่ะ?")
        return [e1, e2, e3]

    if intent == "ASK_STYLE_FIT":
        if "ขาม้า" in last_cust:
            e1 = f"{call_name}คะ ทรงขาม้าของร้านเราจะเป็นปลายขาบานกำลังสวย ไม่บานเว่อร์ ช่วยพรางน่องและทำให้ช่วงขาดูเรียวยาวมากค่ะ (มีครบทั้งขาม้าและขากระบอกตรงนะคะ)"
        elif "กระบอก" in last_cust:
            e1 = f"{call_name}คะ รุ่นนี้จะเป็นทรงขากระบอกตรง/กระบอกเล็กพอดีขา ไม่รัดติ้วและไม่บานเกินไป ช่วยเก็บสะโพกและพรางต้นขาได้สวยมากค่ะ"
        else:
            if is_skirt:
                e1 = f"{call_name}คะ กระโปรงยีนส์ปักฉลุของร้านเราจะเป็นทรงเอไลน์เก็บพุงและพรางสะโพก-ต้นขาได้ดีมากค่ะ ชายกระโปรงฉลุโปร่ง เดินสะดวกไม่รั้งขาเลยนะคะ"
            else:
                e1 = f"{call_name}คะ ทรงกางเกงของร้านเราออกแบบมาเพื่อเก็บพุงและพรางต้นขาโดยเฉพาะ ผ้ายีนส์ยืดเนื้อนิ่ม ใส่แล้วช่วงขาดูเรียวไม่อึดอัดค่ะ"
        e2 = (
            f"มีครบไซส์ M–4XL (เอว 26–42 นิ้ว) ราคาตัวละ {price_label} "
            + (f"ที่ {branch_desc} มีโปรลดหน้าร้าน 10–20% และห้องลองให้ลองใส่ค่ะ" if branch != "ONLINE" else ("ส่งฟรี EMS เก็บปลายทางไม่บวกเพิ่ม (จับคู่ 2 ตัว 2,400 บาทค่ะ)" if allow_2400 else "ส่งฟรี EMS เก็บปลายทางไม่บวกเพิ่ม ใส่ไม่พอดีเปลี่ยนไซส์ได้ค่ะ"))
        )
        e3 = f"ปกติ{call_name}ใส่เอว-สะโพกประมาณเท่าไหร่คะ เดี๋ยวหนูแนะนำทรงและไซส์ที่ใส่สวยที่สุดให้เลยค่ะ?"
        return [e1, e2, e3]

    if pain_thigh_belly or intent == "ASK_SIZE":
        e1 = f"{call_name}คะ รุ่นนี้ตอบโจทย์คนกังวลช่วงหน้าท้อง-ต้นขาเลยค่ะ เพราะเป็นผ้ายีนส์ยืดเนื้อนิ่ม ยืดหยุ่นเพิ่มได้อีก 1–2 นิ้ว มีครบถึง 4XL (เอว 26–42 นิ้ว) ค่ะ"
        e2 = (
            f"ทรง{'เอไลน์ช่วยพรางสะโพกและต้นขาได้ดีมาก' if is_skirt else 'ขากระบอกเล็ก/ทรงปล่อยช่วงต้นขา ใส่แล้วขาดูเรียวไม่อึดอัด'}ค่ะ "
            + (f"แวะลองที่ {branch_desc} ได้เลยนะคะ" if branch != "ONLINE" else f"ราคา {price_label} ส่งฟรี EMS ใส่ไม่พอดีเปลี่ยนไซส์ได้ค่ะ")
        )
        e3 = f"{call_name}บอกเอว-สะโพก หรือน้ำหนัก-ส่วนสูงคร่าวๆ ให้หนูช่วยเทียบไซส์เป๊ะๆ ให้ได้เลยนะคะ?"
        return [e1, e2, e3]

    if intent == "ASK_PRICE":
        asks_size_too = any(k in last_cust for k in ["ขยาด", "ขนาด", "ไซส์"])
        size_line = (
            " ไซส์ทำตั้งแต่ M (เอว 26–28\") / L (28–30\") / XL (30–32\") / 2XL (32–34\") / 3XL (34–36\") / 4XL (38–40 ยืดสุด 42\") ค่ะ"
            if asks_size_too
            else ""
        )
        if already_covered.get("sent_price"):
            e1 = f"{call_name}คะ นอกจากราคา {price_label} ส่งฟรีแล้ว ตัวนี้คุ้มตรงเป็นผ้ายีนส์ยืดนิ่มปักฉลุ ใส่สบายไม่อึดอัดและไม่หดหลังซักค่ะ"
            e2 = (
                f"ที่ {branch_desc} มีโปรหน้าร้าน 1 ตัวลด 10% / 2 ตัวลด 20% นะคะ{size_line}"
                if branch != "ONLINE"
                else (f"ถ้าจับคู่ 2 ตัวจะเหลือเพียง 2,400 บาท (ประหยัด 180 บาท) พร้อมเก็บเงินปลายทางไม่บวกเพิ่มและเปลี่ยนไซส์ได้ค่ะ{size_line}" if allow_2400 else f"พร้อมบริการเก็บเงินปลายทางไม่บวกเพิ่มและเปลี่ยนไซส์ได้ค่ะ{size_line}")
            )
        else:
            e1 = f"{call_name}คะ รุ่นนี้ราคาตัวละ {price_label} ค่ะ งานผ้ายีนส์ยืดปักฉลุละเอียด ใส่สบายเก็บทรงสวยมากค่ะ{size_line}"
            e2 = (
                f"ส่งฟรี EMS ถึงบ้าน หรือเก็บเงินปลายทาง (COD) ไม่บวกเพิ่ม แกะเช็คของก่อนได้ "
                + (f"และที่ {branch_desc} มีโปรลดหน้าร้าน 10–20% ด้วยนะคะ" if branch != "ONLINE" else ("ถ้าจับคู่ 2 ตัวเหลือเพียง 2,400 บาทค่ะ" if allow_2400 else "ใส่ไม่พอดีเปลี่ยนไซส์ได้ค่ะ"))
            )
        e3 = _close_e3(f"ปกติ{call_name}ใส่เอวเท่าไหร่คะ รับโอนหรือเก็บเงินปลายทางดีคะ เดี๋ยวหนูเช็กไซส์ให้เลยค่ะ?")
        return [e1, e2, e3]

    if intent == "ASK_BRANCH":
        other_city = next(
            (c for c in ["กทม", "กรุงเทพ", "ชลบุรี", "ระยอง", "ระยอ", "สัตหีบ", "ชล", "พัทยา", "เชียงใหม่", "ภูเก็ต", "สงขลา", "หาดใหญ่", "สุรินทร์", "บุรีรัมย์", "ร้อยเอ็ด", "มหาสารคาม", "ศรีสะเกษ", "อุบล"] if c in last_cust),
            "",
        )
        if other_city in ("ระยอ", "สัตหีบ", "ชล"):
            other_city = "ชลบุรี/ระยอง"
        if branch == "ONLINE":
            if other_city:
                e1 = f"{call_name}คะ ตอนนี้ที่ร้านยังไม่มีสาขาที่{other_city}เลยค่ะ 🙏 หน้าร้านเรามี 3 สาขาคือ เซ็นทรัลขอนแก่น ชั้น G, เซ็นทรัลโคราช ชั้น 1 และเซ็นทรัลอุดรธานี ชั้น 3 นะคะ"
            else:
                e1 = f"{call_name}คะ หน้าร้านเรามี 3 สาขาคือ เซ็นทรัลขอนแก่น ชั้น G, เซ็นทรัลโคราช ชั้น 1 และเซ็นทรัลอุดรธานี ชั้น 3 ค่ะ แต่ถ้าไม่สะดวกแวะสาขา สั่งออนไลน์ส่งฟรี EMS 1–2 วันถึงบ้านเลยนะคะ"
            e2 = f"ออนไลน์ของพร้อมส่งราคา {price_label} เก็บเงินปลายทาง (COD) ไม่บวกเพิ่ม แกะเช็คก่อนได้ และใส่ไม่พอดีเปลี่ยนไซส์ได้ค่ะ" + (" (โปรคู่ 2 ตัว 2,400 บาท)" if allow_2400 else "")
            e3 = _close_e3(f"ปกติ{call_name}ใส่เอวเท่าไหร่คะ รับโอนหรือเก็บเงินปลายทางดีคะ เดี๋ยวหนูเช็กไซส์ให้เลยค่ะ?")
        else:
            e1 = f"{call_name}คะ หน้าร้านของเราอยู่ที่ {branch_desc} ค่ะ รุ่นงานปักฉลุมีครบไซส์ M–4XL มีห้องให้ลองใส่จริงหลายแบบเลยนะคะ"
            e2 = "แวะมาลองที่ร้านได้เลยค่ะ ตอนนี้หน้าร้านมีโปรซื้อ 1 ตัวลด 10%, 2 ตัวลด 20% และครบ 3,000 แถมเสื้อยืด 1 ตัวด้วยค่ะ"
            e3 = _close_e3(f"{call_name}ใส่เอวเท่าไหร่คะ แวะมาวันไหนดี เดี๋ยวเช็กไซส์ที่สาขาไว้ให้ค่า")
        return [e1, e2, e3]

    if intent == "ASK_COD":
        e1 = f"{call_name}คะ มีเก็บปลายทาง (COD) ส่งฟรี EMS 1–2 วันถึงบ้าน ไม่มีบวกค่าส่งหรือค่าปลายทางเพิ่มเลยค่ะ"
        e2 = f"ของพร้อมส่งราคา {price_label} รับของแล้วแกะเช็กงานก่อนจ่ายได้ และใส่ไม่พอดีเปลี่ยนไซส์ได้ค่ะ"
        e3 = _close_e3(f"รับกี่ตัวดีคะ{call_name} ปกติใส่เอวเท่าไหร่คะ แจ้งไซส์พร้อมชื่อ ที่อยู่ เบอร์โทรมาได้เลยได้เลยค่ะ?")
        return [e1, e2, e3]

    if facts_last.get("wants_dark") or facts_last.get("wants_light") or any(k in last_cust for k in ["อ้วน", "พลาง", "พราง", "เก็บพุง"]):
        if facts_last.get("wants_dark") or "สีเข้ม" in last_cust:
            e1 = f"แนะนำสียีนส์เข้มเลยค่ะ{call_name} ใส่แล้วช่วยพรางสัดส่วนและทำให้ช่วงขาดูเรียวยาวขึ้นเยอะมาก ผ้ายีนส์ยืดเนื้อนิ่มเก็บพุงสบายๆ ครบถึงไซส์ 4XL (เอว 38–40 สะโพก 48–50\") เลยค่ะ"
        elif facts_last.get("wants_light"):
            e1 = f"โทนสียีนส์ฟอกสว่างใส่แล้วดูสดใสขับผิวและแมตช์กับเสื้อได้ง่ายค่ะ{call_name} ผ้ายืดนิ่มพรางสัดส่วนได้ดี ครบไซส์ M–4XL เลยนะคะ"
        else:
            e1 = f"{call_name}คะ รุ่นนี้ออกแบบมาช่วยพรางหน้าท้อง-สะโพกและเก็บทรงสำหรับคนมีเนื้อมีพุงโดยเฉพาะ ผ้ายีนส์ยืดนิ่มยืดตามตัว มีถึง 4XL (เอว 38–40 ยืดเต็มที่ ~41–42\" สะโพก 48–50\") เลยค่ะ"
        e2 = (
            f"ราคาตัวละ {price_label} "
            + (f"ที่ {branch_desc} มีห้องลองและโปรลด 10–20% ด้วยนะคะ" if branch != "ONLINE" else ("ส่งฟรี EMS / เก็บปลายทางไม่บวกเพิ่ม (ใส่ไม่พอดีเปลี่ยนไซส์ได้ค่ะ)" if not allow_2400 else "ส่งฟรี EMS / เก็บปลายทางไม่บวกเพิ่ม (จับคู่ 2 ตัว 2,400 บาท ใส่ไม่พอดีเปลี่ยนไซส์ได้ค่ะ)"))
        )
        e3 = f"ปกติ{call_name}ใส่กางเกงเอวประมาณเท่าไหร่คะ เดี๋ยวหนูเทียบไซส์พอดีตัวและส่งรูปสี{'เข้ม' if facts_last.get('wants_dark') else ''}สวยๆ ให้ชมค่ะ?"
        return [e1, e2, e3]

    if not is_followup and any(k in last_cust for k in ["ซับใน", "มีซับ", "มีทรัพ", "กลัวคัน", "คันไหม", "คันมั้ย"]):
        e1 = f"ไม่มีซับในนะคะ{call_name} แต่ด้านในงานปักเก็บเรียบร้อย และผ้ายีนส์ฟอกนุ่มมาก ใส่แล้วไม่คันไม่ระคายเคืองแน่นอนค่ะ (ขายมาหลายพันตัวลูกค้าชมใส่สบายค่ะ)"
        e2 = f"ของพร้อมส่งครบไซส์ M–4XL ราคาตัวละ {price_label} ส่งฟรี EMS 1–2 วันถึง หรือเก็บเงินปลายทางไม่บวกเพิ่ม (ใส่ไม่พอดีเปลี่ยนได้ค่ะ)"
        e3 = _close_e3(f"ปกติ{call_name}ใส่เอวเท่าไหร่คะ รับโอนหรือเก็บเงินปลายทางดีคะ แจ้งเอวไว้ให้หนูเช็กไซส์ให้เลยค่ะ?")
        return [e1, e2, e3]

    if not is_followup and any(k in last_cust for k in ["สม้อก", "สม็อก", "ยางยืดหลัง", "ยางยืดข้างหลัง", "เอวยางยืด"]):
        e1 = f"{call_name}คะ รุ่นนี้ไม่ใช่เอวสม็อกยางยืดนะคะ แต่เป็นผ้ายีนส์ยืดทั้งตัว ยืดหยุ่นตามตัวได้อีก 1–2 นิ้ว ใส่สบายไม่อึดอัดและเก็บหน้าท้องสวยกว่ายางยืดค่ะ"
        e2 = f"ของพร้อมส่งครบไซส์ M–4XL ราคา {price_label} ส่งฟรี EMS 1–2 วันถึง เก็บเงินปลายทางไม่บวกเพิ่ม และใส่ไม่พอดีเปลี่ยนไซส์ได้ค่ะ"
        e3 = _close_e3(f"ปกติ{call_name}ใส่เอวเท่าไหร่คะ รับโอนหรือเก็บเงินปลายทางดีคะ แจ้งเอวและชื่อ-ที่อยู่-เบอร์โทรให้หนูเตรียมจัดส่งได้เลยค่ะ?")
        return [e1, e2, e3]

    if not is_followup and any(k in last_cust for k in ["เป้าถึงเอว", "ความยาวเป้า", "ปลายขากว้าง", "รอบปลายขา"]):
        e1 = f"{call_name}คะ รุ่นนี้เป้าสูงประมาณ 13 นิ้ว (ทรงเอวสูงเก็บพุง) ส่วนปลายขาหน้าผ้ากว้างประมาณ 10–14 นิ้ว (รอบขา 20–28 นิ้ว ตามทรงขากระบอกหรือขาบาน) ค่ะ"
        e2 = f"ผ้ายีนส์ยืดนิ่มยืดได้อีก 1–2 นิ้ว ราคาตัวละ {price_label} ส่งฟรี EMS 1–2 วันถึง เก็บเงินปลายทางไม่บวกเพิ่มค่ะ"
        e3 = _close_e3(f"ปกติ{call_name}ใส่เอวเท่าไหร่คะ รับโอนหรือเก็บเงินปลายทางดีคะ เดี๋ยวหนูเช็กไซส์ให้เลยค่ะ?")
        return [e1, e2, e3]

    if not is_followup and any(k in last_cust for k in ["เย็บปลายขา", "เย็บขา"]):
        e1 = f"ปกติปลายขาเป็นงานเย็บจากโรงงานค่ะ{call_name} ถ้าอยากให้ที่ร้านจ้างช่างนอกตัด/เย็บปลายขาขึ้นให้ มีค่าบริการเย็บขาเพิ่ม 50 บาทค่ะ"
        e2 = f"หรือถ้าเป็นรุ่นความยาว 35–39 นิ้ว ลูกค้าสามารถพับหรือตัดขาเองได้ไม่เสียทรงค่ะ (ราคาตัวละ {price_label} ส่งฟรี EMS / เก็บปลายทางไม่บวกเพิ่ม)"
        e3 = _close_e3(f"ปกติ{call_name}ใส่เอวเท่าไหร่และสูงเท่าไหร่คะ รับโอนหรือเก็บเงินปลายทางดีคะ?")
        return [e1, e2, e3]

    if not is_followup and any(k in last_cust for k in ["สั่งยังไง", "สังยังไง", "สั่งซื้อยังไง", "วิธีสั่ง", "สั่งแบบไหน"]):
        e1 = f"สั่งง่ายมากเลยค่ะ{call_name} เพียงแจ้งไซส์หรือรอบเอว-สะโพกที่ใส่ แล้วเลือกส่งแบบโอนส่งฟรี EMS หรือเก็บเงินปลายทางไม่บวกเพิ่มค่ะ"
        e2 = f"ราคาตัวละ {price_label} ส่งฟรี EMS 1–2 วันถึงบ้าน แกะเช็คของก่อนจ่ายได้ และถ้าใส่ไม่พอดีสามารถเปลี่ยนไซส์ได้ค่ะ"
        e3 = _close_e3(f"ปกติ{call_name}ใส่เอวเท่าไหร่คะ รับโอนหรือเก็บเงินปลายทางดีคะ ขอชื่อ ที่อยู่ เบอร์โทรมาได้เลยได้เลยค่ะ?")
        return [e1, e2, e3]

    if is_compliment:
        item_label = "กระโปรงยีนส์ปักฉลุ" if is_skirt else ("กางเกงยีนส์ขาสั้น" if is_shorts else "กางเกงยีนส์ปักฉลุ")
        if branch != "ONLINE":
            branch_short = {"KORAT": "เซ็นทรัลโคราช", "KKC": "เซ็นทรัลขอนแก่น", "UDN": "เซ็นทรัลอุดรธานี"}.get(branch, branch_desc)
            e1 = f"ขอบคุณมากๆ เลยค่ะ{call_name} 💖 คลิป/แอดที่พี่ทักเข้ามาเป็นงานจริงที่หน้าร้านสาขา {branch_desc} เลยค่ะ"
            e2 = f"แวะมาลองจริงที่ {branch_short} ได้สบายๆ เลยนะคะ โปรหน้าร้านตอนนี้ซื้อ 1 ตัวลด 10%, 2 ตัวลด 20% และครบ 3,000 แถมเสื้อยืด 1 ตัวค่ะ"
            e3 = f"รุ่น{item_label}ผ้ายีนส์ยืดนิ่มเก็บทรงสวย ทำไซส์ M–4XL (เอว 26–42 นิ้ว) ราคาตัวละ {price_label} ค่ะ"
            e4 = f"{call_name}อยู่แถวไหนคะ แวะลองที่ {branch_short} วันไหนดี หรือแจ้งเอวมาเช็กไซส์ก่อนได้ค่า"
            return [e1, e2, e3, e4]
        e1 = f"ขอบคุณมากๆ เลยค่ะ{call_name} 💖 รุ่น{item_label}ตัวนี้ลูกค้าใส่จริงชมทุกคนเลยค่ะว่าทรงสวยเก็บพุง ผ้ายีนส์ยืดนิ่มใส่สบายมาก (ทำไซส์ M–4XL เอว 26–42 นิ้วค่ะ)"
        e2 = (
            f"ตอนนี้พร้อมส่งราคา {price_label} ส่งฟรี EMS หรือเก็บเงินปลายทาง (COD) ไม่บวกเพิ่ม "
            + ("(โปรจับคู่ 2 ตัว 2,400 บาทคุ้มมากค่ะ)" if allow_2400 else "")
        )
        e3 = f"{call_name}รับเป็นรุ่นนี้สักตัวเลยไหมคะ ปกติใส่เอว-สะโพกประมาณเท่าไหร่ เดี๋ยวหนูเช็กไซส์ที่ใส่สวยเป๊ะให้เลยค่ะ?"
        return [e1, e2, e3]

    if is_shirt:
        e1 = f"มีรุ่นเสื้อของร้านเราให้เลือกใส่เข้าชุดด้วยนะคะ{call_name} เดี๋ยวหนูให้แอดมินส่งแบบเสื้อพร้อมเช็กไซส์รอบอกให้ชมทันทีเลยค่ะ"
        e2 = "ถ้าสนใจรับคู่เซ็ตเสื้อ+กางเกงยีนส์ปักฉลุก็คุ้มมากค่ะ (กางเกง/กระโปรงออนไลน์ส่งฟรี EMS 1–2 วันถึง เก็บปลายทางไม่บวกเพิ่ม หน้าร้านมีโปรลด 10–20% ค่ะ)"
        e3 = f"ปกติ{call_name}ใส่เสื้อรอบอกประมาณกี่นิ้ว และสนใจกางเกง/กระโปรงไซส์ไหนคู่กันด้วยไหมคะ?"
        return [e1, e2, e3]

    # Quick conversational ack on a continuing thread ("ค่ะ", "จ้า", "โอเค") -> warm & gently nudge, NEVER match sentences just ending in คะ!
    if has_prior_reply and not is_followup and not is_compliment and intent == "GREETING_INTEREST" and re.match(
        r"^(?:ได้|โอเค|ok|รับทราบ|อืม|อ่อ|อ๋อ|ค่ะ|คะ|ค่า|จ้า|จร้า|นะคะ|นะค่ะ|ครับ|คับ)+[!.\s🙏❤️🥰👍]*$",
        last_cust.strip(),
    ):
        return [
            f"ได้ค่ะ{call_name} ถ้าเลือกแบบหรือเช็กไซส์ตรงไหนเพิ่ม ทักหนูเช็กไซส์ให้ได้เลยนะคะ (ช่วงนี้บางไซส์ออกไวมากค่ะ)",
            "แจ้งเอว-สะโพกทิ้งให้หนูคัดตัวที่ใส่สวยและคุ้มโปรที่สุดไว้ให้ได้เลยนะคะ 🙏",
        ]

    # GREETING_INTEREST / ASK_STOCK_MODEL + Returning VIP check
    vip = find_customer_crm(customer_name)
    ad_hint = "" if has_prior_reply else ("จากคลิป/แอดที่พี่ทักเข้ามา " if (ad_context or ad_intro) else "")
    greet_prefix = "" if has_prior_reply else "สวัสดีค่ะ"
    base_item = "กระโปรงยีนส์ปักฉลุ" if is_skirt else ("กางเกงยีนส์ขาสั้น" if is_shorts else "กางเกงยีนส์ปักฉลุ")
    item_label = f"{base_item} ({ad_sku})" if ad_sku else base_item
    if vip and not is_followup and not has_prior_reply and not any(k in last_cust for k in ["เปลี่ยน", "เป้ายิ้ม", "ตำหนิ", "ผิด", "แก้"]):
        prev_sku = vip.get("last_sku") or "รุ่นเดิม"
        e1 = f"ยินดีต้อนรับกลับมานะคะ{call_name} รุ่น{item_label}ตอนนี้มีของพร้อมส่งครบไซส์ M–4XL เลยนะคะ"
        e2 = f"หนูมีข้อมูลเดิมของ{call_name} อยู่แล้ว (รอบก่อนรับ {prev_sku}) ส่งฟรี EMS หรือเก็บปลายทางไม่บวกเพิ่มเหมือนเดิมค่ะ"
        e3 = f"รอบนี้{call_name}รับไซส์เดิมที่อยู่เดิมเลยไหมคะ ปลายทางเหมือนเดิมนะคะ?"
        return [e1, e2, e3]

    if branch != "ONLINE":
        branch_short = {"KORAT": "เซ็นทรัลโคราช", "KKC": "เซ็นทรัลขอนแก่น", "UDN": "เซ็นทรัลอุดรธานี"}.get(branch, branch_desc)
        e1 = f"{greet_prefix}{call_name}{'คะ ' if has_prior_reply else ' '}{ad_hint}หน้าร้านของเราอยู่ที่ {branch_desc} นะคะ"
        e2 = f"แวะมาลองที่ {branch_short} ได้สบายๆ เลยนะคะ โปรหน้าร้านตอนนี้ซื้อ 1 ตัวลด 10%, 2 ตัวลด 20% และครบ 3,000 บาทแถมฟรีเสื้อยืด 1 ตัวค่ะ"
        e3 = f"รุ่น{item_label}ผ้ายีนส์ยืดนิ่มทำไซส์ตั้งแต่ M–4XL (เอว 26–42 นิ้ว) ราคาตัวละ {price_label} ค่ะ"
        e4 = f"{call_name}แวะมาลองที่ {branch_short} วันไหนดีคะ หรือแจ้งเอวมาให้หนูเช็กไซส์ไว้ให้ก่อนได้ค่า"
        return [e1, e2, e3, e4]

    e1 = _pick_var([
        f"{greet_prefix}{call_name}{'คะ ' if has_prior_reply else ' '}{ad_hint}รุ่น{item_label}ของพร้อมส่งครบไซส์ M–4XL (เอว 26–42 นิ้ว) ผ้ายีนส์ยืดนิ่มใส่สบาย มีหน้าร้านจริงของตรงปกค่ะ",
        f"{greet_prefix}{call_name}{'คะ ' if has_prior_reply else ' '}รุ่น{item_label}มีของพร้อมส่งครบไซส์ M–4XL (เอว 26–42 นิ้ว) ผ้ายืดนิ่มเก็บทรงสวย ตรงปก 100% ค่ะ",
        f"{greet_prefix}{call_name}{'คะ ' if has_prior_reply else ' '}รุ่น{item_label}ผ้ายีนส์ยืดนิ่ม ใส่สบายไม่รั้งเป้า มีครบไซส์ M–4XL พร้อมส่งเลยนะคะ",
    ], "greet_e1")
    e2 = _pick_var([
        f"ราคาตัวละ {price_label} ส่งฟรี EMS 1–2 วันถึง หรือเก็บเงินปลายทางไม่บวกเพิ่ม"
        + (" (โปรคู่ 2 ตัว 2,400 บาทคุ้มมากค่ะ)" if allow_2400 else " (ใส่ไม่พอดีส่งเปลี่ยนได้ค่ะ)"),
        f"ตัวละ {price_label} ส่งฟรี EMS / เก็บปลายทางไม่บวกเพิ่ม แกะเช็คหน้าบ้านก่อนจ่ายได้นะคะ"
        + (" (รับ 2 ตัวเหลือ 2,400 บาทค่ะ)" if allow_2400 else ""),
        f"ราคา {price_label} พร้อมส่งรอบวันนี้เลยค่ะ ฟรี EMS 1–2 วันถึง หรือปลายทางไม่บวกเพิ่ม ใส่ไม่ได้เปลี่ยนไซส์ได้ค่ะ",
    ], "greet_e2")
    e3 = _close_e3(_pick_var([
        f"ปกติ{call_name}ใส่เอวเท่าไหร่คะ รับโอนหรือเก็บเงินปลายทางดีคะ ส่งชื่อ-ที่อยู่-เบอร์โทรมาได้เลยค่า?",
        f"{call_name}ใส่เอวประมาณกี่นิ้วคะ โอนหรือเก็บเงินปลายทางแจ้งหนูเช็กไซส์พร้อมส่งวันนี้ได้เลยนะคะ?",
        f"แจ้งรอบเอวของ{call_name} พร้อมเลือกโอนหรือปลายทางมาได้เลยค่ะ เดี๋ยวหนูเช็กไซส์แพ็กส่งให้เลยค่า?",
    ], "greet_e3"))
    return [e1, e2, e3]


# Visually verified Meta permanent reusable attachment IDs (never expire unlike CDN URLs)
CURATED_ATTACHMENTS = {
    "SIZE_CHART": "1857306062190394",         # Clear M-4XL size chart board + real jeans
    "BRANCH_KKC": "28941682505460629",        # Central Khon Kaen storefront
    "BRANCH_UDN": "1438370284538274",         # Central Udon storefront
    "BRANCH_KORAT": "2228176728130443",       # Central Korat storefront
    "BRANCH_KKC_2": "1471592311733779",       # Central Khon Kaen storefront 2
    "BRANCH_UDN_2": "1761824871569198",       # Central Udon storefront 2
    "BRANCH_KORAT_2": "1948095589506224",     # Central Korat storefront 2
    "SKIRT": "2526174217871126",              # A-line embroidered denim skirt on model
    "SKIRT_CHOICE": "2134820130482245",       # Dark + light lace-hem skirts held in store
    "STYLE_FLARE": "29138109175828179",       # Flared embroidered jeans on model
    "PRODUCT_FLOWER": "1959782458794345",     # Light-wash flower embroidered jeans at counter
    "PRODUCT_RHINESTONE": "1014104184291093", # Side-crystal straight jeans in store
    "PRODUCT_SUNFLOWER": "937712419275470",   # Sunflower embroidered jeans on model
}

BRANCH_IMAGES = {
    "KORAT": [
        f"attachment_id:{CURATED_ATTACHMENTS['BRANCH_KORAT']}",
        f"attachment_id:{CURATED_ATTACHMENTS['BRANCH_KORAT_2']}",
    ],
    "KKC": [
        f"attachment_id:{CURATED_ATTACHMENTS['BRANCH_KKC']}",
        f"attachment_id:{CURATED_ATTACHMENTS['BRANCH_KKC_2']}",
    ],
    "UDN": [
        f"attachment_id:{CURATED_ATTACHMENTS['BRANCH_UDN']}",
        f"attachment_id:{CURATED_ATTACHMENTS['BRANCH_UDN_2']}",
    ],
}


def pick_images_for_reply(
    messages: List[Dict[str, Any]],
    intent: str,
    branch: str = "ONLINE",
    ad_context: str = "",
    is_followup: bool = False,
    followup_stage: int = 0,
) -> List[str]:
    """Select verified Meta attachment_ids (2 storefront photos for branches, alternating context-matched photo on follow-ups)."""
    if intent in ("AFTER_SALES_THANKS", "SHIPPING_TRACKING"):
        return []
    if is_followup and (followup_stage % 2 == 1 or followup_stage >= 7):
        return []
    msgs = messages or []
    last_cust = next(((m.get("text") or "").lower() for m in reversed(msgs) if m.get("sender_role") == "customer"), "")
    ask_size_chart_img = (not is_followup) and _is_size_chart_request(last_cust)

    def _is_page_img(m: Dict[str, Any]) -> bool:
        if m.get("sender_role") not in ("bot", "admin"):
            return False
        t = m.get("text") or ""
        return "[BOT_SENT_IMAGE]" in t or "[ADMIN_SENT_IMAGE]" in t or "[IMAGE" in t

    # Never resend images if page/bot/admin already sent an image in recent messages
    if any(_is_page_img(m) for m in msgs[-6:]):
        return []

    facts_img = _extract_body_facts(last_cust, last_cust_only=last_cust)
    if facts_img.get("waist_too_big") or facts_img.get("waist_too_small"):
        return []

    # STRICT ZERO-WRONG-PHOTO POLICY:
    # 1. Size chart (ONLY when customer explicitly asks for size chart / available sizes)
    if ask_size_chart_img:
        return [f"attachment_id:{CURATED_ATTACHMENTS['SIZE_CHART']}"]

    # 2. Branch storefront photos: send AT MOST ONCE per 48h session; NEVER repeat on follow-ups if any image was already sent
    recent_48h_imgs = sum(1 for m in _recent_session_messages(msgs, hours=48) if _is_page_img(m))
    any_recent_20_imgs = any(_is_page_img(m) for m in msgs[-20:])
    explicit_branch_ask = any(k in last_cust for k in ["หน้าร้าน", "ที่ไหน", "พิกัด", "สาขา", "ชั้น", "เซ็นทรัล", "ขอนแก่น", "อุดร", "โคราช"])
    if branch in BRANCH_IMAGES and explicit_branch_ask:
        if is_followup:
            if any_recent_20_imgs or recent_48h_imgs > 0:
                return []
            return list(BRANCH_IMAGES[branch])
        if not any(_is_page_img(m) for m in msgs[-6:]):
            return list(BRANCH_IMAGES[branch])

    # Never guess product/skirt/flare/SKU photos (each ad/model differs; admin sends exact model photos via Telegram alert)
    return []


def pick_image_for_reply(
    messages: List[Dict[str, Any]],
    intent: str,
    branch: str = "ONLINE",
    ad_context: str = "",
    is_followup: bool = False,
) -> Optional[str]:
    imgs = pick_images_for_reply(messages, intent, branch, ad_context, is_followup)
    return imgs[0] if imgs else None


def _resolve_fast_model(settings: Dict[str, str]) -> str:
    m = (settings.get("gemini_model") or os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")).strip()
    return "gemini-3-flash-preview" if (not m or m == "gemini-3.8-flash") else m


def analyze_customer_image_with_gemini(image_url: str) -> Optional[Dict[str, Any]]:
    """Use Gemini Vision (when GEMINI_API_KEY is set) to OCR slips, address screenshots, or product photos."""
    settings = get_settings()
    api_key = os.getenv("GEMINI_API_KEY") or settings.get("GEMINI_API_KEY", "")
    model_name = _resolve_fast_model(settings)
    if not api_key or not image_url:
        return None
    try:
        import requests as _req
        from google import genai
        from google.genai import types

        img_bytes = _req.get(image_url, timeout=15).content
        client = genai.Client(api_key=api_key)
        prompt = (
            "วิเคราะห์รูปภาพที่ลูกค้าส่งมาในแชทร้านยีนส์ ตอบเป็น JSON เท่านั้น: "
            '{"type": "SLIP" | "ADDRESS" | "PRODUCT" | "OTHER", '
            '"extracted_text": "สรุปยอดโอน/ชื่อ-ที่อยู่-เบอร์โทร/รุ่นสินค้าที่เห็นในภาพ", '
            '"amount": 0}'
        )
        for cand_model in dict.fromkeys([model_name, "gemini-2.5-flash"]):
            try:
                resp = client.models.generate_content(
                    model=cand_model,
                    contents=[
                        types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"),
                        prompt,
                    ],
                    config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.1),
                )
                return json.loads(resp.text)
            except Exception:
                continue
        return None
    except Exception as e:
        print(f"[BrainVision] Error: {e}")
        return None


LAST_LLM_STATUS: Dict[str, Any] = {"model": "", "ok": False, "error": "", "at": ""}


def generate_3enter_reply(
    customer_name: str,
    branch: str,
    intent: str,
    messages: List[Dict[str, Any]],
    already_covered: Dict[str, Any],
    ad_name: str = "",
    campaign_name: str = "",
    is_followup: bool = False,
    followup_stage: int = 0,
    ad_post_text: str = "",
) -> List[str]:
    """Generate 3 sequential Messenger bubbles tailored to Ad context, Chat history & Grill constraints."""
    settings = get_settings()
    api_key = os.getenv("GEMINI_API_KEY") or settings.get("GEMINI_API_KEY", "")
    model_name = _resolve_fast_model(settings)

    ad_context = " | ".join(
        p for p in [
            f"Campaign: {campaign_name}" if campaign_name else "",
            f"Ad: {ad_name}" if ad_name else "",
            f"Post: {ad_post_text}" if ad_post_text else "",
        ] if p
    )
    ads_kb = list_ad_knowledge()
    matched_ad_kb = next(
        (a for a in ads_kb if ad_name and a.get("ad_name") == ad_name),
        None,
    )
    patterns = list_learned_patterns(branch=branch)[:6]

    last_c_raw = next(((m.get("text") or "").lower() for m in reversed(messages or []) if m.get("sender_role") == "customer"), "")

    # Deferral / polite-close guard: never re-pitch a customer who just said "ไว้ดูก่อน / ยังไม่สั่ง / ขอบคุณ"
    if not is_followup and last_c_raw and len(last_c_raw) <= 80 and not _is_english_query(last_c_raw):
        _q = any(k in last_c_raw for k in ("?", "ไหม", "มั้ย", "เท่าไหร่", "เท่าไร", "เอว", "สะโพก", "ไซส์", "ราคา", "โอน", "ปลายทาง", "ที่อยู่", "เปลี่ยน", "ตำหนิ", "ผิด"))
        if not _q:
            if any(k in last_c_raw for k in ("ไว้ดู", "ดูก่อน", "ยังไม่สั่ง", "ยังไม่เอา", "ยังไม่รับ", "คิดดูก่อน", "ไว้ก่อน", "ไว้โอกาสหน้า", "เดี๋ยวแวะ", "ไว้แวะ", "ถามเฉย", "ดูเฉย")):
                return ["ได้เลยค่ะพี่ ไม่เป็นไรนะคะ 🙏 ถ้าสนใจรุ่นไหนหรืออยากเช็กไซส์ ทักหนูได้ตลอดเลยค่ะ"]
            if any(k in last_c_raw for k in ("ขอบคุณ", "ขอบพระคุณ", "รับทราบ", "โอเค", "เรียบร้อยแล้ว")):
                return []
    # Post-order guard: never interrupt a just-closed order from human admin (e.g. "สรุปออเดอร์การสั่งซื้อ", "คุณร้องขอไป ฿")
    if not is_followup and messages:
        recent_tail = messages[-6:]
        has_recent_order_close = any(
            any(k in (m.get("text") or "") for k in ("สรุปออเดอร์การสั่งซื้อ", "รับออเดอร์ค่ะ", "คุณร้องขอไป ฿", "ทำเครื่องหมายคำสั่งซื้อว่า"))
            for m in recent_tail
        )
        has_new_followup_question = any(
            k in last_c_raw for k in ("อีก", "เพิ่ม", "เสื้อ", "กระโปรง", "รุ่นนี้", "รุ่นอื่น", "ราคา", "กี่บาท", "ไซส์", "เอว", "หนาไหม")
        )
        if has_recent_order_close and not has_new_followup_question:
            return []

    facts_check = _extract_body_facts(last_c_raw, last_cust_only=last_c_raw)
    # Use Gemini for ALL real sales/question/follow-up turns so answers are flexible, context-aware & human-like;
    # only skip LLM for fixed after-sales/tracking acks or when API key is missing.
    use_deterministic_only = (
        not api_key
        or intent in ("AFTER_SALES_THANKS", "SHIPPING_TRACKING")
    )
    if not use_deterministic_only:
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=api_key)

            chat_lines = []
            for m in messages[-16:]:
                role = "ลูกค้า" if m.get("sender_role") == "customer" else "แอดมิน/บอท"
                txt = (m.get("text") or "").strip()
                if txt.startswith("[IMAGE:"):
                    txt = "[ลูกค้าส่งรูปภาพสินค้า/อ้างอิง]"
                elif txt == "[STICKER]":
                    txt = "(ลูกค้ากดไลก์/ส่งสติกเกอร์สนใจสินค้า)"
                elif not txt:
                    continue
                chat_lines.append(f"- {role}: {txt}")
            chat_history_str = "\n".join(chat_lines) if chat_lines else "(ลูกค้าเพิ่งทักเข้ามา)"
            latest_cust_line = "(ลูกค้ากดไลก์/ส่งสติกเกอร์สนใจสินค้า)" if last_c_raw.strip() == "[sticker]" else (last_c_raw.strip() or "(ลูกค้าส่งรูปภาพ/สติกเกอร์)")

            patterns_str = "\n".join(
                f"- [{p['topic']} / {p['customer_intent']}] ลูกค้า: \"{p['customer_example']}\" -> แอดมิน: \"{p['admin_reply_example']}\""
                for p in patterns
            )

            no_repeat_rules = [
                "- ตอบกลับตามภาษาที่ลูกค้าพิมพ์ล่าสุด 100%: ถ้าลูกค้าพิมพ์ภาษาอังกฤษให้ตอบภาษาอังกฤษ, พิมพ์พม่าให้ตอบภาษาพม่า, พิมพ์ลาวให้ตอบภาษาลาว, และถ้าพิมพ์ไทยให้ตอบภาษาไทยสั้นกระชับเหมือนคนจริง!",
                "- ห้ามเดาหรือยัดเยียดไซส์ M ให้ลูกค้าเด็ดขาด! ถ้าลูกค้ายังไม่เคยบอกรอบเอว สะโพก น้ำหนัก หรือระบุไซส์มาก่อน ให้บอกว่าทางร้านมีครบไซส์ M–4XL (เอว 26–42 นิ้ว) แล้วถามกลับตรงๆ ว่า 'ปกติพี่ใส่เอวเท่าไหร่คะ?' เท่านั้น",
                "- ถ้าลูกค้าระบุไซส์ที่ต้องการแล้ว (เช่น 'เอา 4 XL', 'รับ 2XL') หรือแจ้งเอว/สะโพก/น้ำหนักมาแล้ว ให้ยึดไซส์จริงของลูกค้าเป๊ะ ห้ามเผลอตอบไซส์ M หรือแนะนำไซส์ M ให้ลูกค้าไซส์อื่นเด็ดขาด!",
                "- ห้ามเดาหรือเขียนยืนยันรหัสรุ่น (เช่น XRP53) หรือยอดเงิน (เช่น 2,400) ที่ลูกค้าไม่ได้สั่งจริง",
                "- สไตล์การปิดการขายแบบแอดมินจริง (ห้ามเกริ่นยืดยาว ห้ามจบแบบปล่อยลูกค้าเงียบ): ทุกครั้งที่ตอบคำถามลูกค้า (เช่น เปลี่ยนได้ไหม / กี่วันถึง / เอวสูงไหม / ราคาเท่าไหร่ / ความยาว) ให้ตอบสั้นชัดใน 1 ประโยค + การันตีความมั่นใจ (เช่น 'ใส่ไม่พอดีส่งเปลี่ยนได้ / มีหน้าร้านจริงของตรงปก') แล้วปิดท้าย enter3 ด้วยการเร่งปิดออเดอร์ทันที: ถ้ารู้ไซส์/เอวแล้วให้ถาม 'รับไซส์ ... เป็นโอนส่งฟรี EMS หรือเก็บเงินปลายทางดีคะ ขอชื่อ ที่อยู่ เบอร์โทรไว้ให้หนูเตรียมจัดส่งได้เลยค่ะ?' ถ้ายังไม่รู้เอวให้ถามควบ 'ปกติใส่เอวเท่าไหร่คะ รับโอนหรือเก็บเงินปลายทางดีคะ?'",
                "- ชั้นเชิงเมื่อลูกค้าแจ้งเอว สะโพก น้ำหนัก หรือเลือกไซส์: ห้ามถามถ่วงเวลา (ห้ามถามว่าชอบขากระบอกเล็กหรือทรงปล่อย) ให้ฟันธงไซส์ + บอกของพร้อมส่ง 1-2 วันถึง + ราคาตรงตาม Ad/Post เป๊ะ + ถามปิดทันที 'รับไซส์ ... เป็นโอนหรือเก็บเงินปลายทางดีคะ ขอชื่อ ที่อยู่ เบอร์โทรไว้ให้หนูเตรียมจัดส่งได้เลยค่ะ?'",
                "- ถ้าลูกค้าทักแรก/เม้นถาม ('สนใจ', 'ขอรายละเอียด') ไม่ต้องเกริ่นน้ำท่วมทุ่ง: แจ้งจุดเด่นสั้นๆ + ของพร้อมส่ง + ราคาตรง Ad + ถามรวบ 'ปกติใส่เอวเท่าไหร่คะ รับโอนหรือเก็บเงินปลายทางดีคะ?'",
                "- ถ้าลูกค้าถามราคา (เช่น 'ราคาค่ะ', 'เท่าไรคะ', 'ตัวเท่าไร') ต้องตอบราคาที่ตรงกับ Ad/Post ทันทีใน enter1 หรือ enter2 ห้ามข้ามคำถามราคาแล้วไปถามเอวอย่างเดียวเด็ดขาด",
                "- ถ้าลูกค้าแจ้งน้ำหนักอย่างเดียว (เช่น 'หนัก 78', 'หนัก 99 โล') ให้แนะนำไซส์ที่เหมาะสมตามเกณฑ์จริงทันที พร้อมแจ้งราคาและถามปิดการขาย 'โอนหรือเก็บเงินปลายทางดีคะ'",
                "- ถ้าลูกค้าแจ้งเอว >= 43 นิ้ว ให้ตอบตรงๆ ว่าใหญ่สุดของร้านคือ 4XL (เอว 40-42) ยังไม่มีถึงไซส์นั้น",
                "- มาตรฐานไซส์จริงของแอดมิน: เอว 34 สะโพก 44 ให้แนะนำ 2XL (ผ้ายีนส์ยืด ใส่สวยพอดี), เอว 39-40 สะโพก 48 ให้แนะนำ 4XL, และถ้าลูกค้าหรือแอดมินเลือกไซส์ไว้แล้วให้ยึดไซส์นั้นเป็นหลัก",
                "- อ่านบริบทสินค้าที่ลูกค้าสนใจให้แม่น: ถ้าคุยเรื่องกระโปรงหรือกางเกงขาสั้น ห้ามถามเรื่องทรงขากระบอกเล็ก/ทรงปล่อยเด็ดขาด",
                "- ตอบกระชับ ตรงประเด็นเหมือนแอดมินคนจริง: ถ้าลูกค้าถาม กทม./อุบลฯ/จังหวัดอื่นมีหน้าร้านไหม ให้ตอบว่ายังไม่มี ระบุ 3 สาขาและบอกว่าสั่งส่ง EMS 1-2 วันถึง; ถ้าลูกค้าบอกยังไม่ไปวันนี้/สอบถามไว้ก่อน ให้ตอบรับสุภาพสั้นๆ ห้ามยัดเยียด; ถ้าลูกค้าถามตัดขาได้ไหม ให้ตอบว่าได้ พร้อมแจ้งความยาว 39 นิ้ว และถามว่าจะตัดเองหรือให้ร้านตัดให้; ถ้าลูกค้าถามเรื่องสีตก/ซัก ให้ยืนยันว่าผ้ายีนส์ฟอกแล้ว สีไม่ตก ซักได้เลย; ถ้าลูกค้าบอกไซส์กางเกงแบรนด์อื่น (เช่น ลีวาย 28) ให้ถามก่อนว่าผ้ายืดไหมเพื่อเทียบไซส์ให้แม่น; ถ้าลูกค้าถามรุ่นที่คนขายใส่หรือขอเช็กสต็อกเฉพาะตัว ห้ามเดาว่ามีของให้แจ้งว่าต้องเช็กสต็อกหน้างาน; ถ้าลูกค้าขอตารางไซส์ ให้ส่งตารางไซส์ M-4XL ชัดเจนแล้วถามปิดทันทีว่ารับไซส์ไหน/เอวเท่าไหร่ และโอนหรือปลายทางดีคะ; ถ้าลูกค้าเก่าสั่งซ้ำหรือพิมพ์ 'ที่อยู่เดิม'/'ไซส์เดิม'/'เปลี่ยนที่อยู่ใหม่' ให้รับเรื่องตรงๆ และถามยืนยัน 'รับไซส์เดิมที่อยู่เดิมเลยไหมคะ ปลายทางเหมือนเดิมนะคะ' เพื่อปิดออเดอร์ทันที",
            ]
            if branch == "ONLINE" and intent != "ASK_BRANCH":
                no_repeat_rules.append("- แชทนี้อยู่ช่องทาง ONLINE: ห้ามเอ่ยถึงหน้าร้านหรือสาขาโคราช/ขอนแก่น/อุดรเด็ดขาด")
            elif branch in ("KORAT", "KKC", "UDN"):
                no_repeat_rules.append(f"- แชทนี้อยู่สาขา {branch} ({BRANCH_MAP.get(branch, '')}): ห้ามเอ่ยถึงสาขาอื่นเด็ดขาด และตอบให้ตรงบริบทล่าสุดของลูกค้า")
            if already_covered.get("sent_price"):
                no_repeat_rules.append("- ห้ามบอกราคาซ้ำแบบเดิม ให้เสริมความคุ้มค่าแทน")
            if already_covered.get("sent_branch_kkc") or already_covered.get("sent_branch_korat") or already_covered.get("sent_branch_udn"):
                no_repeat_rules.append("- ห้ามส่งพิกัดสาขาซ้ำยืดยาว (ส่งไปแล้ว)")
            if already_covered.get("asked_address"):
                no_repeat_rules.append("- ห้ามทวงชื่อ-ที่อยู่-เบอร์โทร หรือเร่งให้สั่งเด็ดขาด!")
            no_repeat_rules.append("- กางเกงมีสีเดียวตรงตามแบบในรูป ห้ามถามลูกค้าว่าชอบสีเข้มหรือสีฟอกสว่างเด็ดขาด")
            if already_covered.get("asked_size"):
                no_repeat_rules.append("- ถามไซส์/เอวไปแล้ว ห้ามถามเอวซ้ำ และห้ามถามคำถามจุกจิกที่ไม่จำเป็น ให้ช่วยเช็กสต็อก/สรุปปิดการขาย หรือนัดวันเข้าสาขาแทน")
            recent_sent = already_covered.get("recent_bot_texts") or []
            if recent_sent:
                no_repeat_rules.append("- ห้ามใช้ประโยคซ้ำกับที่เพิ่งส่งไป: " + " | ".join(t[:60] for t in recent_sent[-3:]))

            mode_desc = (
                f"FOLLOW-UP (ลูกค้าตอบช้า รอบที่ {followup_stage + 1}): ทวนบริบทเดิมอย่างสุภาพ + เพิ่มข้อมูลใหม่ที่มีประโยชน์ + ไม่กดดัน"
                if is_followup
                else f"INSTANT REPLY (ตอบทันที): ตอบตรงคำถามล่าสุดของลูกค้า (Intent: {intent})"
            )
            branch_already_sent = (
                already_covered.get("sent_branch_kkc")
                or already_covered.get("sent_branch_korat")
                or already_covered.get("sent_branch_udn")
            )
            skip_4enter = any(
                k in last_c_raw
                for k in (
                    "ยังไม่ได้ไป", "ยังไม่สะดวก", "วันหลัง", "โอกาสหน้า", "ขอบคุณ",
                    "ซื้อมาแล้ว", "ซื้อแล้ว", "ซักได้", "สีตก", "ตัดขา", "เปลี่ยนไซส์",
                    "อุบล", "กทม", "กรุงเทพ", "เชียงใหม่", "ภูเก็ต", "ชลบุรี", "พัทยา", "หาดใหญ่",
                )
            )
            is_branch_4enter = (
                branch in ("KORAT", "KKC", "UDN")
                and (not is_followup)
                and (not branch_already_sent)
                and (not skip_4enter)
                and intent in ("GREETING_INTEREST", "ASK_BRANCH")
            )
            enter_spec = (
                "4 ข้อความสั้นๆ (4 Enter): enter1 พิกัด+เบอร์สาขานี้, enter2 ห้องลอง+โปรหน้าร้าน 10%-20%, enter3 ผ้า+ไซส์ M-4XL+ราคา, enter4 คำถามเปิด 1 ข้อ"
                if is_branch_4enter
                else "1-3 ข้อความสั้นๆ (Enter ละ 1 ประโยคสั้นๆ) **ตอบตามบริบทจริงล่าสุดของลูกค้าเป็นหลัก**: ถ้าลูกค้าเล่าว่าซื้อแล้ว/ชม/ขอบคุณ ให้ขอบคุณอย่างจริงใจและแนะนำถนอมผ้าสั้นๆ ห้ามขายซ้ำหรือส่งพิกัดซ้ำ; ถ้าลูกค้าถามเฉพาะจุดให้ตอบตรงประเด็นนั้นอย่างเป็นธรรมชาติเหมือนแอดมินคนจริงๆ"
            )
            json_fmt = '{"enter1": "...", "enter2": "...", "enter3": "...", "enter4": "..."}' if is_branch_4enter else '{"enter1": "...", "enter2": "...", "enter3": "..."}'

            fact_hints = []
            if facts_check.get("size_label"):
                fact_hints.append(f"ไซส์ที่คำนวณได้แม่นยำ: {facts_check['size_label']} (ยึดไซส์นี้เป๊ะ)")
            if facts_check.get("waist_too_big"):
                fact_hints.append(f"ลูกค้าเอว {facts_check.get('waist')} นิ้ว เกินไซส์ใหญ่สุดของร้าน (4XL เอว 38-42) ต้องแจ้งตรงๆ อย่างสุภาพว่าใหญ่สุดคือ 4XL")
            if facts_check.get("waist_too_small"):
                fact_hints.append(f"ลูกค้าเอว {facts_check.get('waist')} นิ้ว เล็กกว่าไซส์เล็กสุดของร้าน (M เอว 26-28) ต้องแจ้งตรงๆ อย่างสุภาพ")
            fact_hint_str = (" | ".join(fact_hints)) if fact_hints else "ยังไม่มีสัดส่วนชัดเจน (ถ้าลูกค้าถามไซส์ให้ถามเอว/สะโพก)"

            prompt = f"""คุณคือ "เซียนแอดมินปิดการขายคนจริง" ของร้าน Jeans Around พูดจาเป็นธรรมชาติเหมือนคนพิมพ์แชทจริงๆ (ห้ามใช้ภาษาหุ่นยนต์/ภาษาทางการแข็งๆ ห้ามขึ้นต้นซ้ำซากแบบเทมเพลต) ใช้แทนตัวว่า "หนู" หรือตอบกระชับเป็นกันเอง เรียกลูกค้าว่า "พี่{_clean_short_name(customer_name)}" (ไม่จำเป็นต้องเรียกชื่อทุกประโยค)
ภารกิจ: ตอบแชทลูกค้าเป็น {enter_spec}

ข้อมูลร้าน:
{BRAND_KNOWLEDGE}

สาขา/ช่องทางของแชทนี้: {branch} ({BRANCH_MAP.get(branch, '')})
บริบท Ad ที่ลูกค้าทักมา: {ad_context or 'ไม่ระบุ'}
{('รายละเอียด Ad: ' + matched_ad_kb.get('creative_summary', '')) if matched_ad_kb else ''}
ข้อมูลสัดส่วนที่คำนวณได้: {fact_hint_str}

ตัวอย่างคำตอบแอดมินเพจที่เรียนรู้มา:
{patterns_str or '(ใช้มาตรฐานร้าน)'}

โหมดการทำงาน: {mode_desc}

กฎเหล็กห้ามซ้ำ/ห้ามปนสาขา/ห้ามทำให้ลูกค้าด่า (Grill Guard):
- ตอบคำถามล่าสุดของลูกค้าก่อนเสมอใน enter1 แบบคนจริงคุยกัน (เช่น ถามซิปหน้าตอบเรื่องซิปหน้า ถามยืดไหมตอบเรื่องยืด ถามราคาตอบราคาตรง Ad) อย่าเพิ่งยิงขายยาวถ้ายังไม่ตอบคำถามเขา
- ห้ามอารัมภบทหรือเกริ่นยาวเด็ดขาด! แต่ละ enter ต้องสั้นมาก **ไม่เกิน 1 บรรทัด (ไม่เกิน 45 ตัวอักษร)** เหมือนแม่ค้าคนจริงพิมพ์แชทในมือถือแล้วซอย enter และถ้าลูกค้าจบประโยค/ตัดสินใจแล้ว (เช่น "เดี๋ยวแวะมาดูเอง", "สั่งแล้ว") ให้ตอบรับสั้นๆ 1 ประโยคพอ ห้ามชวนคุยขายซ้ำ!
- อ่านประวัติแชททั้งหมดและข้อความล่าสุดของลูกค้าให้เข้าใจบริบทก่อนตอบเสมอ ห้ามตอบหลุดบริบทหรือถามซ้ำสิ่งที่ลูกค้าพิมพ์บอกมาแล้ว
- ตอบราคา รุ่น รหัส ประเภทสินค้า (กางเกง/กระโปรง/ขาสั้น) และสาขาให้ตรงตามบริบท Ad/Post และข้อความลูกค้าเป๊ะ 100% ห้ามมั่วเด็ดขาด (ถ้า Ad/Post เขียน 990 ห้ามตอบ 1,290; ถ้า Ad/Post เป็นกระโปรง ห้ามถามเรื่องขากางเกง)
- ถ้าลูกค้าระบุไซส์ที่ต้องการแล้ว (เช่น "เอา 4 XL", "รับ 2XL") ให้ยืนยันไซส์นั้นทันที ห้ามแนะนำไซส์อื่นทับ และห้ามเดาสัดส่วนเอง
- ห้ามใช้เครื่องหมาย ** (markdown bold) ในข้อความเด็ดขาด
{chr(10).join(no_repeat_rules)}

ประวัติแชทล่าสุด (16 ข้อความ):
{chat_history_str}

>>> ข้อความล่าสุดที่ลูกค้าเพิ่งพิมพ์ (ต้องตอบให้ตรงบริบทข้อความนี้เป็นหลัก): "{latest_cust_line}"

ตอบกลับเป็น JSON เท่านั้น: {json_fmt}"""

            if time.time() < globals().get("_GEMINI_429_UNTIL", 0.0):
                cand_models = []
            else:
                cand_models = dict.fromkeys(["gemini-3.5-flash", "gemini-flash-latest", "gemini-flash-lite-latest", "gemini-2.5-flash", model_name])
            for cand_model in cand_models:
                try:
                    gen_cfg = types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.65,
                        thinking_config=types.ThinkingConfig(thinking_budget=0),
                    )
                except Exception:
                    gen_cfg = types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.65,
                    )
                try:
                    resp = client.models.generate_content(
                        model=cand_model,
                        contents=prompt,
                        config=gen_cfg,
                    )
                    LAST_LLM_STATUS.update({"model": cand_model, "ok": True, "error": "", "at": time.strftime("%H:%M:%S")})
                    data = json.loads(resp.text)
                    keys = ("enter1", "enter2", "enter3", "enter4") if is_branch_4enter else ("enter1", "enter2", "enter3")
                    bubbles = [(data.get(k) or "").replace("**", "").strip() for k in keys if (data.get(k) or "").strip()]
                    joined_b = " ".join(bubbles)
                    asking_store = intent == "ASK_BRANCH" or any(k in latest_cust_line for k in ("หน้าร้าน", "สาขา", "อยู่ไหน", "จังหวัด", "where", "shop", "store", "branch", "location", "address", "mall"))
                    other_branches = () if (asking_store or _is_english_query(latest_cust_line)) else {
                        "KORAT": ("ขอนแก่น", "อุดร"),
                        "KKC": ("โคราช", "อุดร"),
                        "UDN": ("โคราช", "ขอนแก่น"),
                        "ONLINE": ("โคราช", "ขอนแก่น", "อุดร"),
                    }.get(branch, ())
                    leaked_branch = any(ob in joined_b for ob in other_branches)
                    if bubbles and not leaked_branch and not (is_followup and _is_dup_bubble(bubbles[0], recent_sent)):
                        if not is_followup and messages and not _is_english_query(latest_cust_line):
                            session_msgs = _recent_session_messages(messages, hours=18)
                            has_prior = any(
                                (m.get("sender_role") == "bot")
                                or (
                                    m.get("sender_role") == "admin"
                                    and not is_auto_ad_greeting_text(
                                        m.get("text") or "",
                                        session_msgs[idx - 1].get("text") or "" if idx > 0 else "",
                                    )
                                )
                                for idx, m in enumerate(session_msgs[:-1])
                            )
                            if has_prior:
                                short_name = _clean_short_name(customer_name)
                                call_name = f"พี่{short_name}" if short_name else "พี่"
                                cust_text = " ".join((m.get("text") or "") for m in session_msgs if m.get("sender_role") == "customer").lower()
                                facts = _extract_body_facts(cust_text, last_cust_only=last_c_raw, asked_waist=bool(already_covered.get("asked_size")))
                                bubbles = _polish_human_flow(bubbles, call_name, branch, BRANCH_MAP.get(branch, BRANCH_MAP["ONLINE"]), already_covered, facts)
                        return _enforce_1line_human_bubbles(bubbles)
                except Exception as inner_e:
                    err_s = str(inner_e)
                    LAST_LLM_STATUS.update({"model": cand_model, "ok": False, "error": err_s[:180], "at": time.strftime("%H:%M:%S")})
                    print(f"[Brain3Enter] {cand_model} error: {inner_e}")
                    if "429" in err_s or "RESOURCE_EXHAUSTED" in err_s:
                        globals()["_GEMINI_429_UNTIL"] = time.time() + 900
                        break
                    continue
        except Exception as e:
            LAST_LLM_STATUS.update({"model": "init", "ok": False, "error": str(e)[:180], "at": time.strftime("%H:%M:%S")})
            print(f"[Brain3Enter] Gemini fallback due to error: {e}")

    res = _build_fallback_3enter(
        customer_name=customer_name,
        branch=branch,
        intent=intent,
        already_covered=already_covered,
        ad_context=ad_context,
        is_followup=is_followup,
        followup_stage=followup_stage,
        messages=messages,
    )
    if not is_followup and intent not in ("AFTER_SALES_THANKS", "SHIPPING_TRACKING") and messages:
        last_c = next(((m.get("text") or "").lower() for m in reversed(messages) if m.get("sender_role") == "customer"), "")
        session_msgs = _recent_session_messages(messages, hours=18)
        has_prior = any(
            (m.get("sender_role") == "bot")
            or (
                m.get("sender_role") == "admin"
                and not is_auto_ad_greeting_text(
                    m.get("text") or "",
                    session_msgs[idx - 1].get("text") or "" if idx > 0 else "",
                )
            )
            for idx, m in enumerate(session_msgs[:-1])
        )
        if has_prior and not _is_english_query(last_c):
            short_name = _clean_short_name(customer_name)
            call_name = f"พี่{short_name}" if short_name else "พี่"
            cust_text = " ".join((m.get("text") or "") for m in session_msgs if m.get("sender_role") == "customer").lower()
            facts = _extract_body_facts(cust_text, last_cust_only=last_c, asked_waist=bool(already_covered.get("asked_size")))
            facts["_last_cust"] = last_c
            res = _polish_human_flow(res, call_name, branch, BRANCH_MAP.get(branch, BRANCH_MAP["ONLINE"]), already_covered, facts)
    return _enforce_1line_human_bubbles(res)


def _enforce_1line_human_bubbles(bubbles: List[str], max_len: int = 54, max_bubbles: int = 4) -> List[str]:
    """Keep each bubble to a crisp 1-line human-style chat message without dropping core answer or closing question."""
    cleaned = [(b or "").strip() for b in bubbles if (b or "").strip()]
    if not cleaned:
        return bubbles
    closing = cleaned[-1]
    body = cleaned[:-1]
    out: List[str] = []
    def _split_clean_1line(text: str, limit: int) -> List[str]:
        if len(text) <= limit or "http" in text or "ตาราง" in text or "\n" in text:
            return [text]
        # Protect parenthesized segments so we never break inside (...)
        tokens = re.findall(r"\([^)]*\)|\S+", text)
        if len(tokens) <= 1:
            return [text]
        chunks: List[str] = []
        cur = ""
        for tok in tokens:
            cand = f"{cur} {tok}".strip() if cur else tok
            if len(cand) <= limit or not cur:
                cur = cand
            else:
                chunks.append(cur)
                cur = tok
        if cur:
            chunks.append(cur)
        return chunks

    for s in body:
        if len(s) <= max_len or "http" in s or "ตาราง" in s or "\n" in s or s.startswith("📍"):
            out.append(s)
            continue
        parts = [p.strip() for p in re.sub(r"(นะคะ|นะครับ|เลยค่ะ|เลยน้า|ได้ค่ะ|ได้น้า|ค่ะ|คะ|ค่า)(?=\s|$)\s*", r"\1|||", s).split("|||") if p.strip()]
        # Merge short salutation like "พี่นุชคะ" with the actual answer so we NEVER drop the core answer!
        if len(parts) > 1 and len(parts[0]) < 18:
            parts = [f"{parts[0]} {parts[1]}".strip()] + parts[2:]
        if len(parts) > 1 and len(parts[0]) <= max_len + 16:
            out.append(parts[0])
        elif parts and len(parts[0]) <= max_len + 16:
            out.append(parts[0])
        else:
            out.extend(_split_clean_1line(parts[0] if parts else s, max_len + 10)[:2])
    # Keep at most (max_bubbles - 1) body bubbles + ALWAYS keep the closing question at the end
    out = out[: max(1, max_bubbles - 1)]
    clean_closing = re.sub(r"\?+", "", closing).strip() if ("http" not in closing and re.search(r"[ก-๙]", closing)) else closing
    if len(clean_closing) <= max_len + 8 or "http" in clean_closing or "ตาราง" in clean_closing or "\n" in clean_closing:
        out.append(clean_closing)
    else:
        c_parts = [p.strip() for p in re.sub(r"(ค่ะ|นะคะ|เลยน้า|ได้น้า|ค่า|คะ)(?=\s|$)\s*", r"\1|||", clean_closing).split("|||") if p.strip()]
        chosen = c_parts[-1] if (c_parts and len(c_parts[-1]) >= 12) else clean_closing
        out.extend(_split_clean_1line(chosen, max_len + 8)[:2])
    # Human-tone sanitizer + remove '?' from Thai messages + drop any standalone '?' or duplicate bubble
    _TONE_FIXES = (
        ("ลองสวม", "ลองใส่"),
        ("สวมเทียบ", "ลองเทียบ"),
        ("ได้สบายใจ", "ได้ค่ะ"),
        ("มีบริการเก็บเงินปลายทาง", "มีเก็บปลายทาง"),
        ("ทางร้าน", "ที่ร้าน"),
        ("ขอบพระคุณ", "ขอบคุณ"),
        ("สะดวกให้หนู", "ให้หนู"),
        ("ได้เลยได้เลย", "ได้เลย"),
    )
    final_out: List[str] = []
    for item in out:
        if "http" not in item:
            if not item.startswith("📍"):
                for _old, _new in _TONE_FIXES:
                    if _old in item:
                        item = item.replace(_old, _new)
            if re.search(r"[ก-๙]", item) or re.fullmatch(r"[\s?.,!]+", item):
                item = re.sub(r"\?+", "", item).strip()
        if item and item not in final_out:
            final_out.append(item)
    return final_out
