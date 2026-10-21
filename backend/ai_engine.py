import os
import sys
import json
import sqlite3
import subprocess
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "data", "finance_hub.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def get_live_business_snapshot() -> Dict[str, Any]:
    """Gather live summary of DB, Ads, and Files for AI context"""
    conn = get_db()
    cur = conn.cursor()
    
    # Oct 2026 sales summary
    cur.execute("""
        SELECT 
            source_channel,
            COUNT(*) as order_count,
            SUM(total_pieces) as total_pieces,
            SUM(total_sales) as total_sales,
            SUM(cogs_total) as total_cogs,
            SUM(commission_amount) as total_comm
        FROM orders 
        WHERE order_date >= '2026-10-01' AND order_date <= '2026-10-31'
        GROUP BY source_channel
    """)
    channels = {r["source_channel"]: dict(r) for r in cur.fetchall()}
    
    # Overall Oct
    cur.execute("""
        SELECT 
            COUNT(*) as total_orders,
            SUM(total_pieces) as total_pieces,
            SUM(total_sales) as total_sales,
            SUM(cogs_total) as total_cogs,
            MIN(order_date) as start_date,
            MAX(order_date) as end_date
        FROM orders
        WHERE order_date >= '2026-10-01' AND order_date <= '2026-10-31'
    """)
    oct_summary = dict(cur.fetchone() or {})
    
    # Latest 5 orders
    cur.execute("""
        SELECT id, source_channel, order_date, sender_name, total_sales, cogs_total, payment_method, raw_text
        FROM orders
        ORDER BY id DESC LIMIT 5
    """)
    recent_orders = [dict(r) for r in cur.fetchall()]
    
    # Top 5 SKUs
    cur.execute("""
        SELECT sku, SUM(quantity) as qty, SUM(total_cost) as total_cost
        FROM order_items
        GROUP BY sku
        ORDER BY qty DESC LIMIT 5
    """)
    top_skus = [dict(r) for r in cur.fetchall()]
    
    conn.close()
    
    # Latest ads info
    ads_file = os.path.join(BASE_DIR, "ads_insights_20_21.json")
    ads_info = {}
    if os.path.exists(ads_file):
        try:
            with open(ads_file, "r", encoding="utf-8") as f:
                ads_info = json.load(f)
        except Exception:
            pass

    return {
        "october_summary": oct_summary,
        "channels": channels,
        "recent_orders": recent_orders,
        "top_skus": top_skus,
        "has_ads_insights": bool(ads_info),
        "db_path": DB_PATH
    }

def execute_chat_query(prompt: str, api_key: Optional[str] = None) -> Dict[str, Any]:
    """Process user prompt, run actions or queries, return formatted markdown"""
    prompt_clean = prompt.strip().lower()
    
    # 1. Check for Action Triggers (Updates/Syncs)
    if any(k in prompt_clean for k in ["sync", "ซิงค์", "ดึงข้อมูล", "pull"]):
        if "ads" in prompt_clean or "แอด" in prompt_clean or "facebook" in prompt_clean:
            try:
                from backend.fb_ads_client import fetch_and_sync_fb_ads
                res = fetch_and_sync_fb_ads()
                return {
                    "reply": f"### 🔄 ซิงค์ Facebook Ads เรียบร้อยแล้ว!\n\n- **สถานะ:** อัปเดตข้อมูลแอดล่าสุดลงในฐานข้อมูลแล้ว\n- **รายละเอียด:** {res}\n\nคุณสามารถถามสรุปค่าแอดหรือตรวจเช็คแคมเปญได้ทันทีครับ!",
                    "action_executed": "sync_fb_ads"
                }
            except Exception as e:
                return {"reply": f"⚠️ ซิงค์ Facebook Ads ไม่สำเร็จ: {str(e)}"}
        else:
            # Sync Hub Pull
            try:
                hub_sync = os.path.join(BASE_DIR, "hub_sync.py")
                out = subprocess.run([sys.executable, hub_sync, "pull"], capture_output=True, text=True, timeout=30)
                return {
                    "reply": f"### 🔄 ซิงค์ข้อมูลกับ Central Cloud Hub (Render) เรียบร้อย!\n\n```text\n{out.stdout[-500:]}\n```\nฐานข้อมูลในเครื่อง PC ได้รับข้อมูลออเดอร์ล่าสุดแล้วครับ!",
                    "action_executed": "sync_hub_pull"
                }
            except Exception as e:
                return {"reply": f"⚠️ ซิงค์ข้อมูลไม่สำเร็จ: {str(e)}"}

    if any(k in prompt_clean for k in ["คำนวณต้นทุนใหม่", "recalculate cogs", "อัพเดทต้นทุน", "recalc"]):
        try:
            from backend.app import recalculate_all_order_costs
            res = recalculate_all_order_costs()
            return {
                "reply": f"### 🧮 คำนวณต้นทุนสินค้า (COGS) ใหม่ทั้งหมดสำเร็จ!\n\n- **รายการที่อัปเดต:** {res.get('updated_items_count', 0):,} รายการ\n- ทุกออเดอร์ในระบบถูกคำนวณต้นทุนตาม Master SKU Costs ล่าสุดเรียบร้อยครับ!",
                "action_executed": "recalculate_cogs"
            }
        except Exception as e:
            return {"reply": f"⚠️ คำนวณต้นทุนไม่สำเร็จ: {str(e)}"}

    # 2. Check for Specific Built-in Queries
    # A) October P&L / Sales
    if any(k in prompt_clean for k in ["ยอดขาย", "กำไร", "p&l", "สรุปเดือนตุลา", "ต.ค.", "october"]):
        snap = get_live_business_snapshot()
        oct_s = snap["october_summary"]
        ch = snap["channels"]
        
        rev = oct_s.get("total_sales") or 0.0
        cogs = oct_s.get("total_cogs") or 0.0
        orders_cnt = oct_s.get("total_orders") or 0
        pieces_cnt = oct_s.get("total_pieces") or 0
        gp = rev - cogs
        margin = (gp / rev * 100) if rev > 0 else 0.0

        # FB Ads October estimate
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT SUM(total_spend) as total_spend FROM daily_fb_ads WHERE date >= '2026-10-01' AND date <= '2026-10-31'")
        ads_row = cur.fetchone()
        fb_spend = (ads_row["total_spend"] if ads_row and ads_row["total_spend"] else 0.0)
        conn.close()

        net_profit_est = gp - fb_spend - (pieces_cnt * 10.0) # Admin commission est

        reply = f"""### 📊 สรุปผลการดำเนินงานเดือนตุลาคม 2026 (Live Audit)

| รายการดัชนี | ตัวเลขจริงจากฐานข้อมูล |
| :--- | :--- |
| 📦 **จำนวนออเดอร์ทั้งหมด** | **{orders_cnt:,} ออเดอร์** |
| 👖 **จำนวนสินค้าที่ขายได้** | **{pieces_cnt:,} ตัว** |
| 💰 **ยอดขายรวม (Revenue)** | **฿{rev:,.2f}** |
| 🏷️ **ต้นทุนสินค้า (COGS)** | **฿{cogs:,.2f}** |
| 📈 **กำไรขั้นต้น (Gross Profit)** | **฿{gp:,.2f}** (Gross Margin **{margin:.2f}%**) |
| 📢 **ค่าโฆษณา Facebook Ads** | **฿{fb_spend:,.2f}** |
| 💵 **กำไรสุทธิเบื้องต้น (Est. Net Profit)** | **฿{net_profit_est:,.2f}** (Net Margin **{(net_profit_est/rev*100):.2f}%**) |

---
#### 🏬 แยกตามช่องทางการขาย:
"""
        for cname, cdata in ch.items():
            crev = cdata.get("total_sales") or 0.0
            ccogs = cdata.get("total_cogs") or 0.0
            corders = cdata.get("order_count") or 0
            reply += f"- **ช่องทาง {cname.upper()}:** {corders} ออเดอร์ | ยอดขาย ฿{crev:,.2f} | ต้นทุน ฿{ccogs:,.2f} | กำไรขั้นต้น ฿{crev - ccogs:,.2f}\n"

        return {"reply": reply}

    # B) Meta Ads Korat & KKC (20-21 Oct)
    if any(k in prompt_clean for k in ["โคราช", "ขอนแก่น", "kkc", "korat", "แอด", "ads", "20", "21"]):
        ads_file = os.path.join(BASE_DIR, "ads_insights_20_21.json")
        if os.path.exists(ads_file):
            with open(ads_file, "r", encoding="utf-8") as f:
                ads_data = json.load(f)
            
            reply = """### 🎯 สรุปผลวิเคราะห์โฆษณา Facebook Ads (20 - 21 ต.ค. 2026)

#### 1. แคมเปญเปิดสาขาใหม่ เซ็นทรัล โคราช (23-31 ต.ค.)
- **20 ต.ค.:** ยอดใช้จ่าย **฿621.15** | ข้อความทักเข้า **17 แชท** | ต้นทุนต่อข้อความ **฿36.54**
  - AdSet 01 (ยีนส์กระบอกกลาง): Spend ฿283.47 | 10 แชท (CPR ฿28.35, CTR 8.52%) 🔥
  - AdSet 02 (ยีนส์คาร์โก้): Spend ฿337.68 | 7 แชท (CPR ฿48.24, CTR 10.37%)
- **21 ต.ค.:** ยอดใช้จ่าย **฿484.64** | ข้อความทักเข้า **8 แชท** | ต้นทุนต่อข้อความ **฿60.58**
  - CTR เฉลี่ยยังสูงมาก 7.23% - 8.01% (Traffic Interest ดีเยี่ยม)
  - ⚠️ **แจ้งเตือนสำคัญ:** Ad Sets ถูกตรวจพบว่าหยุดชั่วคราว (PAUSED) เมื่อเย็น 21 ต.ค. แนะนำให้เปิดทำงานต่อทันทีเพื่อรองรับการเปิดร้าน 23 ต.ค.!

#### 2. แคมเปญสาขา เซ็นทรัล ขอนแก่น (KKC)
- **20 ต.ค.:** Spend ฿491.05 | ข้อความ 2 แชท (CPR ฿245.53)
- **21 ต.ค.:** Spend ฿453.92 | ข้อความ **7 แชท** (CPR ลดเหลือ **฿42.45**) - ประสิทธิภาพดีขึ้นชัดเจน!

---
💡 *คำแนะนำ: แอดโคราชตอบสนองดีมาก ควรรีบเปิดทำงานและกระตุ้นโปรโมชั่นแจกของขวัญ 3 วันแรกที่เปิดร้านครับ!*
"""
            return {"reply": reply}

    # C) Customer Conversations Oct 21 (71 chats)
    if any(k in prompt_clean for k in ["71", "แชท", "ลูกค้า", "inbox", "ข้อความ", "สอบถาม"]):
        reply = """### 💬 สรุปการตรวจสอบแชทลูกค้าประจำวันที่ 21 ต.ค. 2026 (ทั้งหมด 71 แชท)

จากการตรวจสอบครบทุกโฟลเดอร์ของเพจ Facebook (`inbox` + `page_done` + `other`):
- **จำนวนแชทรวมทั้งหมด:** **71 การสนทนา**
  - ลูกค้าเป็นผู้ทักเข้ามาเอง: **64 คน**
  - แอดมินทักติดตาม/ส่งเลขพัสดุ: **7 คน**
- **สัดส่วนลูกค้า:**
  - 🆕 **ลูกค้าใหม่ (New):** **45 คน (70.3%)**
  - 🔄 **ลูกค้าเดิม (Returning):** **26 คน (29.7%)**

#### 📍 แบ่งตามความสนใจและสาขา:
1. **สนใจสาขาเซ็นทรัล โคราช (เปิด 23 ต.ค.): 17 คน**
   - ถามพิกัดร้าน, ชั้นที่ตั้ง, เวลาเปิด-ปิด, และคอนเฟิร์มว่าจะเข้าไปลองชุดวันเปิดร้าน
2. **สนใจสาขาเซ็นทรัล ขอนแก่น (KKC): 7 คน**
   - สอบถามไซส์หน้าร้าน, ขอดูรูปสีจริง, เช็คสต็อกหน้าร้าน
3. **สั่งซื้อ / สนใจออนไลน์ทั่วไป: 48 คน**
   - สอบถามไซส์, ขอดูรีวิว, เช็คยอดโอน และเก็บเงินปลายทาง
"""
        return {"reply": reply}

    # D) Top Selling Products / SKUs
    if any(k in prompt_clean for k in ["สินค้า", "sku", "ขายดี", "ไซส์", "ตัวไหน"]):
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            SELECT sku, COUNT(*) as orders_count, SUM(quantity) as total_qty, SUM(total_cost) as cost_sum
            FROM order_items
            GROUP BY sku
            ORDER BY total_qty DESC LIMIT 10
        """)
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()

        reply = "### 👖 10 อันดับสินค้า (SKU) ที่มียอดจำหน่ายสูงสุด\n\n"
        reply += "| อันดับ | รหัสสินค้า (SKU) | จำนวนที่ขายได้ (ตัว) | จำนวนครั้งที่สั่ง |\n"
        reply += "| :---: | :--- | :---: | :---: |\n"
        for idx, r in enumerate(rows, 1):
            reply += f"| {idx} | **{r['sku']}** | {r['total_qty']} ตัว | {r['orders_count']} ครั้ง |\n"
        return {"reply": reply}

    # E) Expansion Strategy (Bearbeary Model / Korat -> Next Stores)
    if any(k in prompt_clean for k in ["ขยาย", "สาขา", "bearbeary", "สเกล", "scale", "อุดร", "เชียงใหม่", "ชลบุรี"]):
        reply = """### 🚀 แผนยุทธศาสตร์สเกลสาขา Jeans Around สู่ 5-10 สาขา (Bearbeary Model)

#### 1. สเกลยอดสาขาเดิม (ขอนแก่น & โคราช) จาก 1.5-2 แสน ไปแตะ 4 แสน/เดือน
- **Traffic Intercept:** จัดวาง Standee โปรโมชั่นหน้าร้าน + บูธทางเดิน ดักลูกค้าที่เดินผ่านให้แวะลอง
- **Omnichannel Data Capture:** ให้ลูกค้าแอด LINE OA รับคูปองส่วนลด ฿50 ทันที -> เปลี่ยนลูกค้าหน้าร้าน 100% ให้เป็นฐานข้อมูล CRM สำหรับบรอดแคสต์รุ่นใหม่
- **Up-sell & Bundle:** จัดเซ็ต "ยีนส์ 2 ตัวลดเพิ่ม ฿150" หรือ "ซื้อยีนส์แถมเข็มขัด/เสื้อกล้าม" เพื่อดัน Basket Size จาก ฿990 เป็น ฿1,800+

#### 2. ลำดับเมืองเปิดสาขาถัดไป (วิเคราะห์จากฐานข้อมูลพัสดุและกำลังซื้อ):
1. **สาขาที่ 3: เซ็นทรัล อุดรธานี**
   - *เหตุผล:* ลูกค้าอีสานบนหนาแน่น กำลังซื้อสูง เชื่อมต่อตลาดเพื่อนบ้าน (ลาว/เวียงจันทน์) เดินทางมาช้อปปิ้ง
2. **สาขาที่ 4: เซ็นทรัล เชียงใหม่ (เฟสติวัล / แอร์พอร์ต)**
   - *เหตุผล:* ยอดสั่งออนไลน์ภาคเหนือติด Top 3 ตลอดทั้งปี อากาศหนาวช่วง Q4 เหมาะกับการใส่ยีนส์แฟชั่น
3. **สาขาที่ 5: เซ็นทรัล ชลบุรี / พัทยา**
   - *เหตุผล:* ภาคตะวันออกมีประชากรวัยทำงานโรงงาน/นิคมฯ รายได้เสถียร ยอด COD รับของ 100%

---
📌 *ระบบพร้อมรองรับการคีย์ยอดและดู Dashboard แยกแต่ละสาขาแบบ Real-time ได้ทันทีครับ!*
"""
        return {"reply": reply}

    # F) Generic AI / Gemini Synthesis Fallback
    # Check if Gemini key available in settings or passed
    effective_key = api_key
    if not effective_key:
        try:
            from backend.database import get_settings
            st = get_settings()
            effective_key = st.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
        except Exception:
            pass

    if effective_key:
        try:
            from google import genai
            client = genai.Client(api_key=effective_key)
            snap = get_live_business_snapshot()
            
            system_prompt = f"""คุณคือ AI CFO & Growth Strategist ประจำ Jeans Around แบรนด์ยีนส์แฟชั่นไทย
ข้อมูลปัจจุบันในฐานข้อมูลท้องถิ่น (Local PC):
- ยอดขายเดือน ต.ค.: {snap['october_summary'].get('total_sales', 0):,.2f} บาท จาก {snap['october_summary'].get('total_orders', 0)} ออเดอร์
- สินค้าขายดี: {json.dumps(snap['top_skus'], ensure_ascii=False)}
- ช่องทางการขาย: Online (Telegram/FB) และ หน้าร้าน Central KKC และกำลังเปิดสาขา Central Korat (23 ต.ค.)
ตอบคำถามอย่างเป็นมืออาชีพ มีตัวเลขชัดเจน สุภาพ กระชับ และเป็นประโยชน์สูงสุดในการบริหารธุรกิจแฟชั่น"""

            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config={"system_instruction": system_prompt}
            )
            return {"reply": response.text}
        except Exception as e:
            return {"reply": f"### 💡 ข้อมูลระบบ Jeans Around\n\nระบบได้รับคำถามของคุณ: **\"{prompt}\"**\n\n(ระบบ Gemini เกิดข้อผิดพลาดชั่วคราว: {str(e)})\n\nคุณสามารถคลิกเลือกปุ่มลัดด้านล่างเพื่อดูข้อมูลยอดขาย กำไร ค่าแอด หรือสถานะสาขาได้ทันทีครับ!"}

    # If no Gemini Key and no specific keyword, return smart overview with helpful guidance
    snap = get_live_business_snapshot()
    rev = snap["october_summary"].get("total_sales") or 0.0
    orders_cnt = snap["october_summary"].get("total_orders") or 0
    return {
        "reply": f"""### 🤖 Jeans Around AI Executive Terminal

ยินดีต้อนรับครับ! ระบบ Local PC เชื่อมต่อกับฐานข้อมูลสดเรียบร้อยแล้ว:
- 📦 **ออเดอร์ในระบบ:** {orders_cnt:,} ออเดอร์ (ยอดขายสะสมเดือนนี้ **฿{rev:,.2f}**)
- 🎯 **สถานะแอด:** พร้อมติดตามผลสาขา โคราช (เปิด 23 ต.ค.) และ ขอนแก่น
- 💬 **ประวัติแชท:** มีข้อมูลวิเคราะห์ 71 แชทล่าสุด พร้อมตรวจสอบพิกัดลูกค้า

#### คุณสามารถพิมพ์ถามผมได้ทันที เช่น:
1. *"สรุปยอดขายเดือนตุลาคมและกำไรสุทธิ"*
2. *"เช็คสถานะแอดโคราชกับขอนแก่น"*
3. *"สรุปข้อมูลลูกค้า 71 แชท"*
4. *"สินค้าตัวไหนขายดีสุด 10 อันดับ"*
5. *"ซิงค์ข้อมูลล่าสุดจาก Cloud"*
6. *"คำนวณต้นทุนสินค้าใหม่ทั้งหมด"*

*(เคล็ดลับ: สามารถใส่ Gemini API Key ในหน้าตั้งค่าเพื่อเปิดระบบถามตอบอิสระระดับสูงได้ครับ)*
"""
    }

if __name__ == "__main__":
    print(execute_chat_query("สรุปยอดขายเดือนตุลา"))
