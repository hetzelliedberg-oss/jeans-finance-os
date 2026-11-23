"""24/7 Meta Ads Spend & Cost-Per-Chat Watchdog (checks every 5 minutes, today's spend only)."""

import json
import os
import time
from datetime import datetime, timedelta, timezone
import requests
from typing import Any, Dict, List

from db import get_settings, update_setting
from meta_client import meta_client
from telegram_notifier import _send_tg, get_admin_dm_ids

BRANCH_KEYWORDS = ("โคราช", "อุดร", "ขอนแก่น", "korat", "udn", "kkc")
OPS_ALERT_COOLDOWN_SEC = 4 * 3600


def _notify_ads_paused(text: str) -> None:
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not bot_token:
        return
    targets = list(get_admin_dm_ids())
    office_id = os.getenv("TELEGRAM_OFFICE_LOPBURI_CHAT_ID", "-5519732256").strip()
    if office_id and office_id not in targets:
        targets.append(office_id)
    for cid in targets:
        _send_tg(bot_token, cid, text)


def _extract_roas(ins: Dict[str, Any], spend: float) -> float:
    for pr in ins.get("purchase_roas", []) or []:
        try:
            val = float(pr.get("value") or 0)
            if val > 0:
                return round(val, 2)
        except Exception:
            pass
    if spend > 0:
        for av in ins.get("action_values", []) or []:
            if av.get("action_type") in ("omni_purchase", "offsite_conversion.fb_pixel_purchase", "purchase"):
                try:
                    return round(float(av.get("value") or 0) / spend, 2)
                except Exception:
                    pass
    return 0.0


def run_ads_monitor_cycle(dry_run: bool = False) -> Dict[str, Any]:
    """Audit active/today-paused ad sets: pause underperformers (ROAS < 2.5), protect/re-open ROAS > 3.0."""
    meta_client.reload_env()
    tok = meta_client.get_user_token()
    ad_acct = meta_client.ad_account_id
    if not tok or not ad_acct:
        return {"ok": False, "error": "Missing FB_ACCESS_TOKEN or AD_ACCOUNT_ID"}

    fields_str = "id,name,status,effective_status,campaign{id,name,status},insights.date_preset(today){spend,cpm,cpc,actions,action_values,purchase_roas}"
    url = f"https://graph.facebook.com/v21.0/{ad_acct}/adsets"
    params = {
        "fields": fields_str,
        "filtering": json.dumps([{"field": "effective_status", "operator": "IN", "value": ["ACTIVE"]}]),
        "limit": 100,
        "access_token": tok,
    }
    r = requests.get(url, params=params, timeout=20)
    data = r.json()
    if "error" in data:
        return {"ok": False, "error": data["error"]}

    checked: List[Dict[str, Any]] = []
    paused: List[Dict[str, Any]] = []
    reactivated: List[Dict[str, Any]] = []

    bkk_now = datetime.now(timezone(timedelta(hours=7)))
    bkk_today = bkk_now.strftime("%Y-%m-%d")
    bkk_hour = bkk_now.hour
    try:
        peak_state = json.loads(get_settings().get("ads_peak_roas_today") or "{}")
    except Exception:
        peak_state = {}
    if peak_state.get("date") != bkk_today:
        peak_state = {"date": bkk_today, "peaks": {}, "cpr_floors": {}, "bot_paused_ids": []}
    peaks: Dict[str, float] = dict(peak_state.get("peaks") or {})
    cpr_floors: Dict[str, float] = dict(peak_state.get("cpr_floors") or {})
    bot_paused_ids: List[str] = list(peak_state.get("bot_paused_ids") or [])
    peaks_changed = False

    adsets_list: List[Dict[str, Any]] = list(data.get("data", []))
    if bot_paused_ids:
        try:
            pr_res = requests.get(
                "https://graph.facebook.com/v21.0/",
                params={"ids": ",".join(bot_paused_ids[:50]), "fields": fields_str, "access_token": tok},
                timeout=15,
            ).json()
            seen_ids = {a.get("id") for a in adsets_list}
            for aid, aobj in pr_res.items():
                if isinstance(aobj, dict) and aobj.get("id") and aid not in seen_ids:
                    adsets_list.append(aobj)
        except Exception:
            pass

    tot_onl_sp = 0.0
    tot_onl_ch = 0
    for _a in adsets_list:
        _cn = ((_a.get("campaign") or {}).get("name") or "") + " " + (_a.get("name") or "")
        if any(k in _cn.lower() for k in BRANCH_KEYWORDS):
            continue
        _ins_l = (_a.get("insights") or {}).get("data", [])
        _ins = _ins_l[0] if _ins_l else {}
        _sp = float(_ins.get("spend") or 0.0)
        if _sp <= 0:
            continue
        _acts = {x["action_type"]: int(float(x.get("value") or 0)) for x in _ins.get("actions", [])}
        _ch = max(_acts.get("onsite_conversion.total_messaging_connection", 0), _acts.get("onsite_conversion.messaging_conversation_started_7d", 0))
        tot_onl_sp += _sp
        tot_onl_ch += _ch
    avg_cpr_online = round(tot_onl_sp / tot_onl_ch, 2) if tot_onl_ch > 0 else 95.0

    for adset in adsets_list:
        adset_id = adset.get("id", "")
        adset_name = adset.get("name", "")
        eff_status = adset.get("effective_status", "")
        camp_name = (adset.get("campaign") or {}).get("name", "")
        ins_list = (adset.get("insights") or {}).get("data", [])
        ins = ins_list[0] if ins_list else {}
        spend = float(ins.get("spend") or 0.0)
        if eff_status == "PAUSED" and spend <= 0:
            continue

        actions = {a["action_type"]: int(float(a.get("value") or 0)) for a in ins.get("actions", [])}
        # Count both new + returning chats (total_messaging_connection fallback to messaging_conversation_started_7d)
        chats = max(
            actions.get("onsite_conversion.total_messaging_connection", 0),
            actions.get("onsite_conversion.messaging_conversation_started_7d", 0),
        )
        cpr = round(spend / chats, 2) if chats > 0 else None
        cpm = round(float(ins.get("cpm") or 0.0), 2)
        cpc = round(float(ins.get("cpc") or 0.0), 2)
        roas = _extract_roas(ins, spend)

        combined = f"{camp_name} {adset_name}".lower()
        is_branch = any(k in combined for k in BRANCH_KEYWORDS)
        is_purchase_obj = "ซื้อ" in combined

        purchases = max(
            actions.get("purchase", 0),
            actions.get("omni_purchase", 0),
            actions.get("offsite_conversion.fb_pixel_purchase", 0),
        )
        # Never auto-reopen paused ads (closed stays closed)
        should_reactivate = False

        should_pause = False
        rule_reason = ""
        if eff_status == "ACTIVE":
            if is_branch:
                # Branch (Korat/UDN/KKC) Cut-Loss (never auto-reopen):
                # 1) spend > 50 THB, 0 chats, and (CPM > 130 or CPC > 3.0) -> PAUSE
                # 2) spend >= 80 THB and 0 chats -> PAUSE
                # 3) spend >= 120 THB and (chats < 2 or CPM > 140) -> PAUSE
                # 4) spend >= 180 THB and CPR > 80 THB/chat -> PAUSE
                cpr_txt = f"{cpr:.0f}฿/ทัก" if cpr is not None else "0 ทัก"
                if spend > 50.0 and chats < 1 and (cpm > 130.0 or cpc > 3.0):
                    should_pause = True
                    rule_reason = f"แอดสาขาใช้งบวันนี้ {spend:.0f}฿ (>50฿) ยัง 0 ทัก และ CPM {cpm:.0f}฿ / CPC {cpc:.2f}฿"
                elif spend >= 80.0 and chats < 1:
                    should_pause = True
                    rule_reason = f"แอดสาขาใช้งบวันนี้ {spend:.0f}฿ (>=80฿) ยัง 0 ทัก (CPM {cpm:.0f}฿)"
                elif spend >= 120.0 and (chats < 2 or cpm > 140.0):
                    should_pause = True
                    rule_reason = f"แอดสาขาใช้งบวันนี้ {spend:.0f}฿ (>=120฿) ได้ {chats} ทัก ({cpr_txt}), CPM {cpm:.0f}฿"
                elif spend >= 180.0 and (cpr is None or cpr > 80.0):
                    should_pause = True
                    rule_reason = f"แอดสาขาใช้งบวันนี้ {spend:.0f}฿ (>=180฿) ค่าทักแพงเกิน {cpr_txt} (>80฿/ทัก)"
            else:
                # Online High-ROAS Guard (never auto-reopen):
                is_purchase_obj = "ซื้อ" in combined
                zero_chat_limit = 220.0 if is_purchase_obj else 180.0
                hard_cpr_cap = 180.0 if is_purchase_obj else 115.0
                cpr_txt = f"{cpr:.0f}฿/ทัก" if cpr is not None else "0 ทัก"
                prev_peak = float(peaks.get(adset_id) or 0.0)
                if spend >= 700.0 and (chats >= 4 or purchases >= 2) and roas > prev_peak:
                    peaks[adset_id] = roas
                    prev_peak = roas
                    peaks_changed = True
                floor_cpr = cpr_floors.get(adset_id)
                if spend >= 400.0 and chats >= 3 and cpr is not None and (floor_cpr is None or cpr < float(floor_cpr)):
                    cpr_floors[adset_id] = cpr
                    floor_cpr = cpr
                    peaks_changed = True
                cheap_chat_shield = (cpr is not None and cpr <= 70.0 and roas >= 2.2 and bkk_hour < 18)
                if spend >= zero_chat_limit and chats < 1:
                    should_pause = True
                    rule_reason = f"D0: แอดออนไลน์ใช้งบ {spend:.0f}฿ (>={zero_chat_limit:.0f}฿) ยัง 0 ทัก -> คัทลอสไว"
                elif spend >= 450.0 and purchases < 1 and roas < 1.5:
                    should_pause = True
                    rule_reason = f"D0.3-Bleeder ({bkk_hour:02d}h): งบ {spend:.0f}฿ (>=450฿) ยัง 0 ซื้อ / ROAS {roas:.2f} (<1.5) -> คัทไว"
                elif spend >= 600.0 and roas < 2.5:
                    should_pause = True
                    rule_reason = f"Spend-ROAS ({bkk_hour:02d}h): งบ {spend:.0f}฿ (>=600฿) แต่ ROAS {roas:.2f} (<2.5) -> คัทลอสทันที"
                elif spend >= 500.0 and is_purchase_obj and cpr is not None and cpr > 120.0 and cpr > round(avg_cpr_online * 1.20, 2) and roas < 4.0:
                    should_pause = True
                    rule_reason = f"Purchase-CPR ({bkk_hour:02d}h): งบ {spend:.0f}฿ ทักแพง {cpr_txt} (>120฿ และ >ค่าเฉลี่ย {avg_cpr_online:.0f}฿ +20%) | ROAS {roas:.2f}"
                elif not cheap_chat_shield:
                    if spend >= 500.0 and (cpr is None or cpr > hard_cpr_cap) and roas < 2.5:
                        should_pause = True
                        rule_reason = f"D1-CPR ({bkk_hour:02d}h): งบ {spend:.0f}฿ ทักแพง {cpr_txt} (>{hard_cpr_cap:.0f}฿) และ ROAS {roas:.2f} (<2.5)"
                    elif spend >= 650.0 and purchases < 1 and (chats < 4 or (cpr is not None and cpr > 130.0)):
                        should_pause = True
                        rule_reason = f"D1-0ซื้อ ({bkk_hour:02d}h): งบ {spend:.0f}฿ ยัง 0 ซื้อ | {chats} ทัก ({cpr_txt})"
                    elif spend >= 700.0 and prev_peak >= 4.0 and roas <= round(prev_peak * 0.65, 2):
                        should_pause = True
                        drop_pct = round((1.0 - (roas / prev_peak)) * 100)
                        rule_reason = f"Trailing Dynamic -35%: Peak {prev_peak:.2f} ร่วง {drop_pct}% -> {roas:.2f} | งบ {spend:.0f}฿"
                    elif spend >= 700.0 and prev_peak >= 3.0 and roas <= round(prev_peak * 0.70, 2) and roas < 2.8 and (cpr is None or cpr > 100.0):
                        should_pause = True
                        drop_pct = round((1.0 - (roas / prev_peak)) * 100)
                        rule_reason = (
                            f"Trailing ROAS Stop: ROAS ร่วง {drop_pct}% ({prev_peak:.2f} -> {roas:.2f}, <2.8) "
                            f"และทัก {cpr_txt} (>100฿) | งบ {spend:.0f}฿"
                        )
                    elif spend >= 700.0 and floor_cpr is not None and cpr is not None and cpr >= round(float(floor_cpr) * 1.20, 2) and cpr > 120.0 and roas < 2.8:
                        should_pause = True
                        spike_pct = round(((cpr / float(floor_cpr)) - 1.0) * 100)
                        rule_reason = (
                            f"Trailing CPR Spike: ต้นทุนทักพุ่ง +{spike_pct}% ({float(floor_cpr):.0f} -> {cpr:.0f}฿, >120฿) "
                            f"และ ROAS {roas:.2f} (<2.8) | งบ {spend:.0f}฿"
                        )
                    elif bkk_hour >= 16 and spend >= 800.0 and (roas < 2.8 or (roas < 3.0 and (cpr is None or cpr > 115.0))):
                        should_pause = True
                        rule_reason = f"D2-เย็น ({bkk_hour:02d}h): งบ {spend:.0f}฿ (>=800฿) ROAS {roas:.2f} | {chats} ทัก ({cpr_txt}) | {purchases} ซื้อ"

        row = {
            "adset_id": adset_id,
            "campaign_name": camp_name,
            "adset_name": adset_name,
            "type": "BRANCH" if is_branch else "ONLINE",
            "effective_status": eff_status,
            "spend_today": round(spend, 2),
            "chats_today": chats,
            "cost_per_chat": cpr,
            "cpm_today": cpm,
            "roas_today": roas,
            "should_pause": should_pause,
            "should_reactivate": should_reactivate,
            "paused": False,
            "reactivated": False,
        }

        if should_reactivate and not dry_run:
            ar = requests.post(
                f"https://graph.facebook.com/v21.0/{adset_id}",
                data={"status": "ACTIVE", "access_token": tok},
                timeout=15,
            ).json()
            if ar.get("success"):
                row["reactivated"] = True
                reactivated.append(row)
                if adset_id in bot_paused_ids:
                    bot_paused_ids.remove(adset_id)
                    peaks_changed = True
                _notify_ads_paused(f"🟢 เปิดแอดคืนอัตโนมัติ (มียอดซื้อกลับมา {purchases} ซื้อ / ROAS {roas:.2f}): {camp_name} | {adset_name}")

        if should_pause and not dry_run:
            pr = requests.post(
                f"https://graph.facebook.com/v21.0/{adset_id}",
                data={"status": "PAUSED", "access_token": tok},
                timeout=15,
            ).json()
            if pr.get("success"):
                row["paused"] = True
                paused.append(row)
                if adset_id not in bot_paused_ids:
                    bot_paused_ids.append(adset_id)
                    peaks_changed = True
                _notify_ads_paused(f"🛑 ปิดแอดอัตโนมัติ: {camp_name} | {adset_name}\nเหตุผล: {rule_reason}")
            else:
                row["pause_error"] = pr

        checked.append(row)

    if peaks_changed:
        update_setting("ads_peak_roas_today", json.dumps({"date": bkk_today, "peaks": peaks, "cpr_floors": cpr_floors, "bot_paused_ids": bot_paused_ids}))

    # Flag broken/zombie setups: Active adsets spending 0 and Active campaigns with all child adsets paused
    zombie_active = [
        {"campaign_name": r["campaign_name"], "adset_name": r["adset_name"], "adset_id": r["adset_id"]}
        for r in checked
        if r["effective_status"] == "ACTIVE" and r["spend_today"] <= 0
    ]

    all_adsets_paused_camps: List[Dict[str, Any]] = []
    try:
        camp_res = requests.get(
            f"https://graph.facebook.com/v21.0/{ad_acct}/campaigns",
            params={
                "fields": "id,name,status,effective_status,adsets{id,name,status,effective_status}",
                "filtering": json.dumps([{"field": "effective_status", "operator": "IN", "value": ["ACTIVE"]}]),
                "limit": 100,
                "access_token": tok,
            },
            timeout=15,
        ).json()
        for c in camp_res.get("data", []):
            childs = (c.get("adsets") or {}).get("data", []) or []
            active_childs = [a for a in childs if a.get("effective_status") == "ACTIVE"]
            if not active_childs:
                all_adsets_paused_camps.append(
                    {
                        "campaign_id": c.get("id", ""),
                        "campaign_name": c.get("name", ""),
                        "adset_count": len(childs),
                        "adset_statuses": [a.get("effective_status") for a in childs],
                    }
                )
    except Exception:
        pass

    # Ops Telegram spam ("⚠️ แจ้งเตือนแอดเปิดอยู่แต่ไม่วิ่ง / ลูกแอดถูกปิดอยู่") disabled per owner request;
    # keep counts & lists in the JSON response below for dashboard inspection only.

    return {
        "ok": True,
        "active_count": len([x for x in checked if x["effective_status"] == "ACTIVE"]),
        "paused_count": len(paused),
        "reactivated_count": len(reactivated),
        "zero_spend_active_count": len(zombie_active),
        "zero_spend_active": zombie_active,
        "active_campaigns_all_adsets_paused_count": len(all_adsets_paused_camps),
        "active_campaigns_all_adsets_paused": all_adsets_paused_camps,
        "paused": paused,
        "reactivated": reactivated,
        "adsets": checked,
    }
