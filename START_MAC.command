#!/bin/bash
cd "$(dirname "$0")"

clear
echo "=========================================================="
echo "   👖 JEANS AROUND FINANCE OS - MACBOOK M1 SETUP"
echo "=========================================================="
echo ""

# 1. Restore Antigravity Brain / AI Memory
BRAIN_SRC="$(dirname "$0")/brain_293bc512-5508-4800-af50-2b638d8c28fb"
if [ ! -d "$BRAIN_SRC" ]; then
    BRAIN_SRC="$(dirname "$0")/../brain_293bc512-5508-4800-af50-2b638d8c28fb"
fi

if [ -d "$BRAIN_SRC" ]; then
    echo "🧠 [1/3] กำลัง Restore ความจำบทสนทนาและประวัติ Audit เข้า Antigravity บน Mac..."
    mkdir -p ~/.gemini/antigravity/brain/
    cp -R "$BRAIN_SRC" ~/.gemini/antigravity/brain/293bc512-5508-4800-af50-2b638d8c28fb
    echo "   ✅ เรียบร้อย! Antigravity บน Mac จะจำทุกบริบทและตัวเลข Audit ได้ทันที"
else
    echo "   ℹ️ ไม่พบโฟลเดอร์ brain (ข้ามขั้นตอน copy brain)"
fi

echo ""
echo "⚙️ [2/3] ตรวจสอบ Environment สำหรับ Mac M1..."
if [ -d "jeans-around-finance-os" ]; then
    cd jeans-around-finance-os
fi

if ! command -v python3 &> /dev/null; then
    echo "   ❌ ไม่พบ python3 บนเครื่อง กรุณาติดตั้ง Python"
else
    if [ ! -d ".venv" ]; then
        python3 -m venv .venv
    fi
    source .venv/bin/activate
    pip install -q -r requirements.txt 2>/dev/null || pip install -q fastapi uvicorn requests telethon
    echo "   ✅ Environment และ Libraries พร้อมใช้งาน 100%"
fi

echo ""
echo "🚀 [3/3] เปิด Dashboard บน Browser..."
echo "   - Local Server: http://localhost:8000"
echo "   - Cloud Render: https://jeans-finance-os.onrender.com"
echo ""

which open >/dev/null 2>&1 && open "http://localhost:8000" || open "https://jeans-finance-os.onrender.com"

if [ -f ".venv/bin/python3" ]; then
    .venv/bin/python3 -m uvicorn backend.app:app --host 0.0.0.0 --port 8000
else
    python3 -m uvicorn backend.app:app --host 0.0.0.0 --port 8000
fi
