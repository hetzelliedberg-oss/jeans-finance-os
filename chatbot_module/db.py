"""SQLite persistence layer for Jeans Around AI Chatbot."""

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional


def get_data_dir() -> str:
    render_dir = "/opt/render/project/src/data"
    if os.path.isdir("/opt/render/project/src"):
        os.makedirs(render_dir, exist_ok=True)
        return render_dir
    local_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    os.makedirs(local_dir, exist_ok=True)
    return local_dir


DB_PATH = os.path.join(get_data_dir(), "chatbot.db")


BKK_TZ = timezone(timedelta(hours=7))


def utc_now_iso() -> str:
    """Return current Thailand (Asia/Bangkok, +07:00) ISO timestamp."""
    return datetime.now(BKK_TZ).isoformat()


def to_bkk_iso(dt_str: str) -> str:
    """Normalize any ISO/Meta timestamp (Z, +0000, +07:00, naive) to Asia/Bangkok (+07:00) ISO."""
    s = (dt_str or "").strip()
    if not s:
        return utc_now_iso()
    try:
        norm = s[:-1] + "+00:00" if s.endswith("Z") else s
        if len(norm) >= 5 and norm[-5] in ("+", "-") and ":" not in norm[-5:]:
            norm = norm[:-2] + ":" + norm[-2:]
        dt = datetime.fromisoformat(norm)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=BKK_TZ)
        return dt.astimezone(BKK_TZ).isoformat()
    except Exception:
        return s


def _ts_epoch(dt_str: str) -> float:
    """Parse ISO/Meta timestamp to POSIX epoch seconds for exact chronological ordering."""
    s = (dt_str or "").strip()
    if not s:
        return 0.0
    try:
        norm = s[:-1] + "+00:00" if s.endswith("Z") else s
        if len(norm) >= 5 and norm[-5] in ("+", "-") and ":" not in norm[-5:]:
            norm = norm[:-2] + ":" + norm[-2:]
        dt = datetime.fromisoformat(norm)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=BKK_TZ)
        return dt.timestamp()
    except Exception:
        return 0.0


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=15.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS conversations (
                psid TEXT PRIMARY KEY,
                conv_id TEXT,
                customer_name TEXT,
                branch TEXT DEFAULT 'ONLINE',
                ad_id TEXT,
                ad_name TEXT,
                campaign_name TEXT,
                status TEXT DEFAULT 'OPEN',
                blacklist_reason TEXT,
                last_customer_msg_at TEXT,
                last_bot_msg_at TEXT,
                last_admin_msg_at TEXT,
                last_msg_id TEXT,
                followup_stage INTEGER DEFAULT 0,
                next_followup_at TEXT,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS messages (
                msg_id TEXT PRIMARY KEY,
                psid TEXT NOT NULL,
                sender_role TEXT NOT NULL,
                text TEXT,
                ad_context TEXT,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_messages_psid_time ON messages(psid, created_at);

            CREATE TABLE IF NOT EXISTS ad_knowledge (
                ad_id TEXT PRIMARY KEY,
                ad_name TEXT,
                campaign_name TEXT,
                branch TEXT DEFAULT 'ONLINE',
                creative_summary TEXT,
                top_questions_json TEXT DEFAULT '[]',
                winning_replies_json TEXT DEFAULT '[]',
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS learned_patterns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic TEXT NOT NULL,
                branch TEXT DEFAULT 'ONLINE',
                customer_intent TEXT NOT NULL,
                customer_example TEXT,
                admin_reply_example TEXT,
                enter1 TEXT,
                enter2 TEXT,
                enter3 TEXT,
                win_count INTEGER DEFAULT 1,
                updated_at TEXT NOT NULL,
                UNIQUE(topic, branch, customer_intent)
            );

            CREATE TABLE IF NOT EXISTS grill_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                psid TEXT NOT NULL,
                customer_name TEXT,
                trigger_type TEXT NOT NULL,
                decision TEXT NOT NULL,
                reason TEXT,
                bubbles_json TEXT DEFAULT '[]',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                psid TEXT NOT NULL,
                fb_name TEXT,
                recipient_name TEXT,
                phone TEXT,
                address TEXT,
                items TEXT,
                payment_method TEXT DEFAULT 'ปลายทาง',
                amount INTEGER DEFAULT 1290,
                branch TEXT DEFAULT 'ONLINE',
                ad_name TEXT,
                telegram_sent INTEGER DEFAULT 0,
                raw_summary TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS media_assets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tag TEXT NOT NULL,
                sku TEXT DEFAULT '',
                title TEXT DEFAULT '',
                url TEXT UNIQUE NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS customers_crm (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fb_name TEXT UNIQUE NOT NULL,
                recipient_name TEXT,
                phone TEXT,
                address TEXT,
                last_sku TEXT,
                order_count INTEGER DEFAULT 1,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS self_audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                psid TEXT NOT NULL,
                outcome TEXT NOT NULL,
                note TEXT,
                created_at TEXT NOT NULL
            );
            """
        )

        env_model = os.getenv("GEMINI_MODEL", "gemini-3-flash-preview").strip()
        if env_model == "gemini-3.8-flash":
            env_model = "gemini-3-flash-preview"
        defaults = {
            "auto_pilot_enabled": os.getenv("AUTO_PILOT_ENABLED", "false").lower(),
            "dry_run_mode": os.getenv("DRY_RUN_MODE", "true").lower(),
            "poll_interval_sec": "2",
            "followup_delays_min": "15,60,180,720",
            "max_auto_followups": os.getenv("MAX_AUTO_FOLLOWUPS", "4"),
            "gemini_model": env_model,
            "last_learn_at": "",
        }
        for k, v in defaults.items():
            conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, str(v)))

        # Normalize any historical +0000 / Z timestamps in messages to +07:00 so SQLite DESC order matches real time.
        legacy_rows = conn.execute(
            "SELECT msg_id, created_at FROM messages WHERE created_at LIKE '%+0000' OR created_at LIKE '%Z'"
        ).fetchall()
        for lr in legacy_rows:
            conn.execute(
                "UPDATE messages SET created_at = ? WHERE msg_id = ?",
                (to_bkk_iso(lr["created_at"]), lr["msg_id"]),
            )


def get_settings() -> Dict[str, str]:
    with get_conn() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        return {r["key"]: r["value"] for r in rows}


def update_setting(key: str, value: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, str(value)),
        )


def get_bool_setting(key: str, default: bool = False) -> bool:
    val = get_settings().get(key)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def upsert_conversation(data: Dict[str, Any]) -> None:
    now = utc_now_iso()
    with get_conn() as conn:
        existing = conn.execute("SELECT * FROM conversations WHERE psid = ?", (data["psid"],)).fetchone()
        if existing:
            fields = []
            vals = []
            for k in (
                "conv_id",
                "customer_name",
                "branch",
                "ad_id",
                "ad_name",
                "campaign_name",
                "status",
                "blacklist_reason",
                "last_customer_msg_at",
                "last_bot_msg_at",
                "last_admin_msg_at",
                "last_msg_id",
                "followup_stage",
                "next_followup_at",
            ):
                if k in data and (data[k] is not None or k in ("next_followup_at", "blacklist_reason")):
                    fields.append(f"{k} = ?")
                    vals.append(data[k])
            fields.append("updated_at = ?")
            vals.append(now)
            vals.append(data["psid"])
            conn.execute(f"UPDATE conversations SET {', '.join(fields)} WHERE psid = ?", vals)
        else:
            conn.execute(
                """
                INSERT INTO conversations (
                    psid, conv_id, customer_name, branch, ad_id, ad_name, campaign_name,
                    status, blacklist_reason, last_customer_msg_at, last_bot_msg_at,
                    last_admin_msg_at, last_msg_id, followup_stage, next_followup_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data["psid"],
                    data.get("conv_id"),
                    data.get("customer_name", "ลูกค้า"),
                    data.get("branch", "ONLINE"),
                    data.get("ad_id"),
                    data.get("ad_name"),
                    data.get("campaign_name"),
                    data.get("status", "OPEN"),
                    data.get("blacklist_reason"),
                    data.get("last_customer_msg_at"),
                    data.get("last_bot_msg_at"),
                    data.get("last_admin_msg_at"),
                    data.get("last_msg_id"),
                    data.get("followup_stage", 0),
                    data.get("next_followup_at"),
                    now,
                ),
            )


def get_conversation(psid: str) -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM conversations WHERE psid = ?", (psid,)).fetchone()
        return dict(row) if row else None


def list_conversations(limit: int = 100) -> List[Dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM conversations ORDER BY COALESCE(last_customer_msg_at, updated_at) DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def save_message(msg_id: str, psid: str, sender_role: str, text: str, created_at: str, ad_context: Optional[str] = None) -> bool:
    norm_ts = to_bkk_iso(created_at)
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO messages (msg_id, psid, sender_role, text, ad_context, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (msg_id, psid, sender_role, text or "", ad_context, norm_ts),
        )
        return cur.rowcount > 0


def get_messages(psid: str, limit: int = 30) -> List[Dict[str, Any]]:
    with get_conn() as conn:
        # Fetch a wider window in case any legacy unnormalized rows have mixed offsets, then sort by real epoch.
        fetch_lim = max(limit * 3, limit + 40)
        rows = conn.execute(
            "SELECT * FROM messages WHERE psid = ? ORDER BY created_at DESC LIMIT ?",
            (psid, fetch_lim),
        ).fetchall()
        items = [dict(r) for r in rows]
        items.sort(key=lambda r: (_ts_epoch(r.get("created_at") or ""), r.get("msg_id") or ""))
        return items[-limit:] if limit > 0 else items


def log_grill(psid: str, customer_name: str, trigger_type: str, decision: str, reason: str, bubbles: List[str]) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO grill_logs (psid, customer_name, trigger_type, decision, reason, bubbles_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (psid, customer_name, trigger_type, decision, reason, json.dumps(bubbles, ensure_ascii=False), utc_now_iso()),
        )


def list_grill_logs(limit: int = 60) -> List[Dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM grill_logs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            try:
                d["bubbles"] = json.loads(d.pop("bubbles_json") or "[]")
            except Exception:
                d["bubbles"] = []
            out.append(d)
        return out


def upsert_ad_knowledge(
    ad_id: str,
    ad_name: str,
    campaign_name: str,
    branch: str,
    creative_summary: str,
    top_questions: List[str],
    winning_replies: List[str],
) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO ad_knowledge (
                ad_id, ad_name, campaign_name, branch, creative_summary,
                top_questions_json, winning_replies_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ad_id) DO UPDATE SET
                ad_name=excluded.ad_name,
                campaign_name=excluded.campaign_name,
                branch=excluded.branch,
                creative_summary=excluded.creative_summary,
                top_questions_json=excluded.top_questions_json,
                winning_replies_json=excluded.winning_replies_json,
                updated_at=excluded.updated_at
            """,
            (
                ad_id,
                ad_name,
                campaign_name,
                branch,
                creative_summary,
                json.dumps(top_questions, ensure_ascii=False),
                json.dumps(winning_replies, ensure_ascii=False),
                utc_now_iso(),
            ),
        )


def list_ad_knowledge() -> List[Dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM ad_knowledge ORDER BY updated_at DESC").fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["top_questions"] = json.loads(d.pop("top_questions_json") or "[]")
            d["winning_replies"] = json.loads(d.pop("winning_replies_json") or "[]")
            out.append(d)
        return out


def upsert_learned_pattern(
    topic: str,
    branch: str,
    customer_intent: str,
    customer_example: str,
    admin_reply_example: str,
    enter1: str = "",
    enter2: str = "",
    enter3: str = "",
    win_count: int = 1,
) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO learned_patterns (
                topic, branch, customer_intent, customer_example, admin_reply_example,
                enter1, enter2, enter3, win_count, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(topic, branch, customer_intent) DO UPDATE SET
                customer_example=excluded.customer_example,
                admin_reply_example=excluded.admin_reply_example,
                enter1=COALESCE(NULLIF(excluded.enter1, ''), learned_patterns.enter1),
                enter2=COALESCE(NULLIF(excluded.enter2, ''), learned_patterns.enter2),
                enter3=COALESCE(NULLIF(excluded.enter3, ''), learned_patterns.enter3),
                win_count=learned_patterns.win_count + excluded.win_count,
                updated_at=excluded.updated_at
            """,
            (topic, branch, customer_intent, customer_example, admin_reply_example, enter1, enter2, enter3, win_count, utc_now_iso()),
        )


def list_learned_patterns(branch: Optional[str] = None) -> List[Dict[str, Any]]:
    with get_conn() as conn:
        if branch:
            rows = conn.execute(
                "SELECT * FROM learned_patterns WHERE branch = ? OR branch = 'ONLINE' ORDER BY win_count DESC",
                (branch,),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM learned_patterns ORDER BY win_count DESC").fetchall()
        return [dict(r) for r in rows]


def save_order(order: Dict[str, Any]) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO orders (
                psid, fb_name, recipient_name, phone, address, items,
                payment_method, amount, branch, ad_name, telegram_sent, raw_summary, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                order["psid"],
                order.get("fb_name", "ลูกค้า"),
                order.get("recipient_name", "ลูกค้า"),
                order.get("phone", ""),
                order.get("address", ""),
                order.get("items", "XRP53"),
                order.get("payment_method", "ปลายทาง"),
                int(order.get("amount", 1290)),
                order.get("branch", "ONLINE"),
                order.get("ad_name", ""),
                1 if order.get("telegram_sent") else 0,
                order.get("raw_summary", ""),
                utc_now_iso(),
            ),
        )
        return cur.lastrowid


def list_orders(limit: int = 50) -> List[Dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM orders ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]


def get_latest_order_by_psid(psid: str) -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM orders WHERE psid = ? ORDER BY id DESC LIMIT 1", (psid,)).fetchone()
        return dict(row) if row else None


def update_order_by_id(order_id: int, fields: Dict[str, Any]) -> None:
    if not fields:
        return
    with get_conn() as conn:
        cols = [f"{k} = ?" for k in fields.keys()]
        vals = list(fields.values()) + [order_id]
        conn.execute(f"UPDATE orders SET {', '.join(cols)} WHERE id = ?", vals)


def upsert_media_asset(tag: str, url: str, sku: str = "", title: str = "") -> None:
    if not url:
        return
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO media_assets (tag, sku, title, url, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                tag=excluded.tag,
                sku=COALESCE(NULLIF(excluded.sku, ''), media_assets.sku),
                title=COALESCE(NULLIF(excluded.title, ''), media_assets.title)
            """,
            (tag, sku, title, url, utc_now_iso()),
        )


def list_media_assets(limit: int = 50) -> List[Dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM media_assets ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]


def find_media_for_context(tag: str = "", sku: str = "") -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        if sku:
            row = conn.execute("SELECT * FROM media_assets WHERE UPPER(sku) = UPPER(?) ORDER BY id DESC LIMIT 1", (sku,)).fetchone()
            if row:
                return dict(row)
        if tag:
            row = conn.execute("SELECT * FROM media_assets WHERE tag = ? ORDER BY id DESC LIMIT 1", (tag,)).fetchone()
            if row:
                return dict(row)
        return None


def upsert_customer_crm(fb_name: str, recipient_name: str = "", phone: str = "", address: str = "", last_sku: str = "") -> None:
    if not fb_name:
        return
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO customers_crm (fb_name, recipient_name, phone, address, last_sku, order_count, updated_at)
            VALUES (?, ?, ?, ?, ?, 1, ?)
            ON CONFLICT(fb_name) DO UPDATE SET
                recipient_name=COALESCE(NULLIF(excluded.recipient_name, ''), customers_crm.recipient_name),
                phone=COALESCE(NULLIF(excluded.phone, ''), customers_crm.phone),
                address=COALESCE(NULLIF(excluded.address, ''), customers_crm.address),
                last_sku=COALESCE(NULLIF(excluded.last_sku, ''), customers_crm.last_sku),
                order_count=customers_crm.order_count + 1,
                updated_at=excluded.updated_at
            """,
            (fb_name.strip(), recipient_name, phone, address, last_sku, utc_now_iso()),
        )


def find_customer_crm(fb_name: str) -> Optional[Dict[str, Any]]:
    if not fb_name:
        return None
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM customers_crm WHERE LOWER(fb_name) = LOWER(?)", (fb_name.strip(),)).fetchone()
        return dict(row) if row else None


def list_customers_crm(limit: int = 80) -> List[Dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM customers_crm ORDER BY order_count DESC, updated_at DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]


def record_self_audit(psid: str, outcome: str, note: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO self_audit_logs (psid, outcome, note, created_at) VALUES (?, ?, ?, ?)",
            (psid, outcome, note, utc_now_iso()),
        )


def list_self_audits(limit: int = 40) -> List[Dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM self_audit_logs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

