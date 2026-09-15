import sqlite3
import os
import json
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "finance_hub.db")

# Default SKU Cost Mapping from user
DEFAULT_SKU_COSTS = {
    "AR01": 693.00,
    "AR02": 717.75,
    "AR03": 596.55,
    "AR04": 356.40,
    "AR05": 350.00,
    "AR06": 0.00,
    "AR07": 0.00,
    "AR08": 470.00,
    "AR09": 340.00,
    "AR10": 673.20,
    "AR11": 683.10,
    "AR12": 0.00,
    "AR13": 0.00,
    "AR14": 534.60,
    "AR15": 433.12,
    "AR16": 485.00,
    "AR17": 0.00,
    "AR18": 330.00,
    "AR19": 396.00,
    "AR20": 673.20,
    "AR21": 407.16,
    "AR22": 490.05,
    "AR23": 463.05,
    "AR24": 407.40,
    "AR25": 829.35,
    "AR26": 395.25,
    "AR27": 491.40,
    "AR28": 393.12,
    "AR29": 572.30,
    "AR30": 591.70,
    "AR31": 468.00,
    "AR32": 365.00,
    "AR33": 388.44,
    "AR34": 355.00,
    "AR35": 390.78,
    "AR36": 468.00,
    "AR37": 504.00,
    "AR38": 451.20,
    "AR39": 435.24,
    "AR40": 290.40,
    "AR41": 486.30,
    "AR42": 437.00,
    "AR43": 427.80,
    "AR44": 567.30,
    "AR189": 395.00,
    "AR23ขาว": 399.90,
    "XRP02": 478.95,
    "XRP11": 478.95,
    "XRP12": 395.25,
    "XRP13": 530.10,
    "XRP14": 595.20,
    "XRP15": 469.65,
    "XRP17": 352.50,
    "XRP23": 516.15,
    "XRP46": 539.40,
    "XRP47": 511.50,
    "XRP48": 451.05,
    "XRP49": 432.45,
    "XRP50": 534.75,
    "XRP51": 530.10,
    "XRP53": 502.20,
    "XRP55": 525.45,
    "XRP56": 623.10,
    "XRP57": 534.75,
    "XRP60": 0.00,
    "XRP62": 441.75,
    "XRP63": 525.00,
    "XRP65": 460.00,
    "XRP66": 441.00,
    "XRP67": 495.00
}


def get_db_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db_connection()
    cur = conn.cursor()

    # 1. Table: sku_costs
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sku_costs (
            sku TEXT PRIMARY KEY,
            cost REAL NOT NULL DEFAULT 0.0,
            category TEXT DEFAULT 'Jeans',
            note TEXT DEFAULT '',
            updated_at TEXT
        )
    """)

    # 2. Table: orders
    cur.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_channel TEXT NOT NULL,       -- 'online' or 'kkc'
            message_id TEXT,                    -- Unique ID from telegram or hash
            sender_name TEXT,                   -- Admin name or staff
            order_date TEXT NOT NULL,           -- 'YYYY-MM-DD'
            order_time TEXT,                    -- 'YYYY-MM-DD HH:MM:SS'
            raw_text TEXT,                      -- Original order message
            total_pieces INTEGER DEFAULT 1,     -- Total items
            total_sales REAL NOT NULL DEFAULT 0.0, -- Total price billed
            payment_method TEXT DEFAULT 'โอน', -- 'โอน', 'ปลายทาง', 'เงินสด'
            cod_amount REAL DEFAULT 0.0,        -- Amount collected via COD
            transfer_amount REAL DEFAULT 0.0,   -- Amount paid via transfer/cash
            cogs_total REAL DEFAULT 0.0,        -- Cost of goods sold
            commission_amount REAL DEFAULT 0.0, -- Admin commission (pieces * 10)
            status TEXT DEFAULT 'completed',
            created_at TEXT
        )
    """)

    # Create index on order_date & channel
    cur.execute("CREATE INDEX IF NOT EXISTS idx_orders_date ON orders(order_date)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_orders_channel ON orders(source_channel)")
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_orders_msg_uniq ON orders(source_channel, message_id) WHERE message_id IS NOT NULL")

    # 3. Table: order_items
    cur.execute("""
        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            sku TEXT NOT NULL,
            size TEXT DEFAULT '',
            color TEXT DEFAULT '',
            quantity INTEGER NOT NULL DEFAULT 1,
            unit_cost REAL NOT NULL DEFAULT 0.0,
            total_cost REAL NOT NULL DEFAULT 0.0,
            FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_items_sku ON order_items(sku)")

    # 4. Table: daily_fb_ads
    cur.execute("""
        CREATE TABLE IF NOT EXISTS daily_fb_ads (
            date TEXT PRIMARY KEY,               -- 'YYYY-MM-DD'
            online_spend REAL NOT NULL DEFAULT 0.0, -- Ads spend without 'ขอนแก่น'
            kkc_spend REAL NOT NULL DEFAULT 0.0,    -- Ads spend with 'ขอนแก่น'
            total_spend REAL NOT NULL DEFAULT 0.0,  -- online_spend + kkc_spend
            campaign_details TEXT,                  -- JSON string of campaigns
            updated_at TEXT
        )
    """)

    # 5. Table: onedrive_closings
    cur.execute("""
        CREATE TABLE IF NOT EXISTS onedrive_closings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_date TEXT NOT NULL,           -- 'YYYY-MM-DD'
            channel TEXT NOT NULL,               -- 'online', 'storefront_kkc', 'consolidated'
            gross_sales REAL DEFAULT 0.0,
            transfer_amount REAL DEFAULT 0.0,
            cod_amount REAL DEFAULT 0.0,
            cogs REAL DEFAULT 0.0,
            expenses REAL DEFAULT 0.0,
            net_profit REAL DEFAULT 0.0,
            orders_count INTEGER DEFAULT 0,
            pieces_count INTEGER DEFAULT 0,
            source_url TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            raw_json TEXT DEFAULT '',
            created_at TEXT
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_onedrive_date ON onedrive_closings(report_date)")

    # 6. Table: settings
    cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)

    # Populate default SKU costs if table is empty
    cur.execute("SELECT COUNT(*) FROM sku_costs")
    if cur.fetchone()[0] == 0:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for sku, cost in DEFAULT_SKU_COSTS.items():
            cur.execute("""
                INSERT OR IGNORE INTO sku_costs (sku, cost, category, updated_at)
                VALUES (?, ?, 'Jeans', ?)
            """, (sku.upper(), cost, now_str))
        conn.commit()

    # Populate default settings if not exists
    default_settings = {
        "ONLINE_LABOR_DAILY": "1132.0",      # 333+333+400+33+33
        "ONLINE_COMMISSION_PER_PIECE": "10.0",# 10 THB / piece
        "ONLINE_MISC_PER_ORDER": "3.0",      # 3 THB / order
        "ONLINE_COD_FEE_PCT": "2.14",        # 2.14%

        "KKC_RENT_DAILY": "910.0",           # 910.00 THB / day per user requirement
        "KKC_LABOR_WEEKDAY": "460.0",        # Mon-Thu 460 THB / day
        "KKC_LABOR_WEEKEND": "500.0",        # Fri-Sun 500 THB / day
        "KKC_MISC_PER_ORDER": "6.0",         # 6 THB / order bag

        "AD_ACCOUNT_ID": "act_703804833399837",
        "FB_ACCESS_TOKEN": "EAAGpwBXjbGABQ9OBEe5Ha0gjNLm5r5WQGteb8NBu0owaebyLZBcKpfXZC261ZBxFZABQhsjoqnFoIvMwo2zNCMhxYfUCQixZBDrzYWNDXrJ0K6FtqUxN91qGpb8GTfQKIZAfPRosahjtQbraH0zNO5EqjnjTyTna84kyGk2I7yDZAOQN7KtWEEcZCMljB0KXlr9JvF8oRZAAaSpsfVDZBVZCC4x",
        "TELEGRAM_BOT_TOKEN": "",
        "TELEGRAM_ONLINE_CHAT_ID": "",
        "TELEGRAM_KKC_CHAT_ID": ""
    }

    for k, v in default_settings.items():
        cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))

    conn.commit()
    conn.close()


def get_sku_cost_map():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT sku, cost FROM sku_costs")
    rows = cur.fetchall()
    conn.close()
    return {r["sku"].upper(): float(r["cost"]) for r in rows}


def get_settings():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT key, value FROM settings")
    rows = cur.fetchall()
    conn.close()
    return {r["key"]: r["value"] for r in rows}


def update_setting(key, value):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db()
    print("Database initialized successfully at:", DB_PATH)
    cost_map = get_sku_cost_map()
    print(f"Loaded {len(cost_map)} SKU cost entries.")
