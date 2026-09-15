import os
import sys
import json
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from backend.database import get_db_connection, get_settings


def get_dates_in_range(start_date: str, end_date: str) -> List[datetime]:
    """Generate list of datetimes from start_date to end_date inclusive"""
    try:
        s = datetime.strptime(start_date, "%Y-%m-%d")
        e = datetime.strptime(end_date, "%Y-%m-%d")
        if s > e:
            s, e = e, s
        delta = (e - s).days
        return [s + timedelta(days=i) for i in range(delta + 1)]
    except Exception:
        return [datetime.now()]


def calculate_pnl(start_date: str, end_date: str, channel: str = "consolidated") -> Dict[str, Any]:
    """
    Generate Financial Profit & Loss Statement and KPI breakdown
    channel can be: 'consolidated', 'online', 'kkc'
    """
    conn = get_db_connection()
    cur = conn.cursor()
    settings = get_settings()

    dates_list = get_dates_in_range(start_date, end_date)
    days_count = max(len(dates_list), 1)

    # Base settings
    online_labor_rate = float(settings.get("ONLINE_LABOR_DAILY", "1132.0"))
    online_comm_rate = float(settings.get("ONLINE_COMMISSION_PER_PIECE", "10.0"))
    online_misc_rate = float(settings.get("ONLINE_MISC_PER_ORDER", "3.0"))
    online_cod_fee_pct = float(settings.get("ONLINE_COD_FEE_PCT", "2.14"))

    kkc_rent_rate = float(settings.get("KKC_RENT_DAILY", "910.0"))
    kkc_labor_weekday = float(settings.get("KKC_LABOR_WEEKDAY", "460.0"))
    kkc_labor_weekend = float(settings.get("KKC_LABOR_WEEKEND", "500.0"))
    kkc_misc_rate = float(settings.get("KKC_MISC_PER_ORDER", "6.0"))

    # Fetch FB Ads in range
    cur.execute("""
        SELECT 
            COALESCE(SUM(online_spend), 0.0) as online_ads,
            COALESCE(SUM(kkc_spend), 0.0) as kkc_ads,
            COALESCE(SUM(total_spend), 0.0) as total_ads
        FROM daily_fb_ads
        WHERE date >= ? AND date <= ?
    """, (start_date, end_date))
    fb_row = cur.fetchone()
    fb_online_spend = float(fb_row["online_ads"])
    fb_kkc_spend = float(fb_row["kkc_ads"])

    # Fetch Orders in range
    cur.execute("""
        SELECT * FROM orders
        WHERE order_date >= ? AND order_date <= ? AND status != 'cancelled'
    """, (start_date, end_date))
    all_orders = cur.fetchall()

    online_orders = [o for o in all_orders if o["source_channel"] == "online"]
    kkc_orders = [o for o in all_orders if o["source_channel"] == "kkc"]

    # 1. ONLINE CHANNEL CALCULATION
    online_orders_count = len(online_orders)
    online_pieces = sum(o["total_pieces"] for o in online_orders)
    online_gross_sales = sum(o["total_sales"] for o in online_orders)
    online_cod_rev = sum(o["cod_amount"] for o in online_orders)
    online_transfer_rev = sum(o["transfer_amount"] for o in online_orders)
    online_cogs = sum(o["cogs_total"] for o in online_orders)
    online_gross_profit = online_gross_sales - online_cogs
    online_gross_margin = (online_gross_profit / online_gross_sales * 100) if online_gross_sales > 0 else 0.0

    online_labor = online_labor_rate * days_count
    online_comm = online_pieces * online_comm_rate
    online_misc = online_orders_count * online_misc_rate
    online_cod_fee = online_cod_rev * (online_cod_fee_pct / 100.0)
    online_ads = fb_online_spend
    online_expenses = online_labor + online_comm + online_misc + online_cod_fee + online_ads
    online_net_profit = online_gross_profit - online_expenses
    online_net_margin = (online_net_profit / online_gross_sales * 100) if online_gross_sales > 0 else 0.0

    # 2. KKC STOREFRONT CALCULATION
    kkc_orders_count = len(kkc_orders)
    kkc_pieces = sum(o["total_pieces"] for o in kkc_orders)
    kkc_gross_sales = sum(o["total_sales"] for o in kkc_orders)
    kkc_cogs = sum(o["cogs_total"] for o in kkc_orders)
    kkc_gross_profit = kkc_gross_sales - kkc_cogs
    kkc_gross_margin = (kkc_gross_profit / kkc_gross_sales * 100) if kkc_gross_sales > 0 else 0.0

    kkc_rent = kkc_rent_rate * days_count
    kkc_labor = sum(kkc_labor_weekend if d.weekday() in [4, 5, 6] else kkc_labor_weekday for d in dates_list)
    kkc_misc = kkc_orders_count * kkc_misc_rate
    kkc_ads = fb_kkc_spend
    kkc_expenses = kkc_rent + kkc_labor + kkc_misc + kkc_ads
    kkc_net_profit = kkc_gross_profit - kkc_expenses
    kkc_net_margin = (kkc_net_profit / kkc_gross_sales * 100) if kkc_gross_sales > 0 else 0.0

    # 3. CONSOLIDATED
    cons_orders_count = online_orders_count + kkc_orders_count
    cons_pieces = online_pieces + kkc_pieces
    cons_gross_sales = online_gross_sales + kkc_gross_sales
    cons_cogs = online_cogs + kkc_cogs
    cons_gross_profit = cons_gross_sales - cons_cogs
    cons_gross_margin = (cons_gross_profit / cons_gross_sales * 100) if cons_gross_sales > 0 else 0.0

    cons_expenses = online_expenses + kkc_expenses
    cons_net_profit = cons_gross_profit - cons_expenses
    cons_net_margin = (cons_net_profit / cons_gross_sales * 100) if cons_gross_sales > 0 else 0.0

    # Helper function for percentage formatting
    def pct(val: float, total: float) -> float:
        return round((val / total * 100), 2) if total > 0 else 0.0

    # Format P&L structure based on selected channel
    if channel == "online":
        target_sales = online_gross_sales
        pnl_lines = [
            {"label": "1. ยอดขายรวมออนไลน์ (Online Gross Sales)", "amount": online_gross_sales, "pct": 100.0, "type": "revenue", "bold": True},
            {"label": "   - ยอดโอน (Bank Transfer)", "amount": online_transfer_rev, "pct": pct(online_transfer_rev, target_sales), "type": "sub"},
            {"label": "   - ยอดเก็บเงินปลายทาง (COD)", "amount": online_cod_rev, "pct": pct(online_cod_rev, target_sales), "type": "sub"},
            {"label": "2. หัก ต้นทุนสินค้า (COGS)", "amount": online_cogs, "pct": pct(online_cogs, target_sales), "type": "cost", "bold": True},
            {"label": "3. กำไรขั้นต้นออนไลน์ (Gross Profit)", "amount": online_gross_profit, "pct": online_gross_margin, "type": "gross_profit", "bold": True},
            {"label": "4. ค่าใช้จ่ายออนไลน์ทั้งหมด (Online Expenses):", "amount": online_expenses, "pct": pct(online_expenses, target_sales), "type": "header", "bold": True},
            {"label": "   - ค่าคนทำงานออฟฟิต (1,132 บ./วัน)", "amount": online_labor, "pct": pct(online_labor, target_sales), "type": "expense"},
            {"label": "   - ค่าคอมมิชชั่นแอดมิน (10 บ./ตัว)", "amount": online_comm, "pct": pct(online_comm, target_sales), "type": "expense"},
            {"label": "   - ค่าแอด Facebook Ads ออนไลน์ (หักแคมเปญขอนแก่น)", "amount": online_ads, "pct": pct(online_ads, target_sales), "type": "expense"},
            {"label": "   - ค่าจิปาถะ/แพ็คของออนไลน์ (3 บ./ออเดอร์)", "amount": online_misc, "pct": pct(online_misc, target_sales), "type": "expense"},
            {"label": "   - ค่าธรรมเนียม COD ออนไลน์ (2.14% ยอดปลายทาง)", "amount": online_cod_fee, "pct": pct(online_cod_fee, target_sales), "type": "expense"},
            {"label": "5. กำไรสุทธิออนไลน์ (Net Profit)", "amount": online_net_profit, "pct": online_net_margin, "type": "net_profit", "bold": True}
        ]
        kpi = {
            "sales": online_gross_sales,
            "cogs": online_cogs,
            "gross_profit": online_gross_profit,
            "gross_margin": round(online_gross_margin, 2),
            "expenses": online_expenses,
            "expenses_pct": pct(online_expenses, target_sales),
            "net_profit": online_net_profit,
            "net_margin": round(online_net_margin, 2),
            "orders_count": online_orders_count,
            "pieces_count": online_pieces,
            "cod_amount": online_cod_rev,
            "transfer_amount": online_transfer_rev
        }

    elif channel in ["kkc", "storefront_kkc"]:
        target_sales = kkc_gross_sales
        pnl_lines = [
            {"label": "1. ยอดขายหน้าร้านเซนทรัล KKC (KKC Sales)", "amount": kkc_gross_sales, "pct": 100.0, "type": "revenue", "bold": True},
            {"label": "2. หัก ต้นทุนสินค้าหน้าร้าน (COGS)", "amount": kkc_cogs, "pct": pct(kkc_cogs, target_sales), "type": "cost", "bold": True},
            {"label": "3. กำไรขั้นต้นหน้าร้าน (Gross Profit)", "amount": kkc_gross_profit, "pct": kkc_gross_margin, "type": "gross_profit", "bold": True},
            {"label": "4. ค่าใช้จ่ายหน้าร้าน KKC (Store Expenses):", "amount": kkc_expenses, "pct": pct(kkc_expenses, target_sales), "type": "header", "bold": True},
            {"label": "   - ค่าเช่าพื้นที่หน้าร้าน (910 บ./วัน)", "amount": kkc_rent, "pct": pct(kkc_rent, target_sales), "type": "expense"},
            {"label": "   - ค่าคนหน้าร้าน (จ-พฤ 460 / ศ-อา 500 บ.)", "amount": kkc_labor, "pct": pct(kkc_labor, target_sales), "type": "expense"},
            {"label": "   - ค่าแอด Facebook Ads (เฉพาะแคมเปญขอนแก่น)", "amount": kkc_ads, "pct": pct(kkc_ads, target_sales), "type": "expense"},
            {"label": "   - ค่าจิปาถะ/ถุงใส่สินค้า (6 บ./ออเดอร์)", "amount": kkc_misc, "pct": pct(kkc_misc, target_sales), "type": "expense"},
            {"label": "5. กำไรสุทธิหน้าร้าน KKC (Net Profit)", "amount": kkc_net_profit, "pct": kkc_net_margin, "type": "net_profit", "bold": True}
        ]
        kpi = {
            "sales": kkc_gross_sales,
            "cogs": kkc_cogs,
            "gross_profit": kkc_gross_profit,
            "gross_margin": round(kkc_gross_margin, 2),
            "expenses": kkc_expenses,
            "expenses_pct": pct(kkc_expenses, target_sales),
            "net_profit": kkc_net_profit,
            "net_margin": round(kkc_net_margin, 2),
            "orders_count": kkc_orders_count,
            "pieces_count": kkc_pieces,
            "cod_amount": 0.0,
            "transfer_amount": kkc_gross_sales
        }

    else: # Consolidated
        target_sales = cons_gross_sales
        pnl_lines = [
            {"label": "1. ยอดขายรวมทั้งบริษัท (Consolidated Sales)", "amount": cons_gross_sales, "pct": 100.0, "type": "revenue", "bold": True},
            {"label": "   [ออนไลน์] ยอดขายช่องทางออนไลน์", "amount": online_gross_sales, "pct": pct(online_gross_sales, target_sales), "type": "sub"},
            {"label": "   [หน้าร้าน] ยอดขายหน้าร้านเซนทรัล KKC", "amount": kkc_gross_sales, "pct": pct(kkc_gross_sales, target_sales), "type": "sub"},
            {"label": "2. หัก ต้นทุนสินค้ารวมทั้งบริษัท (Total COGS)", "amount": cons_cogs, "pct": pct(cons_cogs, target_sales), "type": "cost", "bold": True},
            {"label": "3. รวมกำไรขั้นต้น (Consolidated Gross Profit)", "amount": cons_gross_profit, "pct": cons_gross_margin, "type": "gross_profit", "bold": True},
            {"label": "4. ค่าใช้จ่ายช่องทางออนไลน์ (Online Expenses):", "amount": online_expenses, "pct": pct(online_expenses, target_sales), "type": "header", "bold": True},
            {"label": "   - ค่าคนออนไลน์ (1,132 บ./วัน)", "amount": online_labor, "pct": pct(online_labor, target_sales), "type": "expense"},
            {"label": "   - ค่าคอมมิชชั่นแอดมิน (10 บ./ตัว)", "amount": online_comm, "pct": pct(online_comm, target_sales), "type": "expense"},
            {"label": "   - ค่าแอด Facebook Ads ออนไลน์", "amount": online_ads, "pct": pct(online_ads, target_sales), "type": "expense"},
            {"label": "   - ค่าจิปาถะ/แพ็คของออนไลน์ (3 บ./ออเดอร์)", "amount": online_misc, "pct": pct(online_misc, target_sales), "type": "expense"},
            {"label": "   - ค่าธรรมเนียม COD ออนไลน์ (2.14%)", "amount": online_cod_fee, "pct": pct(online_cod_fee, target_sales), "type": "expense"},
            {"label": "5. ค่าใช้จ่ายหน้าร้านเซนทรัล KKC (KKC Expenses):", "amount": kkc_expenses, "pct": pct(kkc_expenses, target_sales), "type": "header", "bold": True},
            {"label": "   - ค่าเช่าหน้าร้านเซนทรัล KKC (910 บ./วัน)", "amount": kkc_rent, "pct": pct(kkc_rent, target_sales), "type": "expense"},
            {"label": "   - ค่าคนหน้าร้านเซนทรัล KKC (460/500 บ.)", "amount": kkc_labor, "pct": pct(kkc_labor, target_sales), "type": "expense"},
            {"label": "   - ค่าแอด Facebook Ads หน้าร้าน KKC", "amount": kkc_ads, "pct": pct(kkc_ads, target_sales), "type": "expense"},
            {"label": "   - ค่าจิปาถะ/ถุงหน้าร้าน KKC (6 บ./ออเดอร์)", "amount": kkc_misc, "pct": pct(kkc_misc, target_sales), "type": "expense"},
            {"label": "6. กำไรสุทธิรวมทั้งบริษัท (Consolidated Net Profit)", "amount": cons_net_profit, "pct": cons_net_margin, "type": "net_profit", "bold": True}
        ]
        kpi = {
            "sales": cons_gross_sales,
            "cogs": cons_cogs,
            "gross_profit": cons_gross_profit,
            "gross_margin": round(cons_gross_margin, 2),
            "expenses": cons_expenses,
            "expenses_pct": pct(cons_expenses, target_sales),
            "net_profit": cons_net_profit,
            "net_margin": round(cons_net_margin, 2),
            "orders_count": cons_orders_count,
            "pieces_count": cons_pieces,
            "online_sales": online_gross_sales,
            "kkc_sales": kkc_gross_sales,
            "online_net_profit": online_net_profit,
            "kkc_net_profit": kkc_net_profit,
            "online_expenses": online_expenses,
            "kkc_expenses": kkc_expenses
        }

    # 4. ADMIN LEADERBOARD & BREAKDOWN
    admin_map: Dict[str, Dict[str, Any]] = {}
    for o in online_orders:
        name = o["sender_name"] or "ไม่ระบุแอดมิน"
        if name not in admin_map:
            admin_map[name] = {"admin_name": name, "orders_count": 0, "pieces": 0, "sales": 0.0, "commission": 0.0}
        admin_map[name]["orders_count"] += 1
        admin_map[name]["pieces"] += o["total_pieces"]
        admin_map[name]["sales"] += o["total_sales"]
        admin_map[name]["commission"] += o["commission_amount"]

    admin_list = sorted(admin_map.values(), key=lambda x: x["sales"], reverse=True)
    for adm in admin_list:
        adm["sales_pct"] = pct(adm["sales"], online_gross_sales)

    # 5. SKU & SIZE BREAKDOWN
    # Query items for orders in this range
    order_ids = [str(o["id"]) for o in (online_orders if channel == "online" else (kkc_orders if channel == "kkc" else all_orders))]
    sku_breakdown: Dict[str, Dict[str, Any]] = {}

    if order_ids:
        cur.execute(f"""
            SELECT sku, size, color, quantity, unit_cost, total_cost
            FROM order_items
            WHERE order_id IN ({','.join(order_ids)})
        """)
        items_rows = cur.fetchall()

        for itm in items_rows:
            sku = itm["sku"].upper()
            size = itm["size"] or "N/A"
            qty = itm["quantity"]
            cost = itm["total_cost"]

            if sku not in sku_breakdown:
                sku_breakdown[sku] = {
                    "sku": sku,
                    "total_pieces": 0,
                    "total_cost": 0.0,
                    "unit_cost": itm["unit_cost"],
                    "sizes": {}
                }
            sku_breakdown[sku]["total_pieces"] += qty
            sku_breakdown[sku]["total_cost"] += cost
            sku_breakdown[sku]["sizes"][size] = sku_breakdown[sku]["sizes"].get(size, 0) + qty

    sku_list = sorted(sku_breakdown.values(), key=lambda x: x["total_pieces"], reverse=True)

    # 6. DAILY TREND IN RANGE (Includes daily fixed costs and daily expenses)
    cur.execute("SELECT date, online_spend, kkc_spend FROM daily_fb_ads WHERE date >= ? AND date <= ?", (start_date, end_date))
    daily_ads_map = {r["date"]: (float(r["online_spend"]), float(r["kkc_spend"])) for r in cur.fetchall()}

    daily_trend = []
    for d in dates_list:
        d_str = d.strftime("%Y-%m-%d")
        d_orders = [o for o in all_orders if o["order_date"] == d_str]
        
        # Channel-filtered orders
        if channel == "online":
            ch_orders = [o for o in d_orders if o["source_channel"] == "online"]
        elif channel == "kkc":
            ch_orders = [o for o in d_orders if o["source_channel"] == "kkc"]
        else:
            ch_orders = d_orders

        d_sales = sum(o["total_sales"] for o in ch_orders)
        d_cogs = sum(o["cogs_total"] for o in ch_orders)
        d_pieces = sum(o["total_pieces"] for o in ch_orders)
        d_gross_profit = d_sales - d_cogs

        # Calculate daily expenses for date d
        on_ads, kkc_ads_val = daily_ads_map.get(d_str, (0.0, 0.0))
        d_online_orders = [o for o in d_orders if o["source_channel"] == "online"]
        d_kkc_orders = [o for o in d_orders if o["source_channel"] == "kkc"]

        d_on_exp = (
            online_labor_rate +
            (sum(o["total_pieces"] for o in d_online_orders) * online_comm_rate) +
            (len(d_online_orders) * online_misc_rate) +
            (sum(o["cod_amount"] for o in d_online_orders) * (online_cod_fee_pct / 100.0)) +
            on_ads
        )

        d_kkc_labor = kkc_labor_weekend if d.weekday() in [4, 5, 6] else kkc_labor_weekday
        d_kkc_exp = (
            kkc_rent_rate +
            d_kkc_labor +
            (len(d_kkc_orders) * kkc_misc_rate) +
            kkc_ads_val
        )

        if channel == "online":
            d_expenses = d_on_exp
        elif channel == "kkc":
            d_expenses = d_kkc_exp
        else:
            d_expenses = d_on_exp + d_kkc_exp

        d_net_profit = d_gross_profit - d_expenses

        daily_trend.append({
            "date": d_str,
            "day_name": d.strftime("%a"),
            "orders": len(ch_orders),
            "pieces": d_pieces,
            "sales": round(d_sales, 2),
            "cogs": round(d_cogs, 2),
            "gross_profit": round(d_gross_profit, 2),
            "expenses": round(d_expenses, 2),
            "net_profit": round(d_net_profit, 2)
        })

    conn.close()

    return {
        "channel": channel,
        "date_range": {"start": start_date, "end": end_date, "days": days_count},
        "kpi": kpi,
        "pnl_statement": pnl_lines,
        "admin_leaderboard": admin_list,
        "sku_breakdown": sku_list,
        "daily_trend": daily_trend
    }
