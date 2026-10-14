#!/bin/bash
cd "$(dirname "$0")"

echo "=========================================================="
echo "   👖 JEANS AROUND FINANCE OS - MACBOOK ONE-CLICK SETUP"
echo "=========================================================="
echo ""

# 1. Restore Antigravity Brain / Conversation History
BRAIN_SRC="$(dirname "$0")/../brain_293bc512-5508-4800-af50-2b638d8c28fb"
if [ ! -d "$BRAIN_SRC" ]; then
    BRAIN_SRC="$(dirname "$0")/brain_293bc512-5508-4800-af50-2b638d8c28fb"
fi

if [ -d "$BRAIN_SRC" ]; then
    echo "📦 [1/3] กำลัง Restore ความจำและประวัติ Conversation ข้ามมาที่ Antigravity บน Mac..."
    mkdir -p ~/.gemini/antigravity/brain/
    cp -R "$BRAIN_SRC" ~/.gemini/antigravity/brain/293bc512-5508-4800-af50-2b638d8c28fb
    echo "   ✅ เรียบร้อย! Antigravity บน Mac จะจำทุกคำถาม ข้อความ และ Audit ได้ทันที"
else
    echo "   ℹ️ ไม่พบโฟลเดอร์ brain ในแพ็กเกจ (ข้ามขั้นตอน copy brain)"
fi

echo ""
echo "⚙️ [2/3] กำลังตั้งค่า Python Virtual Environment..."
if ! command -v python3 &> /dev/null; then
    echo "   ⚠️ ไม่พบ python3 ในระบบ กรุณาติดตั้ง Python บน Mac"
else
    if [ ! -d ".venv" ]; then
        python3 -m venv .venv
    fi
    source .venv/bin/activate
    pip install -q -r requirements.txt 2>/dev/null || pip install -q fastapi uvicorn requests telethon
    echo "   ✅ Environment พร้อมใช้งาน"
    echo "   🔄 [Auto-Sync] กำลังดึงข้อมูลล่าสุดจาก Central Cloud Hub..."
    python3 hub_sync.py pull
fi

echo ""
echo "🚀 [3/3] เปิดระบบ Finance Hub..."
echo "   - Local Server: http://localhost:8000"
echo "   - Cloud Render: https://jeans-finance-os.onrender.com"
echo ""

# Open browser
which open >/dev/null 2>&1 && open "http://localhost:8000" || open "https://jeans-finance-os.onrender.com"

# Run local server
if [ -f ".venv/bin/python3" ]; then
    .venv/bin/python3 -m uvicorn backend.app:app --host 0.0.0.0 --port 8000
else
    python3 -m uvicorn backend.app:app --host 0.0.0.0 --port 8000
fi
