import io
import re
import csv
import base64
import json
from datetime import datetime
from typing import Dict, Any, List, Optional
import requests
import openpyxl

from backend.database import get_db_connection


def normalize_onedrive_url(url: str) -> str:
    """Ensure URL has download parameter or direct download format"""
    clean_url = url.strip()
    if not clean_url:
        return ""
    if "download=1" in clean_url:
        return clean_url
    if "?" in clean_url:
        return f"{clean_url}&download=1"
    return f"{clean_url}?download=1"


def download_onedrive_file(url: str) -> bytes:
    """
    Download binary content from OneDrive / SharePoint shareable link
    Supports 1drv.ms, sharepoint.com, and OneDrive REST API
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    # Attempt 1: Direct GET following redirects with download=1
    direct_url = normalize_onedrive_url(url)
    try:
        resp = requests.get(direct_url, headers=headers, timeout=25, allow_redirects=True)
        if resp.status_code == 200 and len(resp.content) > 100:
            if not (resp.content.startswith(b"<!DOCTYPE") or resp.content.startswith(b"<html")):
                return resp.content
    except Exception as e:
        print(f"[!] Direct download failed: {e}")

    # Attempt 2: Public OneDrive API share token
    try:
        clean_target = url.split("?")[0]
        encoded = base64.urlsafe_b64encode(clean_target.encode("utf-8")).decode("utf-8").rstrip("=")
        share_token = f"u!{encoded}"
        api_url = f"https://api.onedrive.com/v1.0/shares/{share_token}/root/content"
        resp2 = requests.get(api_url, headers=headers, timeout=25, allow_redirects=True)
        if resp2.status_code == 200 and len(resp2.content) > 100:
            return resp2.content
    except Exception as e:
        print(f"[!] OneDrive API download failed: {e}")

    # Fallback to standard requests if it had redirect
    resp3 = requests.get(url, headers=headers, timeout=25, allow_redirects=True)
    if resp3.status_code == 200:
        return resp3.content

    raise ValueError(f"Could not download file from OneDrive link (HTTP {resp3.status_code})")


def parse_date_str(val: Any) -> Optional[str]:
    """Extract YYYY-MM-DD from various formats"""
    if isinstance(val, datetime):
        return val.strftime("%Y-%m-%d")
    s = str(val).strip()
    if not s or s.lower() in ["none", "nan", ""]:
        return None

    # Try ISO YYYY-MM-DD
    m_iso = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", s)
    if m_iso:
        y, m, d = int(m_iso.group(1)), int(m_iso.group(2)), int(m_iso.group(3))
        return f"{y:04d}-{m:02d}-{d:02d}"

    # Try Thai/UK format DD/MM/YYYY
    m_uk = re.search(r"(\d{1,2})[-/](\d{1,2})[-/](\d{2,4})", s)
    if m_uk:
        d, m, y = int(m_uk.group(1)), int(m_uk.group(2)), int(m_uk.group(3))
        if y < 100:
            y += 2000
        elif y > 2500: # Buddhist year
            y -= 543
        return f"{y:04d}-{m:02d}-{d:02d}"

    # Try Day-MonthText e.g. 1-Sep, 12-Sep, 1-ก.ย., 01/Sep/2026
    m_txt = re.search(r"(\d{1,2})[\s\-_/]+([a-zA-Zก-๙]+)(?:[\s\-_/]+(\d{2,4}))?", s)
    if m_txt:
        d = int(m_txt.group(1))
        mon = m_txt.group(2).lower()
        y = int(m_txt.group(3)) if m_txt.group(3) else 2026
        if y < 100:
            y += 2000
        elif y > 2500:
            y -= 543

        m_num = 9 # Default September
        if 'sep' in mon or 'ก.ย' in mon or 'กันยา' in mon:
            m_num = 9
        elif 'aug' in mon or 'ส.ค' in mon or 'สิงหา' in mon:
            m_num = 8
        elif 'oct' in mon or 'ต.ค' in mon or 'ตุลา' in mon:
            m_num = 10
        elif 'jul' in mon or 'ก.ค' in mon or 'กรกฎา' in mon:
            m_num = 7
        elif 'jan' in mon or 'ม.ค' in mon or 'มกรา' in mon:
            m_num = 1
        elif 'feb' in mon or 'ก.พ' in mon or 'กุมภา' in mon:
            m_num = 2
        elif 'mar' in mon or 'มี.ค' in mon or 'มีนา' in mon:
            m_num = 3
        elif 'apr' in mon or 'เม.ย' in mon or 'เมษา' in mon:
            m_num = 4
        elif 'may' in mon or 'พ.ค' in mon or 'พฤษภา' in mon:
            m_num = 5
        elif 'jun' in mon or 'มิ.ย' in mon or 'มิถุนา' in mon:
            m_num = 6
        elif 'nov' in mon or 'พ.ย' in mon or 'พฤศจิกา' in mon:
            m_num = 11
        elif 'dec' in mon or 'ธ.ค' in mon or 'ธันวา' in mon:
            m_num = 12

        return f"{y:04d}-{m_num:02d}-{d:02d}"

    return None


def clean_number(val: Any) -> float:
    """Convert any price/cost string to float safely, handling accounting parentheses (358.80) as negative"""
    if isinstance(val, (int, float)):
        return float(val)
    if not val:
        return 0.0
    s = str(val).replace(",", "").strip()
    is_negative = ("(" in s and ")" in s) or s.startswith("-")
    m = re.search(r"\d*\.?\d+", s)
    if not m or not m.group(0):
        return 0.0
    num = float(m.group(0))
    return -num if is_negative else num


def parse_excel_bytes(content: bytes) -> List[Dict[str, Any]]:
    """Parse Excel sheets for daily closings"""
    wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
    results = []

    for sheet in wb.worksheets:
        rows = list(sheet.iter_rows(values_only=True))
        if not rows:
            continue

        # Look for headers
        header_idx = -1
        col_map = {}
        for idx, row in enumerate(rows[:15]):
            row_str = " ".join(str(c or "").lower() for c in row)
            if any(k in row_str for k in ["วันที่", "date", "ยอดขาย", "sales", "revenue", "รวม"]):
                header_idx = idx
                for c_idx, cell in enumerate(row):
                    txt = str(cell or "").strip().lower()
                    if any(k in txt for k in ["วันที่", "date", "วัน"]):
                        col_map["date"] = c_idx
                    elif any(k in txt for k in ["ยอดขาย", "sales", "revenue", "ยอดรวม", "total"]):
                        col_map["sales"] = c_idx
                    elif any(k in txt for k in ["โอน", "transfer", "bank"]):
                        col_map["transfer"] = c_idx
                    elif any(k in txt for k in ["ปลายทาง", "cod"]):
                        col_map["cod"] = c_idx
                    elif any(k in txt for k in ["ต้นทุน", "cogs", "cost"]):
                        col_map["cogs"] = c_idx
                    elif any(k in txt for k in ["ค่าใช้จ่าย", "expense", "expenses"]):
                        col_map["expenses"] = c_idx
                    elif any(k in txt for k in ["กำไร", "profit", "net"]):
                        col_map["profit"] = c_idx
                    elif any(k in txt for k in ["ตัว", "จำนวนตัว", "pieces", "qty"]):
                        col_map["pieces"] = c_idx
                    elif any(k in txt for k in ["บิล", "ออเดอร์", "orders"]):
                        col_map["orders"] = c_idx
                    elif any(k in txt for k in ["ช่องทาง", "สาขา", "channel"]):
                        col_map["channel"] = c_idx
                break

        start_row = header_idx + 1 if header_idx != -1 else 0
        sheet_title = sheet.title.lower()
        default_channel = "storefront_kkc" if ("ขอนแก่น" in sheet_title or "kkc" in sheet_title or "หน้าร้าน" in sheet_title) else "online"

        for row in rows[start_row:]:
            if not any(row):
                continue

            date_val = None
            if "date" in col_map and col_map["date"] < len(row):
                date_val = parse_date_str(row[col_map["date"]])

            if not date_val:
                for c in row:
                    parsed = parse_date_str(c)
                    if parsed:
                        date_val = parsed
                        break

            if not date_val:
                continue

            sales_val = clean_number(row[col_map["sales"]]) if "sales" in col_map and col_map["sales"] < len(row) else 0.0
            if sales_val == 0.0:
                nums = [clean_number(c) for c in row if isinstance(c, (int, float))]
                if nums:
                    sales_val = max(nums)

            channel_str = default_channel
            if "channel" in col_map and col_map["channel"] < len(row):
                ch_txt = str(row[col_map["channel"]]).lower()
                if "ขอนแก่น" in ch_txt or "kkc" in ch_txt or "หน้าร้าน" in ch_txt:
                    channel_str = "storefront_kkc"
                elif "ออนไลน์" in ch_txt or "online" in ch_txt:
                    channel_str = "online"

            results.append({
                "report_date": date_val,
                "channel": channel_str,
                "gross_sales": sales_val,
                "transfer_amount": clean_number(row[col_map["transfer"]]) if "transfer" in col_map and col_map["transfer"] < len(row) else 0.0,
                "cod_amount": clean_number(row[col_map["cod"]]) if "cod" in col_map and col_map["cod"] < len(row) else 0.0,
                "cogs": clean_number(row[col_map["cogs"]]) if "cogs" in col_map and col_map["cogs"] < len(row) else 0.0,
                "expenses": clean_number(row[col_map["expenses"]]) if "expenses" in col_map and col_map["expenses"] < len(row) else 0.0,
                "net_profit": clean_number(row[col_map["profit"]]) if "profit" in col_map and col_map["profit"] < len(row) else 0.0,
                "orders_count": int(clean_number(row[col_map["orders"]])) if "orders" in col_map and col_map["orders"] < len(row) else 0,
                "pieces_count": int(clean_number(row[col_map["pieces"]])) if "pieces" in col_map and col_map["pieces"] < len(row) else 0,
                "notes": f"จากแผ่นงาน: {sheet.title}"
            })

    return results


def parse_csv_bytes(content: bytes) -> List[Dict[str, Any]]:
    """Parse CSV content for daily closings"""
    text = ""
    for enc in ["utf-8-sig", "utf-8", "cp874", "tis-620"]:
        try:
            text = content.decode(enc)
            break
        except Exception:
            continue

    if not text:
        return []

    lines = list(csv.reader(io.StringIO(text)))
    results = []
    for row in lines:
        if not row:
            continue
        date_val = None
        for c in row:
            parsed = parse_date_str(c)
            if parsed:
                date_val = parsed
                break
        if not date_val:
            continue

        nums = [clean_number(c) for c in row if re.search(r"\d", c)]
        sales_val = max(nums) if nums else 0.0

        results.append({
            "report_date": date_val,
            "channel": "online" if "ออนไลน์" in text else "storefront_kkc",
            "gross_sales": sales_val,
            "transfer_amount": 0.0,
            "cod_amount": 0.0,
            "cogs": 0.0,
            "expenses": 0.0,
            "net_profit": 0.0,
            "orders_count": 0,
            "pieces_count": 0,
            "notes": "นำเข้าจากไฟล์ CSV"
        })

    return results


def parse_pasted_closing_text(text: str, default_channel: str = "storefront_kkc") -> List[Dict[str, Any]]:
    """
    Parse copy-pasted closing table text from Excel/closing reports.
    Supports transposed label-value format and tabular rows.
    """
    lines = [l.strip() for l in text.strip().split("\n") if l.strip()]
    if not lines:
        return []

    days_data: Dict[str, Dict[str, float]] = {}

    for line in lines:
        parts = re.split(r'\t+|\s{2,}', line)
        if len(parts) >= 2:
            d_str = parse_date_str(parts[0])
            if not d_str:
                m = re.match(r'(\d+)[\s\-_/]+([a-zA-Zก-๙]+)', parts[0].strip())
                if m:
                    d = int(m.group(1))
                    mon = m.group(2).lower()
                    if 'sep' in mon or 'ก.ย' in mon or 'กันยา' in mon:
                        d_str = f"2026-09-{d:02d}"
                    elif 'aug' in mon or 'ส.ค' in mon or 'สิงหา' in mon:
                        d_str = f"2026-08-{d:02d}"

            if not d_str:
                continue

            label = parts[1].strip()
            val_str = parts[2].strip() if len(parts) >= 3 else "0"
            val = clean_number(val_str)

            if d_str not in days_data:
                days_data[d_str] = {}
            days_data[d_str][label] = val

    results = []
    for d, vals in sorted(days_data.items()):
        cash = 0.0
        transfer = 0.0
        cogs = 0.0
        rent = 910.00
        labor = 460.0
        ads = 0.0
        orders = 0
        pieces = 0
        profit = 0.0
        has_profit = False

        for k, v in vals.items():
            k_low = k.lower()
            if "สด" in k or "cash" in k_low:
                cash = v
            elif "โอน" in k or "transfer" in k_low:
                transfer = v
            elif "ทุน" in k or "cogs" in k_low:
                cogs = v
            elif "เช่า" in k or "rent" in k_low:
                rent = v
            elif "พนักงาน" in k or "คน" in k or "labor" in k_low:
                labor = v
            elif "โฆษณา" in k or "แอด" in k or "ads" in k_low:
                ads = v
            elif "กำไร" in k or "ขาดทุน" in k or "profit" in k_low:
                profit = v
                has_profit = True
            elif "ออเดอร์" in k or "order" in k_low:
                orders = int(v)
            elif "ตัว" in k or "piece" in k_low or "qty" in k_low:
                pieces = int(v)

        total_sales = cash + transfer
        if total_sales == 0.0:
            for k, v in vals.items():
                if "ยอดขาย" in k or "sales" in k.lower():
                    total_sales = v
                    break

        expenses = rent + labor + ads
        calc_profit = profit if has_profit else round(total_sales - cogs - expenses, 2)
        results.append({
            "report_date": d,
            "channel": default_channel,
            "gross_sales": total_sales,
            "transfer_amount": transfer,
            "cod_amount": cash,
            "cogs": cogs,
            "expenses": expenses,
            "net_profit": calc_profit,
            "orders_count": orders,
            "pieces_count": pieces,
            "notes": f"นำเข้าจากข้อความปิดวัน (เช่า {rent}, คน {labor}, แอด {ads})"
        })

    return results


def save_onedrive_closings(closings: List[Dict[str, Any]], source_url: str = "") -> int:
    """Upsert list of daily closings into onedrive_closings table and sync to orders table"""
    conn = get_db_connection()
    cur = conn.cursor()
    saved_count = 0
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for item in closings:
        r_date = item["report_date"]
        ch = item["channel"]

        cur.execute("SELECT id FROM onedrive_closings WHERE report_date = ? AND channel = ?", (r_date, ch))
        existing = cur.fetchone()

        if existing:
            cur.execute("""
                UPDATE onedrive_closings SET
                    gross_sales = ?, transfer_amount = ?, cod_amount = ?,
                    cogs = ?, expenses = ?, net_profit = ?,
                    orders_count = ?, pieces_count = ?, source_url = ?,
                    notes = ?, raw_json = ?, created_at = ?
                WHERE id = ?
            """, (
                item["gross_sales"], item["transfer_amount"], item["cod_amount"],
                item["cogs"], item["expenses"], item["net_profit"],
                item["orders_count"], item["pieces_count"], source_url,
                item.get("notes", ""), json.dumps(item, ensure_ascii=False),
                now_str, existing["id"]
            ))
        else:
            cur.execute("""
                INSERT INTO onedrive_closings (
                    report_date, channel, gross_sales, transfer_amount, cod_amount,
                    cogs, expenses, net_profit, orders_count, pieces_count,
                    source_url, notes, raw_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                r_date, ch, item["gross_sales"], item["transfer_amount"], item["cod_amount"],
                item["cogs"], item["expenses"], item["net_profit"],
                item["orders_count"], item["pieces_count"], source_url,
                item.get("notes", ""), json.dumps(item, ensure_ascii=False), now_str
            ))

        # Also sync to orders table for storefront_kkc so dashboard reflects it immediately
        if ch in ["storefront_kkc", "kkc"] and item["gross_sales"] > 0:
            msg_id = f"kkc_closing_{r_date}"
            cur.execute("SELECT id FROM orders WHERE source_channel = 'kkc' AND message_id = ?", (msg_id,))
            ex_ord = cur.fetchone()
            cash_val = item.get("cod_amount", 0.0)
            tr_val = item.get("transfer_amount", 0.0)
            pcs_val = item.get("pieces_count", 0)
            cogs_val = item.get("cogs", 0.0)
            orders_val = item.get("orders_count", 0)
            raw_desc = f"ปิดยอดหน้าร้าน KKC วันที่ {r_date}: ยอดขาย ฿{item['gross_sales']:,.2f} (สด {cash_val:,.2f} / โอน {tr_val:,.2f}) {pcs_val} ตัว {orders_val} คน"
            unit_c = round(cogs_val / max(pcs_val, 1), 2) if pcs_val > 0 else 0.0

            if ex_ord:
                oid = ex_ord["id"]
                cur.execute("""
                    UPDATE orders SET
                        total_pieces = ?, total_sales = ?, transfer_amount = ?,
                        cod_amount = ?, cogs_total = ?, raw_text = ?,
                        sender_name = 'หน้าร้านเซนทรัล KKC', status = 'completed'
                    WHERE id = ?
                """, (pcs_val, item["gross_sales"], tr_val, cash_val, cogs_val, raw_desc, oid))
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
                        ?, ?, ?, 'โอน', ?,
                        ?, ?, 0.0, 'completed', ?,
                        'ลูกค้าหน้าร้าน', 'storefront'
                    )
                """, (msg_id, r_date, f"{r_date} 21:30:00", raw_desc, pcs_val, item["gross_sales"], cash_val, tr_val, cogs_val, now_str))
                oid = cur.lastrowid

            if pcs_val > 0:
                cur.execute("""
                    INSERT INTO order_items (order_id, sku, size, color, quantity, unit_cost, total_cost)
                    VALUES (?, 'KKC_STORE', 'MIX', '', ?, ?, ?)
                """, (oid, pcs_val, unit_c, cogs_val))

        saved_count += 1

    conn.commit()
    conn.close()
    return saved_count


def reconcile_closings_vs_system(start_date: str, end_date: str, channel: str = "online") -> Dict[str, Any]:
    """
    3-Way Reconciliation between System Orders (Chat / Telegram) and OneDrive Daily Closing
    """
    conn = get_db_connection()
    cur = conn.cursor()

    sys_cond = ["status != 'cancelled'", "order_date >= ?", "order_date <= ?"]
    sys_params = [start_date, end_date]
    if channel == "online":
        sys_cond.append("source_channel = 'online'")
    elif channel in ["storefront_kkc", "kkc"]:
        sys_cond.append("source_channel IN ('kkc', 'storefront_kkc')")

    cur.execute(f"""
        SELECT 
            order_date,
            COUNT(id) as orders_count,
            SUM(total_pieces) as pieces_count,
            SUM(total_sales) as gross_sales,
            SUM(transfer_amount) as transfer_sales,
            SUM(cod_amount) as cod_sales,
            SUM(cogs_total) as cogs_total
        FROM orders
        WHERE {' AND '.join(sys_cond)}
        GROUP BY order_date
        ORDER BY order_date ASC
    """, sys_params)
    system_by_date = {r["order_date"]: dict(r) for r in cur.fetchall()}

    od_cond = ["report_date >= ?", "report_date <= ?"]
    od_params = [start_date, end_date]
    if channel == "online":
        od_cond.append("channel = 'online'")
    elif channel in ["storefront_kkc", "kkc"]:
        od_cond.append("channel IN ('kkc', 'storefront_kkc')")

    cur.execute(f"""
        SELECT 
            report_date,
            SUM(gross_sales) as gross_sales,
            SUM(transfer_amount) as transfer_amount,
            SUM(cod_amount) as cod_amount,
            SUM(cogs) as cogs,
            SUM(expenses) as expenses,
            SUM(net_profit) as net_profit,
            SUM(orders_count) as orders_count,
            SUM(pieces_count) as pieces_count,
            MAX(source_url) as source_url
        FROM onedrive_closings
        WHERE {' AND '.join(od_cond)}
        GROUP BY report_date
        ORDER BY report_date ASC
    """, od_params)
    onedrive_by_date = {r["report_date"]: dict(r) for r in cur.fetchall()}

    all_dates = sorted(set(list(system_by_date.keys()) + list(onedrive_by_date.keys())))

    reconcile_rows = []
    total_sys_sales = 0.0
    total_od_sales = 0.0
    total_diff_sales = 0.0

    for d in all_dates:
        sys_data = system_by_date.get(d, {"gross_sales": 0.0, "orders_count": 0, "pieces_count": 0})
        od_data = onedrive_by_date.get(d, {"gross_sales": 0.0, "orders_count": 0, "pieces_count": 0})

        sys_s = float(sys_data.get("gross_sales") or 0.0)
        od_s = float(od_data.get("gross_sales") or 0.0)
        diff_s = sys_s - od_s

        total_sys_sales += sys_s
        total_od_sales += od_s
        total_diff_sales += diff_s

        status = "MATCH"
        if abs(diff_s) > 0.01:
            if sys_s > 0 and od_s == 0:
                status = "MISSING_ONEDRIVE"
            elif sys_s == 0 and od_s > 0:
                status = "MISSING_SYSTEM"
            else:
                status = "DIFF"

        reconcile_rows.append({
            "date": d,
            "system_sales": sys_s,
            "system_orders": sys_data.get("orders_count", 0),
            "system_pieces": sys_data.get("pieces_count", 0),
            "onedrive_sales": od_s,
            "onedrive_orders": od_data.get("orders_count", 0),
            "onedrive_pieces": od_data.get("pieces_count", 0),
            "diff_sales": round(diff_s, 2),
            "status": status,
            "is_matched": status == "MATCH"
        })

    conn.close()

    return {
        "channel": channel,
        "date_range": {"start": start_date, "end": end_date},
        "totals": {
            "system_sales": round(total_sys_sales, 2),
            "onedrive_sales": round(total_od_sales, 2),
            "diff_sales": round(total_diff_sales, 2),
            "matched_days": sum(1 for r in reconcile_rows if r["status"] == "MATCH"),
            "total_days": len(reconcile_rows)
        },
        "rows": reconcile_rows
    }
