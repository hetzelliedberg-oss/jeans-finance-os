import os
import requests
import json
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List
from backend.database import get_db_connection, get_settings, update_setting

def fetch_and_sync_fb_ads(since_date: str, until_date: str) -> Dict[str, Any]:
    """
    Fetch FB Ads spend from Meta Marketing API day-by-day.
    Classify spend into:
      - Online Ads: spend without 'ขอนแก่น' in campaign name
      - KKC Ads: spend with 'ขอนแก่น' in campaign name
    Saves to daily_fb_ads table.
    """
    settings = get_settings()
    act_id = settings.get("AD_ACCOUNT_ID", "act_703804833399837")
    token = settings.get("FB_ACCESS_TOKEN", "")

    if not act_id or not token:
        return {"success": False, "error": "Missing Ad Account ID or Facebook Access Token"}

    url = f"https://graph.facebook.com/v20.0/{act_id}/insights"
    params = {
        "access_token": token,
        "level": "campaign",
        "time_increment": 1,
        "time_range": json.dumps({"since": since_date, "until": until_date}),
        "fields": "campaign_name,spend,date_start,date_stop",
        "limit": 1000
    }

    try:
        res = requests.get(url, params=params, timeout=20)
        data = res.json()

        if "error" in data:
            return {"success": False, "error": data["error"].get("message", "FB API error")}

        entries = data.get("data", [])
        
        # Group by date
        daily_breakdown: Dict[str, Dict[str, Any]] = {}

        for item in entries:
            c_name = item.get("campaign_name", "")
            spend = float(item.get("spend", 0.0))
            date_str = item.get("date_start")
            if not date_str:
                continue

            if date_str not in daily_breakdown:
                daily_breakdown[date_str] = {
                    "online_spend": 0.0,
                    "kkc_spend": 0.0,
                    "total_spend": 0.0,
                    "campaigns": []
                }

            is_kkc = "ขอนแก่น" in c_name
            if is_kkc:
                daily_breakdown[date_str]["kkc_spend"] += spend
            else:
                daily_breakdown[date_str]["online_spend"] += spend

            daily_breakdown[date_str]["total_spend"] += spend
            daily_breakdown[date_str]["campaigns"].append({
                "campaign_name": c_name,
                "spend": spend,
                "channel": "kkc" if is_kkc else "online"
            })

        # Save to DB
        conn = get_db_connection()
        cur = conn.cursor()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        for d_str, v in daily_breakdown.items():
            cur.execute("""
                INSERT OR REPLACE INTO daily_fb_ads (date, online_spend, kkc_spend, total_spend, campaign_details, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                d_str,
                round(v["online_spend"], 2),
                round(v["kkc_spend"], 2),
                round(v["total_spend"], 2),
                json.dumps(v["campaigns"], ensure_ascii=False),
                now_str
            ))

        conn.commit()
        conn.close()

        return {
            "success": True,
            "synced_days": len(daily_breakdown),
            "dates": list(daily_breakdown.keys())
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


def get_fb_ads_summary(since_date: str, until_date: str) -> Dict[str, Any]:
    """Get aggregated FB Ads spend from DB for given date range"""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT 
            COUNT(date) as days,
            COALESCE(SUM(online_spend), 0.0) as total_online_spend,
            COALESCE(SUM(kkc_spend), 0.0) as total_kkc_spend,
            COALESCE(SUM(total_spend), 0.0) as total_spend
        FROM daily_fb_ads
        WHERE date >= ? AND date <= ?
    """, (since_date, until_date))
    row = cur.fetchone()
    conn.close()

    return {
        "days": row["days"],
        "online_spend": round(row["total_online_spend"], 2),
        "kkc_spend": round(row["total_kkc_spend"], 2),
        "total_spend": round(row["total_spend"], 2)
    }


class AdsSyncWorker:
    def __init__(self):
        self.is_running = False
        self.thread = None

    def start(self):
        if self.is_running:
            return
        self.is_running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.is_running = False

    def _run_loop(self):
        while self.is_running:
            try:
                today = datetime.now()
                since = (today - timedelta(days=14)).strftime("%Y-%m-%d")
                until = today.strftime("%Y-%m-%d")
                res = fetch_and_sync_fb_ads(since, until)
                if res.get("success"):
                    print(f"[FB Ads Sync] Auto-synced {res.get('synced_days')} days of ads up to {until}", flush=True)
            except Exception as e:
                print(f"[FB Ads Sync] Error in auto sync: {e}", flush=True)
            
            # Sleep 15 minutes (900 seconds)
            for _ in range(900):
                if not self.is_running:
                    break
                time.sleep(1)


ads_sync_instance = AdsSyncWorker()


if __name__ == "__main__":
    today = datetime.now()
    since = (today - timedelta(days=7)).strftime("%Y-%m-%d")
    until = today.strftime("%Y-%m-%d")
    print(f"Syncing FB Ads from {since} to {until}...")
    res = fetch_and_sync_fb_ads(since, until)
    print("Sync Result:", res)
    summary = get_fb_ads_summary(since, until)
    print("Summary:", summary)
