@echo off
chcp 65001 > nul
echo ===================================================
echo   Jeans Around Finance OS & Telegram Profit Hub
echo ===================================================
echo.
echo กำลังเริ่มต้นระบบ Web App...
echo.

cd /d "%~dp0"
set VENV_PY=C:\Users\PAWIN\.gemini\antigravity\scratch\fb-sales-ai-engine\.venv\Scripts\python.exe

echo ตรวจสอบและเปิด Server ที่พอร์ต 8055 (เปิดให้ Mac/iPhone เข้าผ่านวง LAN ได้)...
echo    - บนคอมเครื่องนี้: http://127.0.0.1:8055
echo    - บน Mac / iPad / iPhone (Wi-Fi เดียวกัน): http://192.168.1.109:8055
echo    - บน Tailscale (ใช้งานนอกบ้าน): http://100.71.23.107:8055
echo.

start "" http://127.0.0.1:8055

"%VENV_PY%" -m uvicorn backend.app:app --host 0.0.0.0 --port 8055
pause
