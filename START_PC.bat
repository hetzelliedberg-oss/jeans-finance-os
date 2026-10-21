@echo off
chcp 65001 >nul
title Jeans Around Finance OS - PC Auto Sync Launcher

echo ==========================================================
echo    👖 JEANS AROUND FINANCE OS - PC AUTO SYNC LAUNCHER
echo ==========================================================
echo.

set VENV_PY=C:\Users\PAWIN\.gemini\antigravity\scratch\fb-sales-ai-engine\.venv\Scripts\python.exe

echo 🔄 [1/2] กำลังดึงข้อมูลล่าสุดจาก Central Cloud Hub อัตโนมัติ...
"%VENV_PY%" hub_sync.py pull

echo.
echo 🚀 [2/2] เปิดระบบ Finance Hub Web Server...
echo    - บนคอมเครื่องนี้: http://127.0.0.1:8055
echo    - บน Mac / iPad / iPhone (Wi-Fi): http://192.168.1.109:8055
echo    - บน Tailscale (นอกบ้าน): http://100.71.23.107:8055
echo    - Cloud Render: https://jeans-finance-os.onrender.com
echo.

start http://127.0.0.1:8055
"%VENV_PY%" -m uvicorn backend.app:app --host 0.0.0.0 --port 8055 --reload
pause
