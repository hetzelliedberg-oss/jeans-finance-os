import os
import sys
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from fastapi import FastAPI, UploadFile, File, Form, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel

# Ensure backend directory is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

from backend.database import (
    init_db, get_db_connection, get_sku_cost_map,
    get_settings, update_setting
)
from backend.parser import parse_order_message
from backend.finance_engine import calculate_pnl
from backend.fb_ads_client import fetch_and_sync_fb_ads, get_fb_ads_summary, ads_sync_instance
from backend.order_importer import (
    save_order_to_db, import_telegram_export_json,
    import_pasted_text
)
from backend.import_fact_orders import import_fact_orders_from_chat
from backend.migrate_and_import_fb_page import audit_page_vs_telegram
from backend.telegram_bot import telegram_bot_instance
from backend.telethon_client import telethon_manager
from backend.onedrive_engine import (
    download_onedrive_file, parse_excel_bytes, parse_csv_bytes,
    save_onedrive_closings, reconcile_closings_vs_system, parse_pasted_closing_text
)

# Initialize database & schema
init_db()
import_fact_orders_from_chat()

app = FastAPI(title="Jeans Around Finance OS", version="1.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Start background workers: Telegram bot & FB Ads auto-sync
telegram_bot_instance.start()
ads_sync_instance.start()

# ─── PRODUCTION KEEPALIVE + AUTO DB BACKUP ───────────────────────────────────
import threading, time, base64, requests as _req

RENDER_URL = os.environ.get("RENDER_EXTERNAL_URL", "http://localhost:8055")
GH_TOKEN   = os.environ.get("GH_TOKEN", "")
GH_REPO    = os.environ.get("GH_REPO", "hetzelliedberg-oss/jeans-finance-os")
DB_PATH    = os.path.join(BASE_DIR, "data", "finance_hub.db")

def _keepalive_loop():
    """Ping own /api/health every 10 min → Render free tier stays awake 24/7"""
    time.sleep(30)
    print(f"[Keepalive] Started → pinging {RENDER_URL} every 10 min", flush=True)
    while True:
        try:
            _req.get(f"{RENDER_URL}/api/health", timeout=15)
            print(f"[Keepalive] ✅ {datetime.now().strftime('%H:%M')}", flush=True)
        except Exception as e:
            print(f"[Keepalive] ⚠ {e}", flush=True)
        time.sleep(600)

def _backup_db_to_github():
    """Push DB binary to GitHub every night at 02:00 so data survives Render restarts"""
    while True:
        now = datetime.now()
        # Sleep until next 02:00
        next_2am = now.replace(hour=2, minute=0, second=0, microsecond=0)
        if now >= next_2am:
            next_2am = next_2am.replace(day=next_2am.day + 1)
        wait_sec = (next_2am - now).total_seconds()
        print(f"[DB Backup] Next backup at 02:00 (in {wait_sec/3600:.1f}h)", flush=True)
        time.sleep(wait_sec)
        
        if not GH_TOKEN:
            print("[DB Backup] No GH_TOKEN set, skipping", flush=True)
            continue
        try:
            with open(DB_PATH, "rb") as f:
                content = base64.b64encode(f.read()).decode()
            
            api = f"https://api.github.com/repos/{GH_REPO}/contents/data/finance_hub.db"
            headers = {"Authorization": f"token {GH_TOKEN}", "Accept": "application/vnd.github.v3+json"}
            
            # Get current SHA
            r = _req.get(api, headers=headers, timeout=15)
            sha = r.json().get("sha", "")
            
            payload = {
                "message": f"[auto] DB backup {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                "content": content,
                "branch": "main"
            }
            if sha:
                payload["sha"] = sha
            
            r2 = _req.put(api, headers=headers, json=payload, timeout=30)
            if r2.status_code in (200, 201):
                print(f"[DB Backup] ✅ Backed up to GitHub at {datetime.now().strftime('%H:%M')}", flush=True)
            else:
                print(f"[DB Backup] ⚠ GitHub API {r2.status_code}: {r2.text[:100]}", flush=True)
        except Exception as e:
            print(f"[DB Backup] ⚠ {e}", flush=True)

threading.Thread(target=_keepalive_loop, daemon=True, name="keepalive").start()
threading.Thread(target=_backup_db_to_github, daemon=True, name="db-backup").start()
# ─────────────────────────────────────────────────────────────────────────────


# Pydantic models
class ScanTextRequest(BaseModel):
    text: str
    channel: str = "online"
    date: Optional[str] = None


class SkuCostItem(BaseModel):
    sku: str
    cost: float
    category: Optional[str] = "Jeans"
    note: Optional[str] = ""


class SettingsUpdateRequest(BaseModel):
    settings: Dict[str, Any]


class AdsSyncRequest(BaseModel):
    since_date: str
    until_date: str


class StorefrontDailyEntry(BaseModel):
    date: str
    sales: float
    pieces: int
    orders_count: Optional[int] = 0
    note: Optional[str] = "ยอดขายประจำวันสาขาเซนทรัล KKC"


class TelegramPhoneRequest(BaseModel):
    phone: str


class TelegramCodeRequest(BaseModel):
    code: str
    password: Optional[str] = ""


class TelegramSyncRequest(BaseModel):
    chat_id: Any
    channel: str = "storefront_kkc"
    since_date: Optional[str] = "2026-08-01"


class OneDriveLinkRequest(BaseModel):
    url: str
    channel: Optional[str] = "storefront_kkc"


class PasteClosingRequest(BaseModel):
    text: str
    channel: Optional[str] = "storefront_kkc"


# ---------------- API ENDPOINTS ---------------- #

@app.get("/api/health")
def health_check():
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


@app.get("/api/audit")
def get_audit_report(
    start_date: Optional[str] = "2026-08-01",
    end_date: Optional[str] = "2026-09-13"
):
    """Reconcile and audit orders between Facebook Page chat and Telegram"""
    res = audit_page_vs_telegram(start_date, end_date)
    return res


@app.get("/api/pnl")
def get_pnl_report(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    channel: str = "consolidated"
):
    """
    Get full P&L statement, KPI cards, admin leaderboard, and SKU breakdown
    channel: 'consolidated' | 'online' | 'kkc'
    """
    today_str = datetime.now().strftime("%Y-%m-%d")
    s_date = start_date or today_str
    e_date = end_date or s_date
    res = calculate_pnl(s_date, e_date, channel)
    return res


@app.get("/api/orders")
def get_orders_list(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    channel: Optional[str] = None,
    admin: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 100,
    offset: int = 0
):
    """List orders with their items for the given criteria"""
    conn = get_db_connection()
    cur = conn.cursor()

    conditions = ["status != 'cancelled'"]
    params = []

    if start_date:
        conditions.append("order_date >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("order_date <= ?")
        params.append(end_date)
    if channel and channel != "consolidated" and channel != "all":
        conditions.append("source_channel = ?")
        params.append(channel)
    if admin:
        conditions.append("sender_name = ?")
        params.append(admin)
    if search:
        conditions.append("(raw_text LIKE ? OR sender_name LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%"])

    where_clause = " WHERE " + " AND ".join(conditions)

    # Count total
    cur.execute(f"SELECT COUNT(*) FROM orders {where_clause}", params)
    total_count = cur.fetchone()[0]

    # Query rows
    query = f"""
        SELECT * FROM orders
        {where_clause}
        ORDER BY order_date DESC, id DESC
        LIMIT ? OFFSET ?
    """
    cur.execute(query, params + [limit, offset])
    order_rows = cur.fetchall()

    orders_list = []
    for r in order_rows:
        o_dict = dict(r)
        # Fetch items
        cur.execute("SELECT * FROM order_items WHERE order_id = ?", (r["id"],))
        o_dict["items"] = [dict(it) for it in cur.fetchall()]
        orders_list.append(o_dict)

    conn.close()
    return {
        "total": total_count,
        "limit": limit,
        "offset": offset,
        "orders": orders_list
    }


class OrderUpdateRequest(BaseModel):
    order_date: Optional[str] = None
    total_sales: Optional[float] = None
    total_pieces: Optional[int] = None
    payment_method: Optional[str] = None
    cod_amount: Optional[float] = None
    transfer_amount: Optional[float] = None
    source_channel: Optional[str] = None


@app.patch("/api/orders/{order_id}")
def update_order_by_id(order_id: int, req: OrderUpdateRequest):
    conn = get_db_connection()
    cur = conn.cursor()
    updates = []
    params = []
    for k, v in req.dict(exclude_unset=True).items():
        if v is not None:
            updates.append(f"{k} = ?")
            params.append(v)
    if updates:
        params.append(order_id)
        cur.execute(f"UPDATE orders SET {', '.join(updates)} WHERE id = ?", params)
        conn.commit()
    conn.close()
    return {"success": True, "order_id": order_id}



@app.post("/api/storefront/daily-entry")
def record_storefront_daily_entry(req: StorefrontDailyEntry):
    """Record daily sales and pieces for Central Khon Kaen Storefront"""
    conn = get_db_connection()
    cur = conn.cursor()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Average jean cost estimate if not itemized
    sku_cost_map = get_sku_cost_map()
    avg_cost = sum(sku_cost_map.values()) / max(len(sku_cost_map), 1) if sku_cost_map else 495.0
    total_cogs = round(req.pieces * avg_cost, 2)
    orders_cnt = req.orders_count if req.orders_count > 0 else max(req.pieces, 1)

    msg_id = f"kkc_daily_{req.date}"

    # Check existing entry for this day
    cur.execute("SELECT id FROM orders WHERE source_channel = 'kkc' AND message_id = ?", (msg_id,))
    existing = cur.fetchone()

    if existing:
        oid = existing["id"]
        cur.execute("""
            UPDATE orders SET
                total_pieces = ?, total_sales = ?, transfer_amount = ?,
                cogs_total = ?, raw_text = ?, sender_name = 'หน้าร้านเซนทรัล KKC'
            WHERE id = ?
        """, (req.pieces, req.sales, req.sales, total_cogs, req.note, oid))
        cur.execute("DELETE FROM order_items WHERE order_id = ?", (oid,))
    else:
        cur.execute("""
            INSERT INTO orders (
                source_channel, message_id, sender_name, order_date, order_time,
                raw_text, total_pieces, total_sales, payment_method, cod_amount,
                transfer_amount, cogs_total, commission_amount, status, created_at,
                customer_name, platform
            ) VALUES (
                'kkc', ?, 'หน้าร้านเซนทรัล KKC', ?, ?,
                ?, ?, ?, 'โอน', 0.0,
                ?, ?, 0.0, 'completed', ?,
                'ลูกค้าหน้าร้าน', 'storefront'
            )
        """, (msg_id, req.date, f"{req.date} 21:00:00", req.note, req.pieces, req.sales, req.sales, total_cogs, now_str))
        oid = cur.lastrowid

    # Insert default item
    cur.execute("""
        INSERT INTO order_items (order_id, sku, size, color, quantity, unit_cost, total_cost)
        VALUES (?, 'KKC_STORE', 'ALL', '', ?, ?, ?)
    """, (oid, req.pieces, avg_cost, total_cogs))

    conn.commit()
    conn.close()
    return {"success": True, "date": req.date, "sales": req.sales, "pieces": req.pieces, "cogs": total_cogs}


@app.post("/api/orders/scan-text")
def scan_pasted_text(req: ScanTextRequest):
    """Parse text pasted from Telegram and save orders"""
    res = import_pasted_text(req.text, req.channel, req.date or "")
    return res


@app.post("/api/orders/upload-export")
async def upload_telegram_export(
    file: UploadFile = File(...),
    channel: str = Form("online")
):
    """Upload result.json from Telegram Desktop export"""
    content = await file.read()
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        text = content.decode("cp874", errors="ignore")

    res = import_telegram_export_json(text, channel)
    return res


# ---------------- TELEGRAM HUB ENDPOINTS ---------------- #

@app.get("/api/telegram/status")
def telegram_status():
    """Check Telethon authorization and connection status"""
    return telethon_manager.get_status()


@app.post("/api/telegram/login/phone")
def telegram_request_code(req: TelegramPhoneRequest):
    """Request OTP verification code for Telegram account"""
    return telethon_manager.request_login_code(req.phone)


@app.post("/api/telegram/login/code")
def telegram_verify_code(req: TelegramCodeRequest):
    """Submit OTP code to finish Telegram sign-in"""
    return telethon_manager.verify_login_code(req.code, req.password or "")


@app.get("/api/telegram/dialogs")
def telegram_list_dialogs():
    """List Telegram groups/channels to select for sync"""
    return telethon_manager.list_dialogs()


@app.post("/api/telegram/sync")
def telegram_sync_group(req: TelegramSyncRequest):
    """Sync past messages from selected group into orders table"""
    ch = "storefront_kkc" if req.channel in ["kkc", "storefront_kkc"] else "online"
    res = telethon_manager.sync_group_history(req.chat_id, ch, req.since_date or "2026-08-01")
    return res


@app.get("/api/telegram/bot-check")
def telegram_bot_check():
    """Verify Telegram Bot Token, check getMe, and verify Privacy Mode"""
    settings = get_settings()
    token = settings.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        return {"configured": False, "message": "ยังไม่ได้ระบุ Bot Token"}

    import requests
    try:
        r = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=10)
        data = r.json()
        if not data.get("ok"):
            return {"configured": True, "valid": False, "message": "Bot Token ไม่ถูกต้อง", "error": data.get("description")}

        bot_info = data.get("result", {})
        can_read = bot_info.get("can_read_all_group_messages", False)
        bot_username = bot_info.get("username", "")

        return {
            "configured": True,
            "valid": True,
            "bot_username": bot_username,
            "can_read_all_group_messages": can_read,
            "privacy_mode": "Enabled" if not can_read else "Disabled",
            "message": "บอทเชื่อมต่อสำเร็จ"
        }
    except Exception as e:
        return {"configured": True, "valid": False, "error": str(e)}


# ---------------- ONEDRIVE CLOSING & AUDIT ENDPOINTS ---------------- #

@app.post("/api/onedrive/sync-link")
def onedrive_sync_from_link(req: OneDriveLinkRequest):
    """Download daily closing Excel/CSV from OneDrive link and save to database"""
    try:
        content = download_onedrive_file(req.url)
        try:
            closings = parse_excel_bytes(content)
        except Exception:
            closings = parse_csv_bytes(content)

        if not closings:
            return {"success": False, "error": "ไม่พบข้อมูลแถวรายงานปิดวันในไฟล์ หรือโครงสร้างไฟล์ไม่ถูกต้อง"}

        if req.channel and req.channel != "both":
            ch = "storefront_kkc" if req.channel in ["kkc", "storefront_kkc"] else "online"
            for c in closings:
                c["channel"] = ch

        count = save_onedrive_closings(closings, req.url)
        return {"success": True, "imported_closings": count, "data": closings}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/onedrive/upload")
async def onedrive_upload_file(
    file: UploadFile = File(...),
    channel: str = Form("storefront_kkc")
):
    """Upload Excel/CSV file from local machine as fallback"""
    content = await file.read()
    try:
        try:
            closings = parse_excel_bytes(content)
        except Exception:
            closings = parse_csv_bytes(content)

        if not closings:
            return {"success": False, "error": "ไม่พบข้อมูลแถวรายงานปิดวัน"}

        ch = "storefront_kkc" if channel in ["kkc", "storefront_kkc"] else "online"
        for c in closings:
            c["channel"] = ch

        count = save_onedrive_closings(closings, file.filename)
        return {"success": True, "imported_closings": count, "data": closings}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/onedrive/paste-text")
def onedrive_paste_closing_text(req: PasteClosingRequest):
    """Parse and import pasted closing table text (e.g. from Excel/closing report)"""
    try:
        ch = "storefront_kkc" if req.channel in ["kkc", "storefront_kkc"] else "online"
        closings = parse_pasted_closing_text(req.text, ch)
        if not closings:
            return {"success": False, "error": "ไม่พบข้อมูลแถววันที่ในข้อความที่วาง กรุณาตรวจสอบรูปแบบ"}
        count = save_onedrive_closings(closings, "Pasted Text Report")
        return {"success": True, "imported_closings": count, "data": closings}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/api/onedrive/reconcile")
def onedrive_reconcile_report(
    start_date: Optional[str] = "2026-08-01",
    end_date: Optional[str] = "2026-09-13",
    channel: str = "online"
):
    """Reconcile daily orders between Telegram/Chat and OneDrive Closing Report"""
    return reconcile_closings_vs_system(start_date, end_date, channel)


@app.post("/api/ads/sync")
def sync_facebook_ads(req: AdsSyncRequest):
    """Manually trigger sync of Facebook Ads spend"""
    res = fetch_and_sync_fb_ads(req.since_date, req.until_date)
    return res


@app.get("/api/sku-costs")
def list_sku_costs():
    """List all SKU cost entries"""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM sku_costs ORDER BY sku ASC")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


@app.post("/api/sku-costs")
def save_sku_cost(item: SkuCostItem):
    """Add or update an SKU cost"""
    conn = get_db_connection()
    cur = conn.cursor()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    clean_sku = item.sku.strip().upper()
    cur.execute("""
        INSERT INTO sku_costs (sku, cost, category, note, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(sku) DO UPDATE SET
            cost = excluded.cost,
            category = excluded.category,
            note = excluded.note,
            updated_at = excluded.updated_at
    """, (clean_sku, item.cost, item.category or "Jeans", item.note or "", now_str))
    conn.commit()
    conn.close()
    return {"success": True, "sku": clean_sku, "cost": item.cost}


@app.delete("/api/sku-costs/{sku}")
def delete_sku_cost(sku: str):
    """Delete SKU from master table"""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM sku_costs WHERE sku = ?", (sku.upper(),))
    conn.commit()
    conn.close()
    return {"success": True, "deleted": sku}


@app.get("/api/settings")
def get_all_settings():
    """Get all settings"""
    settings = get_settings()
    # Mask token for security
    fb_tok = settings.get("FB_ACCESS_TOKEN", "")
    masked_fb = f"{fb_tok[:10]}...{fb_tok[-6:]}" if len(fb_tok) > 20 else fb_tok
    return {
        "settings": settings,
        "fb_token_masked": masked_fb
    }


@app.post("/api/settings")
def save_settings(req: SettingsUpdateRequest):
    """Update settings"""
    for k, v in req.settings.items():
        update_setting(k, v)
    return {"success": True, "updated": list(req.settings.keys())}


# ---------------- SERVE STATIC FRONTEND ---------------- #
frontend_dir = os.path.join(BASE_DIR, "frontend")
if os.path.exists(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

    @app.get("/")
    def serve_index():
        response = FileResponse(os.path.join(frontend_dir, "index.html"))
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response



if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app:app", host="127.0.0.1", port=8055, reload=True)
