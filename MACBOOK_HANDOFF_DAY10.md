# Jeans Around OS — MacBook Handoff Kit (Day 10 — 2026-11-24)

## 1. วิธีดึงโปรเจกต์ลง MacBook (ทำครั้งเดียว 30 วินาที)
เปิด Terminal บน MacBook แล้วรัน:
```bash
mkdir -p ~/projects && cd ~/projects
git clone https://github.com/hetzelliedberg-oss/jeans-finance-os.git
cd jeans-finance-os
```
จากนั้นเอาไฟล์ `.env` ที่ส่งมาทาง Telegram ไปวางไว้ในโฟลเดอร์ `~/projects/jeans-finance-os/chatbot_module/.env` (และถ้าจะรันสคริปต์ยิง Sweep จาก MacBook ให้วางสำเนาไว้ที่ `~/projects/jeans-finance-os/.env` ด้วย)

เปิดโฟลเดอร์ `~/projects/jeans-finance-os` เป็น Workspace ใน Antigravity บน MacBook ได้เลยครับ

---

## 2. สถานะระบบ Production ปัจจุบัน (อัปเดต Day 10 / commit `5f1e9a7`)
- **Unified Cloud URL (Render):** `https://jeans-finance-os-gma9.onrender.com`
  - Finance OS Health: `/api/health`
  - AI Chatbot + 8-Step Follow-up Status: `/chatbot/api/status`
  - **Auto-Deploy:** ทุกครั้งที่แก้โค้ดใน `chatbot_module/` แล้ว `git push origin main` ตัว Cloud `gma9` จะอัปเดตอัตโนมัติใน ~1–2 นาที
- **ไฟล์หัวใจของบอทที่พัฒนาอยู่:**
  - `chatbot_module/brain_3enter.py` — สมอง Zero-Key 3-Enter (แยกราคา/รุ่น/โพส/สาขา, ดึงที่อยู่เดิมย้อนหลัง 80 ข้อความ, 8-Step Follow-up, ตัดคำโป๊ะบอทครบ 10 หมวด, บล็อกสแปมราคาซ้ำ, ห้ามใช้ `?` ในภาษาไทย)
  - `chatbot_module/grill_engine.py` — ตัวคัดกรองความปลอดภัย (กันทักคนซื้อแล้วใน 24 ชม., กันตามของ/เคลม/เปลี่ยนไซส์/ของไม่ครบ/ส่งรูปสลิป)
  - `chatbot_module/app.py` — Auto-Pilot poller (3 วิ), 8-Step Follow-up (`5,10,20,30,60,120,180,240` นาที), Telegram Handoff/Fraud Alert, Deep 80-msg history lookup
  - `chatbot_module/meta_client.py` — Meta Graph API v21.0 client
- **หมายเหตุ:** ตอนนี้ Cloud `gma9` รัน `Zero-Key` (`has_gemini_key: false`) หากต้องการเปิดพลัง Gemini เสริม แค่เพิ่ม `GEMINI_API_KEY` ใน Render Environment Variables ของ `jeans-finance-os-gma9`

---

## 3. Master Prompt (ก๊อปข้อความด้านล่างไปวางเปิดแชทใหม่บน MacBook ได้เลย)
```text
นี่คือโปรเจกต์ Jeans Around Finance OS + AI Chatbot (Unified Cloud: https://jeans-finance-os-gma9.onrender.com, repo: jeans-finance-os, โฟลเดอร์บอทอยู่ที่ chatbot_module/)

กฎเหล็กที่ต้องยึดตลอด:
1. ตอบลูกค้าแบบมนุษย์นักขายขั้นเทพ: สุภาพ สั้น ซอย 3-4 Enter (1 บรรทัด/ข้อความ) ห้ามใช้ "?" ในภาษาไทย ห้ามใช้คำโป๊ะบอท (สะดวก/ทางร้าน/ลองสวม/สบายใจ/มีบริการ/เกรดพรีเมียม)
2. ห้ามตอบซ้ำประโยค/ซ้ำใจความเดิม ห้ามยิงราคา 1,290 ซ้ำถ้าเคยแจ้งแล้ว
3. แยกราคาตามโพส/รุ่น/รหัส แยกสาขา (ขอนแก่น/โคราช/อุดร) vs ออนไลน์ให้แม่น 100%
4. ห้ามทักขายซ้ำคนที่ซื้อแล้วใน 24 ชม., คนตามของ/เคลม/เปลี่ยนไซส์/ของไม่ครบ
5. แก้โค้ดเสร็จให้รันเทสยืนยันจริง แล้ว git push origin main เพื่อขึ้น Cloud gma9 ทันที
6. รายงานผลด้วยตัวเลขจริงจากเครื่องมือเท่านั้น ห้ามเดา ห้ามมโน

ช่วยเช็กสถานะ Cloud gma9 และเตรียมพร้อมพัฒนาต่อได้เลยครับ
```
