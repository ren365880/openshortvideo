@echo off
chcp 65001 >nul
REM openshortvideo startup script (Windows)

echo ========================================
echo     Starting openshortvideo...
echo ========================================
python  frontend/app_webui.py
pause