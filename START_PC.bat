@echo off
chcp 65001 >nul
title Jeans Around Finance OS - PC Auto Sync Launcher

echo ==========================================================
echo    👖 JEANS AROUND FINANCE OS - PC AUTO SYNC LAUNCHER
echo ==========================================================
echo.

echo 🔄 [1/2] กำลังดึงข้อมูลล่าสุดจาก Central Cloud Hub อัตโนมัติ...
python hub_sync.py pull

echo.
echo 🚀 [2/2] เปิดระบบ Finance Hub Web Server...
echo    - Local Server: http://localhost:8000
echo    - Cloud Render: https://jeans-finance-os.onrender.com
echo.

start http://localhost:8000
python -m uvicorn backend.app:app --host 0.0.0.0 --port 8000 --reload
pause
